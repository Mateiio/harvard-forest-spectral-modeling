"""Stage C: recover surface reflectance from HF365's three indices.

hf365.xml states the three definitions exactly::

    EVI2 = 2.5 * ((NIR - RED) / (NIR + 2.4 * RED + 1))
    NDVI = (NIR - RED) / (NIR + RED)
    NIRV = NDVI * NIR

so NIR and RED invert in closed form from NDVI and NIRv::

    NIR = NIRv / NDVI
    RED = NIR * (1 - NDVI) / (1 + NDVI)

leaving EVI2 as an independent check that never entered the inversion.

**This is a product, not an audit.** The audit passes -- recomputed EVI2 matches
the archived values to a residual sd of 0.00059 against a rounding-only floor of
0.00045-0.00059, i.e. the two agree to the limit of the 3-decimal storage
precision, so there is no discrepancy to report. What earns its keep is the
uncertainty envelope: RED is recovered to ~0.3% relative (7e-5 absolute in the
growing season), which is two orders of magnitude below any plausible v1.4-to-v2.0
version difference. That is what makes attributing such a difference to the red
band rather than the NIR band feasible at all.

The three files do not share a date index. Never assume they nest -- see
:func:`date_sets`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wp0 import io

STORAGE_DP = 3                     # HF365 stores 3 decimals
HALF_ULP = 0.5 * 10 ** -STORAGE_DP  # +-0.0005 uniform rounding
N_DRAWS = 500
GROWING_DOY = (150, 250)


def _load(key: str) -> pd.DataFrame:
    df = io.read_raw(key)
    return df.set_index("date").sort_index()


def date_sets() -> pd.DataFrame:
    """Per-file date coverage. The mismatch is three-way and non-nested."""
    e, n, v = _load("hf365_evi2"), _load("hf365_ndvi"), _load("hf365_nirv")
    se, sn, sv = set(e.index), set(n.index), set(v.index)
    alld = sorted(se | sn | sv)
    return pd.DataFrame({
        "date": alld,
        "in_evi2": [d in se for d in alld],
        "in_ndvi": [d in sn for d in alld],
        "in_nirv": [d in sv for d in alld],
        "in_all_three": [d in se and d in sn and d in sv for d in alld],
    })


def invert(ndvi: np.ndarray, nirv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    nir = nirv / ndvi
    red = nir * (1.0 - ndvi) / (1.0 + ndvi)
    return nir, red


def evi2_from(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    return 2.5 * (nir - red) / (nir + 2.4 * red + 1.0)


def build(n_draws: int = N_DRAWS, seed: int = 0) -> tuple[pd.DataFrame, dict]:
    e, n, v = _load("hf365_evi2"), _load("hf365_ndvi"), _load("hf365_nirv")
    plots = [c for c in n.columns if c in v.columns]

    # NIR/RED need NDVI and NIRv only; EVI2 is held out for the closure check.
    pair = sorted(set(n.index) & set(v.index))
    N = n.loc[pair, plots].to_numpy(float)
    V = v.loc[pair, plots].to_numpy(float)
    nir, red = invert(N, V)

    rng = np.random.default_rng(seed)
    acc_nir = np.zeros((2,) + N.shape)   # running sum, sum of squares
    acc_red = np.zeros((2,) + N.shape)
    for _ in range(n_draws):
        dn = N + rng.uniform(-HALF_ULP, HALF_ULP, N.shape)
        dv = V + rng.uniform(-HALF_ULP, HALF_ULP, V.shape)
        a, b = invert(dn, dv)
        acc_nir[0] += a; acc_nir[1] += a * a
        acc_red[0] += b; acc_red[1] += b * b
    sd_nir = np.sqrt(np.maximum(acc_nir[1] / n_draws - (acc_nir[0] / n_draws) ** 2, 0))
    sd_red = np.sqrt(np.maximum(acc_red[1] / n_draws - (acc_red[0] / n_draws) ** 2, 0))

    long = pd.DataFrame({
        "date": np.repeat(pair, len(plots)),
        "plot": np.tile(plots, len(pair)),
        "ndvi": N.ravel(), "nirv": V.ravel(),
        "nir": nir.ravel(), "red": red.ravel(),
        "sd_nir": sd_nir.ravel(), "sd_red": sd_red.ravel(),
    })
    long["evi2_archived"] = (e.reindex(index=pair, columns=plots).to_numpy(float).ravel()
                             if len(set(pair) & set(e.index)) else np.nan)
    long["evi2_recomputed"] = evi2_from(long["nir"], long["red"])
    long["evi2_residual"] = long["evi2_recomputed"] - long["evi2_archived"]
    long = long.dropna(subset=["ndvi", "nirv"]).reset_index(drop=True)

    doy = pd.to_datetime(long["date"]).dt.dayofyear
    long["season"] = np.where(doy.between(*GROWING_DOY), "growing", "off")

    r = long["evi2_residual"].dropna()
    g = long[long["season"] == "growing"]
    stats = {
        "n_dates_pairwise_ndvi_nirv": len(pair),
        "n_cells": int(long["ndvi"].notna().sum()),
        "n_closure_cells": int(len(r)),
        "evi2_residual_sd": float(r.std()),
        "evi2_residual_abs_p95": float(r.abs().quantile(0.95)),
        "evi2_residual_abs_max": float(r.abs().max()),
        "mc_floor_sd_median": float(np.nanmedian(
            evi2_mc_floor(N, V, n_draws=min(n_draws, 200), seed=seed + 1))),
        "red_rel_sd_growing_p50": float((g["sd_red"] / g["red"]).median()),
        "red_abs_sd_growing_p50": float(g["sd_red"].median()),
        "nir_rel_sd_growing_p50": float((g["sd_nir"] / g["nir"]).median()),
    }
    stats["closure_within_rounding_floor"] = bool(
        stats["evi2_residual_sd"] <= stats["mc_floor_sd_median"] * 1.5)
    return long, stats


def evi2_mc_floor(N: np.ndarray, V: np.ndarray, n_draws: int, seed: int) -> np.ndarray:
    """Per-cell sd of recomputed EVI2 attributable to storage rounding alone."""
    rng = np.random.default_rng(seed)
    s = np.zeros(N.shape); s2 = np.zeros(N.shape)
    for _ in range(n_draws):
        dn = N + rng.uniform(-HALF_ULP, HALF_ULP, N.shape)
        dv = V + rng.uniform(-HALF_ULP, HALF_ULP, V.shape)
        a, b = invert(dn, dv)
        ev = evi2_from(a, b)
        s += ev; s2 += ev * ev
    return np.sqrt(np.maximum(s2 / n_draws - (s / n_draws) ** 2, 0))


def run() -> tuple[pd.DataFrame, dict]:
    ds = date_sets()
    long, stats = build()
    io.write(ds, "hf365_date_sets.csv")
    io.write(long, "hf365_reflectance.csv")
    io.record(
        stage="C",
        inputs=["hf365_evi2", "hf365_ndvi", "hf365_nirv", "eml_hf365"],
        params={"storage_dp": STORAGE_DP, "half_ulp": HALF_ULP,
                "n_draws": N_DRAWS, "growing_doy": list(GROWING_DOY),
                "join_mode": "pairwise(ndvi,nirv) for bands; intersection3 for closure"},
        outputs=["hf365_reflectance.csv", "hf365_date_sets.csv"],
        notes=f"EVI2 closure sd {stats['evi2_residual_sd']:.5f} vs rounding floor "
              f"{stats['mc_floor_sd_median']:.5f}. Dates are three-way non-nested: "
              f"{int(ds.in_all_three.sum())} in all three, {len(ds)} in the union.",
    )
    return long, stats
