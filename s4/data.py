"""Build the half-hourly transmittance series and its covariates.

Three things here are load-bearing and none of them are cosmetic.

**The two PAR files use different timestamp conventions.** WP0 established that
``hf004`` stamps mark the START of the hour, so its effective sampling centre is
stamp + 0.5 h. Two independent tests here put ``hf206-05`` at centre-labelled:
its parabola-vertex lag is -0.082 h where interval-start would give -0.25, and
minimising morning/afternoon asymmetry in tau at matched SZA also selects
centre. Aligning the two stamp-to-stamp would misalign numerator and denominator
by half an hour -- worst exactly where irradiance changes fastest, which is the
regime this study lives in.

**hf206-05 duplicates essentially all of 2024.** 20,350 rows share a duplicated
timestamp, 20,348 of them byte-identical, plus 2 genuinely conflicting rows in
2010. A naive load double-counts a year.

**Small negative PAR is sensor zero-offset, not bad data.** The ``_ave`` columns
bottom out near -3 umol m-2 s-1. The program says clamp, do not discard.
Separately, the +-7999 Campbell sentinels live in the ``_max`` columns, not the
``_ave`` ones used here.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from wp0 import io as wio, solar

OUT = Path(__file__).resolve().parent / "out"

# hf206-05 understory sensors -> biometry plot. EMS1 = C3, B2, C2; EMS2 = E3, F3, F2.
PAR_PLOT = {"par_c3_ave": "C3", "par_b2_ave": "B2", "par_c2_ave": "C2",
            "par_e3_ave": "E3", "par_f3_ave": "F3", "par_f2_ave": "F2"}
PRIMARY = ["C2", "E3", "B2"]        # lowest missingness (1.4, 1.4, 1.6 %)
REPLICATION = ["F3", "F2", "C3"]    # 7.6, 11.0, 12.1 %

HF004_CENTRE_OFFSET_H = 0.5   # interval-start hourly  -> centre is stamp + 0.5 h
HF206_CENTRE_OFFSET_H = 0.0   # centre-labelled        -> centre is the stamp

MIN_ABOVE_PAR = 100.0         # below this the ratio is dominated by sensor noise
MIN_ELEVATION_DEG = 10.0      # refraction and horizon obstruction below this


def load_understory() -> pd.DataFrame:
    """Long-format understory PAR, deduplicated, zero-offset clamped."""
    cols = list(PAR_PLOT)
    d = pd.read_csv(wio.RAW["hf206_ems"], usecols=["datetime"] + cols)
    t = pd.to_datetime(d["datetime"], errors="coerce")
    d = d.assign(t=t).dropna(subset=["t"])
    n_before = len(d)
    d = d.drop_duplicates(subset=["t"], keep="first").sort_values("t")
    dropped = n_before - len(d)

    d["t"] = d["t"].dt.tz_localize(wio.TZ)
    d["centre"] = d["t"] + pd.Timedelta(hours=HF206_CENTRE_OFFSET_H)
    long = d.melt(id_vars=["t", "centre"], value_vars=cols,
                  var_name="sensor", value_name="und")
    long["plot"] = long["sensor"].map(PAR_PLOT)
    long["und"] = pd.to_numeric(long["und"], errors="coerce").clip(lower=0.0)
    long.attrs["duplicate_rows_dropped"] = dropped
    return long.dropna(subset=["und"])[["centre", "plot", "und"]]


def load_above() -> pd.DataFrame:
    """Above-canopy PAR, measured diffuse fraction, and VPD, on centre times."""
    cols = ["datetime", "par.29", "par.dir.ue.m2.s", "par.dfs.ue.m2.s",
            "ta.27.9m", "rh.27.9m"]
    a = pd.read_csv(wio.RAW["hf004_final"], usecols=cols)
    a["t"] = pd.to_datetime(a["datetime"], errors="coerce")
    a = a.dropna(subset=["t"]).sort_values("t")
    a["t"] = a["t"].dt.tz_localize(wio.TZ)
    a["centre"] = a["t"] + pd.Timedelta(hours=HF004_CENTRE_OFFSET_H)

    a["abv"] = pd.to_numeric(a["par.29"], errors="coerce").clip(lower=0.0)
    dirp = pd.to_numeric(a["par.dir.ue.m2.s"], errors="coerce").clip(lower=0.0)
    dfs = pd.to_numeric(a["par.dfs.ue.m2.s"], errors="coerce").clip(lower=0.0)
    tot = dirp + dfs
    a["diffuse_frac"] = np.where(tot > 0, dfs / tot, np.nan)

    # VPD from canopy-top air temperature and relative humidity (Tetens)
    ta = pd.to_numeric(a["ta.27.9m"], errors="coerce")
    rh = pd.to_numeric(a["rh.27.9m"], errors="coerce").clip(0, 100)
    es = 0.6108 * np.exp(17.27 * ta / (ta + 237.3))
    a["vpd_kpa"] = (es * (1 - rh / 100)).clip(lower=0)
    return a[["centre", "abv", "diffuse_frac", "vpd_kpa"]].dropna(subset=["abv"])


def field_lai_daily() -> pd.DataFrame:
    """Per-plot daily PAI, interpolated within campaigns (raw, not woody-corrected)."""
    lai = pd.read_csv(wio.OUT / "hf069_plot_clean.csv", usecols=["date", "plot", "pai"])
    lai["date"] = pd.to_datetime(lai["date"])
    out = []
    for plot, d in lai.groupby("plot"):
        if plot not in PAR_PLOT.values():
            continue
        s = d.dropna(subset=["pai"]).sort_values("date").set_index("date")["pai"]
        if len(s) < 3:
            continue
        full = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))
        gap = full.notna().cumsum()
        size = full.isna().groupby(gap).transform("size")
        interp = full.interpolate("time")
        interp[size > 21] = np.nan
        out.append(pd.DataFrame({"plot": plot, "day": interp.index,
                                 "pai": interp.to_numpy()}))
    return pd.concat(out, ignore_index=True).dropna(subset=["pai"])


def build(start: str = "2008-01-01", end: str = "2023-12-31",
          clearsky_min: float = 0.0) -> pd.DataFrame:
    """Half-hourly transmittance with solar geometry and covariates attached."""
    und = load_understory()
    abv = load_above()
    g = (solar.grid(start, end, freq="15min")
         .rename(columns={"datetime_est": "centre"})
         [["centre", "sza_deg", "azimuth_deg", "elevation_deg",
           "clearsky_par", "toa_par"]].sort_values("centre"))

    m = pd.merge_asof(und.sort_values("centre"), abv.sort_values("centre"),
                      on="centre", direction="nearest",
                      tolerance=pd.Timedelta(minutes=31)).dropna(subset=["abv"])
    m = pd.merge_asof(m.sort_values("centre"), g, on="centre",
                      direction="nearest", tolerance=pd.Timedelta(minutes=8))
    m = m.dropna(subset=["sza_deg"])

    m = m[(m["elevation_deg"] > MIN_ELEVATION_DEG) & (m["abv"] > MIN_ABOVE_PAR)]
    if clearsky_min > 0:
        m = m[m["abv"] > clearsky_min * m["clearsky_par"]]

    m["tau"] = (m["und"] / m["abv"]).clip(0.0, 1.0)
    # clearness index: measured against theoretical top-of-atmosphere PAR
    m["kt"] = (m["abv"] / m["toa_par"]).replace([np.inf, -np.inf], np.nan).clip(0, 1.2)
    m["day"] = m["centre"].dt.normalize().dt.tz_localize(None)
    m["doy"] = m["centre"].dt.dayofyear
    m["year"] = m["centre"].dt.year
    m["hour"] = m["centre"].dt.hour + m["centre"].dt.minute / 60
    m["ampm"] = np.where(m["hour"] < 12, "am", "pm")

    m = m.merge(field_lai_daily(), on=["plot", "day"], how="left")
    m["group"] = np.where(m["plot"].isin(PRIMARY), "primary", "replication")
    return m.reset_index(drop=True)


def run(start: str = "2008-01-01", end: str = "2023-12-31") -> tuple[pd.DataFrame, dict]:
    t = build(start, end)
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT / "transmittance.csv", index=False)   # no parquet engine installed
    stats = {
        "rows": int(len(t)),
        "plots": sorted(t["plot"].unique()),
        "window": [str(t["centre"].min()), str(t["centre"].max())],
        "days": int(t["day"].nunique()),
        "with_lai": int(t["pai"].notna().sum()),
        "with_measured_diffuse": int(t["diffuse_frac"].notna().sum()),
        "tau_median": float(t["tau"].median()),
        "tau_p95": float(t["tau"].quantile(0.95)),
        "sza_range": [float(t["sza_deg"].min()), float(t["sza_deg"].max())],
        "alignment": {"hf004_centre_offset_h": HF004_CENTRE_OFFSET_H,
                      "hf206_centre_offset_h": HF206_CENTRE_OFFSET_H},
    }
    return t, stats
