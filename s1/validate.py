"""The two ground-referenced results, and the angle-band cross-check.

**Which assignment convention wins.** Interpolate field LAI to the acquisition
dates and correlate both the single-pixel and the area-weighted series against
it. Whichever tracks the ground better justifies the convention shipped in v2.
This needs nothing beyond WP0 and is the fastest defensible result in the
program.

Its honest limit, and it must be stated with the answer: field LAI is biweekly
in the shoulder seasons and monthly mid-summer, so it constrains the seasonal
trajectory, not any individual acquisition. It will detect sustained departures
well and single-date contamination poorly. Report the flag as a trajectory-level
departure, not a per-date verdict.

**The angle cross-check.** WP0 stage D already produced a pvlib solar series for
the tower. The HLS ``SZA`` band should agree with it at the acquisition instant.
Any disagreement is informative rather than fatal: L30 angles are derived for
the red band and applied to all bands, and S30 angles are interpolated from
ESA's 5 km grid using the 2nd red-edge band's view angle, so the residual
distribution differs by product **by construction**. S4's matched-SZA design
leans on these bands, so the size of that residual is a number it needs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from s1 import io as sio

MAX_LAI_GAP_DAYS = 21     # do not interpolate across a gap wider than this


def field_lai_daily(series: str = "pai") -> pd.DataFrame:
    """Per-plot daily field series, linearly interpolated within campaigns.

    ``series`` selects which of WP0's variants to use. WP0 deliberately ships
    raw PAI beside every woody-correction reading; the default here is raw PAI
    so the validation does not inherit an unresolved equation choice.
    """
    lai = sio.read_wp0("field_lai")
    lai["date"] = pd.to_datetime(lai["date"])
    col = series if series in lai.columns else "pai"

    out = []
    for plot, d in lai.groupby("plot"):
        d = d.sort_values("date").dropna(subset=[col])
        if len(d) < 3:
            continue
        s = d.set_index("date")[col]
        full = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))
        gap = full.notna().cumsum()
        size = full.isna().groupby(gap).transform("size")
        interp = full.interpolate("time")
        interp[size > MAX_LAI_GAP_DAYS] = np.nan
        out.append(pd.DataFrame({"plot": plot, "date": interp.index,
                                 "field_lai": interp.to_numpy()}))
    return pd.concat(out, ignore_index=True).dropna(subset=["field_lai"])


def compare_conventions(v20: pd.DataFrame, measure: str = "ndvi",
                        series: str = "pai") -> pd.DataFrame:
    """Correlate each convention against interpolated field LAI, per plot and pooled."""
    fl = field_lai_daily(series)
    df = v20.copy()
    df["date"] = pd.to_datetime(df["date"])
    m = df.merge(fl, on=["plot", "date"], how="inner")

    rows = []
    for conv in ("single", "weighted"):
        col = f"{measure}_{conv}"
        if col not in m.columns:
            continue
        sub = m.dropna(subset=[col, "field_lai"])
        if len(sub) < 10:
            continue
        r, p = stats.pearsonr(sub[col], sub["field_lai"])
        rs, _ = stats.spearmanr(sub[col], sub["field_lai"])
        per_plot = (sub.groupby("plot")
                    .apply(lambda g: stats.pearsonr(g[col], g["field_lai"])[0]
                           if len(g) > 5 else np.nan, include_groups=False)
                    .dropna())
        rows.append({"convention": conv, "measure": measure, "n": int(len(sub)),
                     "n_plots": int(sub["plot"].nunique()),
                     "pearson_r": float(r), "r2": float(r ** 2),
                     "spearman_r": float(rs), "p_value": float(p),
                     "median_per_plot_r": float(per_plot.median()),
                     "n_plots_scored": int(len(per_plot))})
    out = pd.DataFrame(rows)
    if len(out) == 2:
        win = out.loc[out["pearson_r"].idxmax(), "convention"]
        out["winner"] = win
        out["margin_r"] = out["pearson_r"].max() - out["pearson_r"].min()
    out["caveat"] = ("field LAI is biweekly in shoulder seasons and monthly "
                     "mid-summer: this constrains the seasonal trajectory, not "
                     "individual acquisitions")
    return out


def check_sza(pix: pd.DataFrame, tolerance: str = "20min") -> pd.DataFrame:
    """HLS SZA band vs WP0's pvlib series at each acquisition instant.

    Matched with ``merge_asof`` rather than ``np.interp``. Converting two
    tz-aware columns to int64 is not safe here: pandas may carry one as
    microsecond resolution and the other as nanosecond, and the silent 1000x
    mismatch lands the lookup in the middle of the night -- it produced a
    nonsensical -78 degree residual before this was caught.
    """
    sol = sio.read_wp0("solar_30min", usecols=["datetime_est", "sza_deg"])
    sol["t"] = pd.to_datetime(sol["datetime_est"], utc=True).astype("datetime64[ns, UTC]")
    sol = sol.dropna(subset=["sza_deg"]).sort_values("t")[["t", "sza_deg"]]

    obs = pix.dropna(subset=["sza", "sensing_time_utc"]).copy()
    obs = obs.drop_duplicates(["date", "product"])
    obs["t"] = pd.to_datetime(obs["sensing_time_utc"], utc=True).astype("datetime64[ns, UTC]")
    obs = obs.sort_values("t")

    m = pd.merge_asof(obs, sol, on="t", direction="nearest",
                      tolerance=pd.Timedelta(tolerance))
    m["sza_pvlib"] = m["sza_deg"]
    m["sza_residual"] = m["sza"] - m["sza_pvlib"]
    m["angle_provenance"] = m["product"].map(
        {k: v for k, v in __import__("s1.schema", fromlist=["x"]).ANGLE_PROVENANCE.items()})
    return m


def sza_summary(obs: pd.DataFrame) -> pd.DataFrame:
    if obs.empty:
        return pd.DataFrame()
    return (obs.groupby(["product", "angle_provenance"])["sza_residual"]
            .agg(n="size", median="median", mad=lambda s: float((s - s.median()).abs().median()),
                 p05=lambda s: s.quantile(0.05), p95=lambda s: s.quantile(0.95))
            .reset_index())


def convention_by_overlap(v20: pd.DataFrame, measure: str = "ndvi",
                          series: str = "pai") -> pd.DataFrame:
    """The convention comparison stratified by how split each plot actually is.

    Pooling hides the answer: 7 plots sit wholly inside one pixel, where the two
    conventions are identical by construction and can only dilute a difference.
    The question is whether area-weighting helps *where the plot is split*.
    """
    from scipy import stats as st
    cw = sio.read_wp0("crosswalk_hls")
    dom = cw[cw["is_dominant"]].set_index("plot")["overlap_frac"]
    fl = field_lai_daily(series)
    fl["date"] = pd.to_datetime(fl["date"]).dt.strftime("%Y-%m-%d")

    m = v20.copy()
    m["dom_overlap"] = m["plot"].map(dom)
    m = m.merge(fl, on=["plot", "date"], how="inner")

    rows = []
    for lo, hi, lab in [(0.0, 0.5, "<50%"), (0.5, 0.8, "50-80%"),
                        (0.8, 0.999, "80-100%"), (0.999, 1.01, "fully inside")]:
        s = m[(m["dom_overlap"] >= lo) & (m["dom_overlap"] < hi)].dropna(
            subset=[f"{measure}_single", f"{measure}_weighted", "field_lai"])
        if len(s) < 30:
            continue
        r1 = st.pearsonr(s[f"{measure}_single"], s["field_lai"])[0]
        r2 = st.pearsonr(s[f"{measure}_weighted"], s["field_lai"])[0]
        rows.append({"overlap_band": lab, "n": len(s), "n_plots": s["plot"].nunique(),
                     "r_single": r1, "r_weighted": r2, "r_weighted_minus_single": r2 - r1,
                     "median_abs_diff": float(
                         (s[f"{measure}_single"] - s[f"{measure}_weighted"]).abs().median())})
    return pd.DataFrame(rows)
