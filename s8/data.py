"""Build the ground-satellite pair table. `python -m s8 build` -> s8/out/pairs.csv

One row is one HF069 plot reading matched to the nearest usable HF365 v2
observation of that same plot.

Four matching decisions, each with a measured reason:

  * **match per plot, never site-wide.** The plot dimension is the point; a
    site mean throws away the 14 % of variance that is per-plot offset.
  * **nearest pass within a tolerance, not exact dates.** The two calendars are
    near-disjoint by construction -- a satellite orbit against a field crew's
    schedule. Exact joining finds 17 pairs where +-8 days finds 4,378.
  * **one-to-one.** Plain ``merge_asof(direction="nearest")`` lets one satellite
    pass partner two ground readings when HF365 has a long gap (its median gap
    is 6 days, its max 57). Deduplicate on the satellite date, keeping the
    tightest match.
  * **default tolerance 3 days, not 8.** +-3 costs 30 % of the sample and buys
    R2 +0.019; the looser windows are kept available because the shoulder
    seasons move fast enough that an 8-day gap is itself disagreement.

The instrument floor defaults to 2015. LAI-2000 runs to 2014-11-04 and LAI-2200
from 2015-04-17 with no overlap period, so anything earlier sits on the far side
of a calibration break for 392 extra pairs.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from s1 import io as sio

PKG = Path(__file__).resolve().parent
OUT = PKG / "out"

TOL_DAYS = 3
INSTRUMENT_FLOOR = "2015-01-01"     # LAI-2200 era only; see module docstring
INDICES = ["evi2", "ndvi", "nirv"]


def load_ground(instrument_floor: str | None = INSTRUMENT_FLOOR) -> pd.DataFrame:
    """WP0's cleaned HF069, with the woody correction already carried."""
    g = pd.read_csv(sio.WP0_INPUTS["field_lai"], parse_dates=["date"])
    keep = ["date", "plot", "pai", "se", "n_reps", "campaign_id", "year", "doy",
            "instrument", "lai_subtractive_fx", "lai_subtractive_py"]
    g = g[[c for c in keep if c in g.columns]].dropna(subset=["pai"])
    g = g.rename(columns={"lai_subtractive_fx": "lai"})
    if instrument_floor:
        g = g[g["date"] >= pd.Timestamp(instrument_floor)]
    return g.sort_values(["date", "plot"], ignore_index=True)


def load_satellite() -> pd.DataFrame:
    """S1's reprocessed archive, usable observations only.

    ``single_usable`` is S1's own gate; the weighted columns are carried for a
    sensitivity check but are not the default, because S1-05 measured
    single-pixel and area-weighted assignment as indistinguishable.
    """
    h = pd.read_csv(sio.OUT / "hf365_v2_candidate.csv", parse_dates=["date"])
    h = h[h["single_usable"]].copy()
    cols = (["date", "plot", "sza", "vza", "product", "platform",
             "weight_coverage", "evi2_sd_tc"]
            + [f"{i}_single" for i in INDICES]
            + [f"{i}_weighted" for i in INDICES]
            + ["red_single", "nir_single"])
    h = h[[c for c in cols if c in h.columns]]
    return h.rename(columns={f"{i}_single": i for i in INDICES})


def match(ground: pd.DataFrame, sat: pd.DataFrame,
          tol_days: int = TOL_DAYS) -> pd.DataFrame:
    """Nearest usable pass per plot, one satellite observation used at most once."""
    out = []
    for plot, gp in ground.groupby("plot"):
        hp = sat[sat["plot"] == plot]
        if hp.empty:
            continue
        hp = hp.drop(columns="plot").sort_values("date").rename(columns={"date": "sat_date"})
        m = pd.merge_asof(gp.sort_values("date"), hp,
                          left_on="date", right_on="sat_date",
                          direction="nearest", tolerance=pd.Timedelta(days=tol_days))
        out.append(m)
    m = pd.concat(out, ignore_index=True).dropna(subset=["evi2"])
    m["days_apart"] = (m["date"] - m["sat_date"]).dt.days.abs()
    m = (m.sort_values("days_apart")
           .drop_duplicates(subset=["plot", "sat_date"], keep="first"))
    return m.sort_values(["date", "plot"], ignore_index=True)


def add_features(m: pd.DataFrame) -> pd.DataFrame:
    """Calendar harmonics. SZA is deliberately absent -- see the package docstring."""
    m = m.copy()
    ang = 2 * np.pi * m["doy"] / 365.0
    m["sin_doy"], m["cos_doy"] = np.sin(ang), np.cos(ang)
    return m


def run(tol_days: int = TOL_DAYS,
        instrument_floor: str | None = INSTRUMENT_FLOOR) -> tuple[pd.DataFrame, dict]:
    g, h = load_ground(instrument_floor), load_satellite()
    m = add_features(match(g, h, tol_days))
    OUT.mkdir(exist_ok=True)
    m.to_csv(OUT / "pairs.csv", index=False)
    stats = {
        "n_pairs": int(len(m)),
        "n_plots": int(m["plot"].nunique()),
        "n_ground_dates": int(m["date"].nunique()),
        "n_campaigns": int(m["campaign_id"].nunique()),
        "window": [str(m["date"].min().date()), str(m["date"].max().date())],
        "tol_days": tol_days,
        "instrument_floor": instrument_floor,
        "mean_days_apart": round(float(m["days_apart"].mean()), 3),
        "ground_rows_offered": int(len(g)),
        "match_rate": round(len(m) / len(g), 3),
        "pai_sd": round(float(m["pai"].std()), 4),
        "lai_sd": round(float(m["lai"].std()), 4),
    }
    return m, stats


def load_pairs() -> pd.DataFrame:
    return pd.read_csv(OUT / "pairs.csv", parse_dates=["date", "sat_date"])
