"""Forecast LAI at a future date. `python -m s8 forecast` -> s8/out/forecast_*.csv

S8's retrieval needs the satellite pass for the date it is predicting, so it can
only reach dates already observed. This module answers the other question: given
everything known on day ``D - h``, what is the leaf area on day ``D``?

**The setup is a hard cutoff, not a tolerance window.** For a ground reading on
``D``, only satellite observations dated ``D - h`` or earlier are admissible.
Nothing inside the horizon is visible, which is what makes the score a forecast
rather than a retrieval scored oddly.

**The calendar is not cheating.** Day-of-year for the target date is known
arbitrarily far ahead, so it is legitimately available at forecast time. That is
also why it is the baseline: a wall calendar forecasts LAI with no data at all,
and anything built here has to beat it.

**Three references, in increasing difficulty to beat.**

``calendar``      target date only. Free, available for any future date.
``persistence``   run the retrieval on the last pass, carry that value forward
                  unchanged. This is the honest "nothing has changed since we
                  last looked" answer.
``forecast``      last pass spectra, the target date's calendar, how stale the
                  pass is, and how fast the indices were moving.

Beating ``calendar`` shows the satellite helps. Beating ``persistence`` shows
the model is projecting change rather than repeating the last observation. The
second is the one that matters, and it is much harder.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from s8 import data as s8data
from s8 import model as s8model

PKG = Path(__file__).resolve().parent
OUT = PKG / "out"

HORIZONS = (8, 16, 32, 64)
MAX_STALENESS = 45      # days; beyond this the last pass carries no usable signal
SPECTRAL = s8model.SPECTRAL


def _with_lags(sat: pd.DataFrame) -> pd.DataFrame:
    """Per plot, attach the previous usable pass so a rate of change exists."""
    out = []
    for plot, sp in sat.groupby("plot"):
        sp = sp.sort_values("date").copy()
        gap = sp["date"].diff().dt.days
        for i in SPECTRAL:
            sp[f"d_{i}"] = sp[i].diff() / gap.replace(0, np.nan)
        sp["prev_gap"] = gap
        out.append(sp)
    return pd.concat(out, ignore_index=True)


def build(horizon: int, instrument_floor: str | None = s8data.INSTRUMENT_FLOOR,
          max_staleness: int = MAX_STALENESS) -> pd.DataFrame:
    """One row per ground reading that has an admissible prior observation."""
    g = s8data.load_ground(instrument_floor)
    sat = _with_lags(s8data.load_satellite())
    g = g.assign(cutoff=g["date"] - pd.Timedelta(days=horizon))

    parts = []
    for plot, gp in g.groupby("plot"):
        sp = sat[sat["plot"] == plot]
        if sp.empty:
            continue
        sp = (sp.drop(columns="plot").sort_values("date")
                .rename(columns={"date": "last_pass"}))
        m = pd.merge_asof(gp.sort_values("cutoff"), sp,
                          left_on="cutoff", right_on="last_pass",
                          direction="backward")
        parts.append(m)

    m = pd.concat(parts, ignore_index=True).dropna(subset=SPECTRAL)
    m["lead_days"] = (m["date"] - m["last_pass"]).dt.days
    m = m[m["lead_days"] <= horizon + max_staleness]

    ang = 2 * np.pi * m["doy"] / 365.0                    # TARGET date, known ahead
    m["sin_doy"], m["cos_doy"] = np.sin(ang), np.cos(ang)
    last_doy = m["last_pass"].dt.dayofyear
    m["sin_last"] = np.sin(2 * np.pi * last_doy / 365.0)  # the pass's own calendar
    m["cos_last"] = np.cos(2 * np.pi * last_doy / 365.0)
    m["doy_last"] = last_doy
    m["horizon"] = horizon
    return m.sort_values(["date", "plot"], ignore_index=True)


#: name -> (columns, plot dummies). ``persistence`` deliberately uses the last
#: pass's own calendar, so it predicts the leaf area *then*, not now.
REFERENCES: dict[str, tuple[list[str], bool]] = {
    "calendar": (["sin_doy", "cos_doy", "doy"], True),
    "persistence": (SPECTRAL + ["sin_last", "cos_last", "doy_last"], True),
    "forecast": (SPECTRAL + ["sin_doy", "cos_doy", "doy"], True),
    "forecast + trend": (SPECTRAL + [f"d_{i}" for i in SPECTRAL]
                         + ["sin_doy", "cos_doy", "doy", "lead_days"], True),
}


def run(horizons=HORIZONS) -> tuple[pd.DataFrame, dict]:
    OUT.mkdir(exist_ok=True)
    rows, frames = [], []
    for h in horizons:
        m = build(h)
        if len(m) < 200:
            continue
        frames.append(m)
        for name, (cols, plots) in REFERENCES.items():
            sub = m.dropna(subset=cols + ["lai"])
            d = s8model.build(sub, cols, plots, "lai", "known_plot")
            _, s = s8model.cross_validate(d)
            rows.append({"horizon_days": h, "reference": name,
                         "median_lead_days": int(sub["lead_days"].median()), **s})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "forecast_results.csv", index=False)
    pd.concat(frames, ignore_index=True).to_csv(OUT / "forecast_pairs.csv", index=False)

    piv = res.pivot(index="horizon_days", columns="reference", values="r2")
    summary = {
        "horizons": list(piv.index.astype(int)),
        "r2": {c: [round(float(v), 4) for v in piv[c]] for c in piv.columns},
        "beats_calendar": {int(h): bool(piv.loc[h, "forecast + trend"]
                                        > piv.loc[h, "calendar"]) for h in piv.index},
        "beats_persistence": {int(h): bool(piv.loc[h, "forecast + trend"]
                                           > piv.loc[h, "persistence"])
                              for h in piv.index},
        "max_staleness_days": MAX_STALENESS,
        "note": ("retrieval scores R2 "
                 f"{json.loads((OUT / 'results_summary.json').read_text('utf8'))['known_plot']['r2']:.3f} "
                 "with the same-date pass available; every number here is "
                 "strictly worse by construction"),
    }
    (OUT / "forecast_summary.json").write_text(json.dumps(summary, indent=2), "utf8")
    return res, summary
