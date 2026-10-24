"""The decomposition: geometry within a day, canopy across days at matched illumination.

The matched-pair idea is implemented by **conditioning rather than enumeration**.
Forming all pairs over 600k observations is unnecessary; grouping achieves the
same matching exactly and in linear time.

  * **Geometry.** Within one plot on one day, leaf area, leaf angle and structure
    are constant by construction, so everything that moves is illumination.
    Beer-Lambert says ``tau = exp(-G(theta) L / cos theta)``, so regressing
    ``ln tau`` on ``sec(SZA)`` within a day has slope ``-G*L`` -- the effective
    extinction for that day, obtained without assuming a value for G.

  * **Canopy.** Within one plot and one narrow (SZA, diffuse fraction) cell,
    illumination is matched by construction, so everything that moves is canopy.
    Regressing ``tau`` on leaf area within such a cell is the matched-pair
    contrast, and observations in a cell come from different days by
    construction -- a plot cannot revisit the same SZA twice in a day except
    once side of noon.

**Fensholt unmodified is the baseline, characterised not beaten.** For a
spherical leaf angle distribution ``G = 0.5``, so the daily extinction should be
``0.5 * LAI``. Comparing the measured ``G*L`` against that is the whole test:
a G that is stable across the season means Beer-Lambert with a fixed leaf angle
distribution suffices; a G that drifts with season at fixed LAI is the
geometry-canopy entanglement this study is looking for.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MIN_PER_DAY = 8            # half-hours needed to fit a within-day slope
MIN_PER_CELL = 12          # observations needed in an illumination cell
SZA_BIN_DEG = 1.0          # program specifies matching within 1 degree
DIFFUSE_BIN = 0.1
MIN_TAU = 1e-4             # ln(tau) needs a floor; below this it is sensor noise
G_SPHERICAL = 0.5          # Fensholt / Beer-Lambert with a spherical LAD


def _ols(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """slope, intercept, r2 -- no statsmodels in this environment."""
    X = np.column_stack([np.ones_like(x), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return float(beta[1]), float(beta[0]), (1 - ss_res / ss_tot if ss_tot > 0 else np.nan)


def daily_extinction(t: pd.DataFrame, clear_only: bool = True,
                     kt_min: float = 0.6) -> pd.DataFrame:
    """Per plot-day: fit ln(tau) ~ sec(SZA). Slope is -G*L for that day.

    Canopy is constant within a day, so this isolates the geometric response
    with no model of the canopy at all.
    """
    d = t[(t["tau"] > MIN_TAU) & t["tau"].notna()].copy()
    if clear_only:
        d = d[d["kt"] >= kt_min]
    d["sec"] = 1.0 / np.cos(np.radians(d["sza_deg"]))
    d["ln_tau"] = np.log(d["tau"])

    rows = []
    for (plot, day), g in d.groupby(["plot", "day"], sort=False):
        if len(g) < MIN_PER_DAY or g["sec"].nunique() < 4:
            continue
        slope, intercept, r2 = _ols(g["sec"].to_numpy(), g["ln_tau"].to_numpy())
        rows.append({
            "plot": plot, "day": day, "n": len(g),
            "kL": -slope,                      # G(theta)*L, the effective extinction
            "ln_tau0": intercept, "r2": r2,
            "sza_min": float(g["sza_deg"].min()), "sza_max": float(g["sza_deg"].max()),
            "sza_span": float(g["sza_deg"].max() - g["sza_deg"].min()),
            "pai": float(g["pai"].median()) if g["pai"].notna().any() else np.nan,
            "diffuse_frac": float(g["diffuse_frac"].median()),
            "doy": int(g["doy"].iloc[0]), "year": int(g["year"].iloc[0]),
            "group": g["group"].iloc[0],
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["G_measured"] = out["kL"] / out["pai"]
    out["kL_beer_spherical"] = G_SPHERICAL * out["pai"]
    out["kL_residual"] = out["kL"] - out["kL_beer_spherical"]
    return out


def canopy_at_matched_illumination(t: pd.DataFrame, kt_min: float = 0.6) -> pd.DataFrame:
    """Within matched (plot, SZA, diffuse) cells, how does tau track leaf area?

    Illumination is held fixed by the cell, so any remaining dependence is
    canopy. This is the matched-pair contrast, computed by conditioning.
    """
    d = t[(t["tau"] > MIN_TAU) & t["pai"].notna() & t["diffuse_frac"].notna()].copy()
    d = d[d["kt"] >= kt_min]
    d["sza_bin"] = (d["sza_deg"] / SZA_BIN_DEG).round() * SZA_BIN_DEG
    d["dif_bin"] = (d["diffuse_frac"] / DIFFUSE_BIN).round() * DIFFUSE_BIN

    rows = []
    for (plot, sb, db), g in d.groupby(["plot", "sza_bin", "dif_bin"], sort=False):
        if len(g) < MIN_PER_CELL or g["pai"].nunique() < 5:
            continue
        slope, _, r2 = _ols(g["pai"].to_numpy(), np.log(g["tau"].to_numpy()))
        rows.append({"plot": plot, "sza_bin": sb, "dif_bin": db, "n": len(g),
                     "n_days": g["day"].nunique(),
                     "dlntau_dLAI": slope, "r2": r2,
                     "pai_span": float(g["pai"].max() - g["pai"].min())})
    return pd.DataFrame(rows)


def marginal_sza_curve(ext: pd.DataFrame, n_splines: int = 12) -> pd.DataFrame:
    """Smooth the daily extinction against season, holding leaf area fixed.

    A GAM is used here only to pool and smooth what the daily fits already
    separated. It is not asked to predict and is not scored on held-out
    accuracy. Because SZA and day-of-year are dependent by construction, giving
    a GAM smoothers for both invites concurvity -- so the response modelled here
    is the *daily extinction* (already free of within-day geometry) against
    canopy state and season.
    """
    from pygam import LinearGAM, s

    d = ext.dropna(subset=["kL", "pai", "diffuse_frac"]).copy()
    if len(d) < 100:
        return pd.DataFrame()
    X = d[["pai", "doy", "diffuse_frac"]].to_numpy()
    y = d["kL"].to_numpy()
    gam = LinearGAM(s(0, n_splines=n_splines) + s(1, n_splines=n_splines)
                    + s(2, n_splines=6)).fit(X, y)

    rows = []
    for i, name in enumerate(["pai", "doy", "diffuse_frac"]):
        grid = gam.generate_X_grid(term=i)
        pdep, ci = gam.partial_dependence(term=i, X=grid, width=0.95)
        rows.append(pd.DataFrame({"term": name, "x": grid[:, i],
                                  "partial": pdep, "lo": ci[:, 0], "hi": ci[:, 1]}))
    out = pd.concat(rows, ignore_index=True)
    out.attrs["pseudo_r2"] = float(gam.statistics_["pseudo_r2"]["explained_deviance"])
    return out


def seasonal_hysteresis(ext: pd.DataFrame, lai_tol: float = 0.3) -> pd.DataFrame:
    """Does extinction differ between spring and autumn at the SAME leaf area?

    Spring and autumn pass through identical leaf area on the way up and down.
    If Beer-Lambert with a fixed leaf angle distribution were sufficient,
    extinction would be identical at matched LAI. A difference is canopy
    structure changing in a way leaf area alone does not capture.
    """
    d = ext.dropna(subset=["kL", "pai"]).copy()
    d["phase"] = np.where(d["doy"] <= 200, "spring", "autumn")
    d["lai_bin"] = (d["pai"] / lai_tol).round() * lai_tol
    p = (d.groupby(["lai_bin", "phase"])["kL"]
         .agg(["median", "size"]).unstack())
    if p.empty or "median" not in p.columns.get_level_values(0):
        return pd.DataFrame()
    med, cnt = p["median"], p["size"]
    keep = (cnt.min(axis=1) >= 10) if cnt.shape[1] == 2 else pd.Series(dtype=bool)
    res = pd.DataFrame({
        "lai_bin": med.index,
        "kL_spring": med.get("spring"), "kL_autumn": med.get("autumn"),
        "n_spring": cnt.get("spring"), "n_autumn": cnt.get("autumn"),
    })
    res["difference"] = res["kL_autumn"] - res["kL_spring"]
    return res[keep.reindex(res.index, fill_value=False).to_numpy()] if len(keep) else res
