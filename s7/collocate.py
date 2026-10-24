"""Build the three-way collocated triplet.

Three views of the same canopy, at three supports:

  * **ground** -- HF069 plant area index over a 314 m2 plot;
  * **HLS** -- a 30 m (900 m2) pixel, from S1's reprocessed product;
  * **MODIS** -- a 500 m (~215,000 m2) MCD15A2H cell.

Triple collocation does not require the three to share units. It requires each
to be *linearly* related to the same latent quantity, and estimates each one's
error variance in its own units. Whether that linearity actually holds here is
not assumed -- :mod:`s7.tc` tests it, because NDVI saturates at high LAI and a
saturating relationship breaks the model rather than merely adding noise.

Matching is asymmetric on purpose. Ground visits are the scarce term (biweekly
in the shoulder seasons, monthly mid-summer), so each ground measurement anchors
a triplet and the two satellite streams are matched to it within a tolerance.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from s1 import io as sio

MODIS_CSV = Path(r"c:\crtusers\matei\prj\data\MODIS"
                 r"\Main5Pixels-PointSample-MCD15A2H-061-results.csv")
OUT = Path(__file__).resolve().parent / "out"

HLS_TOL_DAYS = 4        # HLS revisit is a few days; keep the match tight
MODIS_TOL_DAYS = 4      # MCD15A2H is an 8-day composite, so +-4 covers one window
MODIS_QC_GOOD = "Good quality (main algorithm with or without saturation)"
MODIS_FILL_MIN, MODIS_FILL_MAX = 0.0, 10.0


def load_modis() -> pd.DataFrame:
    cols = ["ID", "Date", "MCD15A2H_061_Lai_500m", "MCD15A2H_061_LaiStdDev_500m",
            "MCD15A2H_061_Fpar_500m",
            "MCD15A2H_061_FparLai_QC_MODLAND_Description"]
    m = pd.read_csv(MODIS_CSV, usecols=cols).rename(columns={
        "MCD15A2H_061_Lai_500m": "modis_lai",
        "MCD15A2H_061_LaiStdDev_500m": "modis_lai_sd",
        "MCD15A2H_061_Fpar_500m": "modis_fpar",
        "MCD15A2H_061_FparLai_QC_MODLAND_Description": "modis_qc"})
    m["date"] = pd.to_datetime(m["Date"])
    m["appeears_pixel"] = m["ID"].astype(str).str.replace("_", "", regex=False)
    good = m["modis_qc"] == MODIS_QC_GOOD
    inrange = m["modis_lai"].between(MODIS_FILL_MIN, MODIS_FILL_MAX)
    # StdDev carries its own fill (248); do not let it through as a real number
    m.loc[m["modis_lai_sd"] > 10, "modis_lai_sd"] = np.nan
    m["modis_good"] = good & inrange
    return m[m["modis_good"]][["date", "appeears_pixel", "modis_lai",
                               "modis_lai_sd", "modis_fpar"]]


def load_ground() -> pd.DataFrame:
    g = sio.read_wp0("field_lai", usecols=["date", "plot", "pai", "n_reps"])
    g["date"] = pd.to_datetime(g["date"])
    return g.dropna(subset=["pai"])


def load_hls(measure: str = "evi2") -> pd.DataFrame:
    h = pd.read_csv(sio.OUT / "hf365_v2_candidate.csv")
    h = h[h["single_usable"]].copy()
    h["date"] = pd.to_datetime(h["date"])
    keep = ["date", "plot", "product", "platform",
            f"{measure}_single", f"{measure}_weighted", "sza", "weight_coverage"]
    return h[keep].rename(columns={f"{measure}_single": "hls",
                                   f"{measure}_weighted": "hls_weighted"})


def _nearest(anchor: pd.DataFrame, other: pd.DataFrame, on: list[str],
             tol_days: int, suffix: str) -> pd.DataFrame:
    """Nearest-in-time match per group, within tolerance."""
    a = anchor.sort_values("date")
    o = other.sort_values("date")
    m = pd.merge_asof(a, o, on="date", by=on, direction="nearest",
                      tolerance=pd.Timedelta(days=tol_days),
                      suffixes=("", f"_{suffix}"))
    return m


def build(measure: str = "evi2", hls_tol: int = HLS_TOL_DAYS,
          modis_tol: int = MODIS_TOL_DAYS, active_only: bool = True) -> pd.DataFrame:
    reg = sio.read_wp0("plot_registry")
    xw = sio.read_wp0("crosswalk_hls")            # not used, but keeps provenance honest
    modis_cw = pd.read_csv(
        Path(sio.WP0_INPUTS["plot_registry"]).parent / "crosswalk_plot_to_modis.csv",
        usecols=["plot", "status", "appeears_pixel"])

    g = load_ground()
    if active_only:
        g = g[g["plot"].isin(set(reg.loc[reg["status"] == "active_tower", "plot"]))]
    g = g.merge(modis_cw[["plot", "appeears_pixel"]], on="plot", how="left")
    g = g[g["appeears_pixel"].isin(load_modis()["appeears_pixel"].unique())]

    h = load_hls(measure)
    # one HLS row per plot-date: prefer the observation closest to the ground visit
    h = h.sort_values(["plot", "date"]).drop_duplicates(["plot", "date"])

    trip = _nearest(g, h, on=["plot"], tol_days=hls_tol, suffix="hls")
    trip = trip.rename(columns={"date": "ground_date"})
    trip["date"] = trip["ground_date"]

    md = load_modis()
    trip = _nearest(trip, md, on=["appeears_pixel"], tol_days=modis_tol, suffix="modis")

    trip = trip.dropna(subset=["pai", "hls", "modis_lai"])
    trip["year"] = trip["ground_date"].dt.year
    trip["doy"] = trip["ground_date"].dt.dayofyear
    trip["measure"] = measure
    return trip.reset_index(drop=True)


def run(measure: str = "evi2") -> tuple[pd.DataFrame, dict]:
    t = build(measure)
    OUT.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT / f"triplet_{measure}.csv", index=False)
    stats = {
        "measure": measure,
        "n_triplets": int(len(t)),
        "n_plots": int(t["plot"].nunique()),
        "n_ground_dates": int(t["ground_date"].nunique()),
        "n_modis_cells": int(t["appeears_pixel"].nunique()),
        "window": [str(t["ground_date"].min().date()), str(t["ground_date"].max().date())],
        "hls_tol_days": HLS_TOL_DAYS, "modis_tol_days": MODIS_TOL_DAYS,
    }
    return t, stats
