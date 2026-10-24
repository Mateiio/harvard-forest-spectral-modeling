"""Fit and score the retrieval. `python -m s8 fit` -> s8/out/

**Two regimes, because plot dummies answer two different questions.**

``known_plot``  dummies in, folds grouped by field campaign. Answers "what was
                the leaf area at plot C2 on a date nobody visited?" The plot has
                appeared in training on other dates, so its offset is learnable.
``new_plot``    dummies out, folds grouped by plot. Answers "what is the leaf
                area at a plot never measured?" The held-out plot is unseen.

Reporting one number without saying which regime produced it is the easiest way
to overstate this model, so both are always written.

**Ridge, not a random forest.** Measured, not assumed: with folds grouped by
campaign a random forest scores 0.859 against ridge's 0.885. Ungrouped splits
let a forest memorise date-specific patterns, which is why the earlier
MODIS-target notebook found the opposite ordering.

Grouping is by ``campaign_id``, not raw date. WP0 defines a campaign as visits
within 3 days of each other, so two dates from one field trip are one sampling
occasion and must not straddle a fold boundary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.metrics import r2_score

from s8 import data as s8data

PKG = Path(__file__).resolve().parent
OUT = PKG / "out"

ALPHA = 1.0
N_SPLITS = 5
TARGETS = ["lai", "pai"]
CALENDAR = ["sin_doy", "cos_doy", "doy"]
SPECTRAL = ["evi2", "ndvi", "nirv"]

#: The ladder every run reports. The bool toggles the per-plot dummies.
LADDER: dict[str, tuple[list[str], bool]] = {
    "calendar only":                 (CALENDAR, False),
    "evi2 only":                     (["evi2"], False),
    "ndvi only":                     (["ndvi"], False),
    "spectral only":                 (SPECTRAL, False),
    "spectral + calendar":           (SPECTRAL + CALENDAR, False),
    "plot id + calendar":            (CALENDAR, True),
    "spectral + calendar + plot id": (SPECTRAL + CALENDAR, True),
    "+ sza (rejected)":              (SPECTRAL + CALENDAR + ["sza"], True),
}

#: The configuration S8 ships.
CHOSEN = "spectral + calendar + plot id"


@dataclass
class Design:
    """A feature matrix plus the grouping that makes its score honest."""
    X: np.ndarray
    y: np.ndarray
    groups: np.ndarray
    names: list[str] = field(default_factory=list)


def build(m: pd.DataFrame, cols: list[str], plots: bool, target: str,
          regime: str) -> Design:
    m = m.dropna(subset=cols + [target])
    blocks, names = [m[cols].to_numpy(float)], list(cols)
    if plots:
        d = pd.get_dummies(m["plot"], prefix="plot")
        blocks.append(d.to_numpy(float))
        names += list(d.columns)
    groups = m["campaign_id" if regime == "known_plot" else "plot"].to_numpy()
    return Design(np.hstack(blocks), m[target].to_numpy(float), groups, names)


def cross_validate(d: Design, alpha: float = ALPHA,
                   n_splits: int = N_SPLITS) -> tuple[np.ndarray, dict]:
    """Out-of-fold predictions and their scores. Never refits on the test fold."""
    n_splits = min(n_splits, len(np.unique(d.groups)))
    pred = np.full(len(d.y), np.nan)
    for tr, te in GroupKFold(n_splits).split(d.X, d.y, d.groups):
        pred[te] = Ridge(alpha=alpha).fit(d.X[tr], d.y[tr]).predict(d.X[te])
    resid = d.y - pred
    return pred, {"r2": round(float(r2_score(d.y, pred)), 4),
                  "rmse": round(float(np.sqrt((resid ** 2).mean())), 4),
                  "mae": round(float(np.abs(resid).mean()), 4),
                  "bias": round(float(resid.mean()), 4),
                  "n": int(len(d.y)), "n_groups": int(len(np.unique(d.groups))),
                  "target_sd": round(float(d.y.std()), 4)}


def run_ladder(m: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for target in TARGETS:
        for name, (cols, plots) in LADDER.items():
            for regime in ("known_plot", "new_plot"):
                if plots and regime == "new_plot":
                    continue        # a dummy for an unseen plot is meaningless
                d = build(m, cols, plots, target, regime)
                _, s = cross_validate(d)
                rows.append({"target": target, "features": name, "regime": regime,
                             "plot_dummies": plots, **s})
    return pd.DataFrame(rows)


def season_skill(m: pd.DataFrame, target: str = "lai") -> pd.DataFrame:
    """Where the skill lives, with and without the plot offset.

    Reported because the pooled number hides the failure: the indices saturate
    once the canopy closes, and without plot identity the model has no skill
    there at all.
    """
    bins = [0, 120, 160, 250, 300, 366]
    labels = ["winter", "green-up", "peak", "senescence", "late"]
    rows = []
    for name in ("spectral + calendar", CHOSEN):
        cols, plots = LADDER[name]
        sub = m.dropna(subset=cols + [target]).copy()
        d = build(sub, cols, plots, target, "known_plot")
        pred, _ = cross_validate(d)
        sub["pred"] = pred
        sub["season"] = pd.cut(sub["doy"], bins, labels=labels)
        for s, part in sub.groupby("season", observed=True):
            rows.append({"features": name, "season": str(s), "n": len(part),
                         "r2": round(float(r2_score(part[target], part["pred"])), 4),
                         "rmse": round(float(np.sqrt(((part[target] - part["pred"]) ** 2)
                                                     .mean())), 4),
                         "target_sd": round(float(part[target].std()), 4)})
    return pd.DataFrame(rows)


def fit_final(m: pd.DataFrame, target: str = "lai",
              alpha: float = ALPHA) -> tuple[Ridge, Design]:
    cols, plots = LADDER[CHOSEN]
    d = build(m, cols, plots, target, "known_plot")
    return Ridge(alpha=alpha).fit(d.X, d.y), d


def variance_budget(m: pd.DataFrame, target: str = "lai") -> dict:
    """How the target's variance splits, before any model sees it."""
    y = m[target]
    between_date = m.groupby("date")[target].transform("mean")
    plot_mean = m.groupby("plot")[target].transform("mean")
    tot = float(y.var())
    return {"total": round(tot, 4),
            "between_date_frac": round(float(between_date.var()) / tot, 4),
            "within_date_frac": round(float((y - between_date).var()) / tot, 4),
            "static_plot_frac": round(float(plot_mean.var()) / tot, 4)}


def sza_is_the_calendar(m: pd.DataFrame) -> dict:
    """Regress SZA on a day-of-year harmonic. The reason SZA is not a feature."""
    s = m.dropna(subset=["sza"])
    X = np.c_[s["sin_doy"], s["cos_doy"], np.ones(len(s))]
    beta, *_ = np.linalg.lstsq(X, s["sza"].to_numpy(float), rcond=None)
    resid = s["sza"].to_numpy(float) - X @ beta
    return {"r2": round(1 - float(resid.var()) / float(s["sza"].var()), 4),
            "residual_sd_deg": round(float(resid.std()), 3),
            "sza_range": [round(float(s["sza"].min()), 1),
                          round(float(s["sza"].max()), 1)],
            "vza_max": round(float(m["vza"].max()), 1)}


def run() -> tuple[pd.DataFrame, dict]:
    m = s8data.load_pairs()
    OUT.mkdir(exist_ok=True)

    ladder = run_ladder(m)
    ladder.to_csv(OUT / "cv_results.csv", index=False)
    season_skill(m).to_csv(OUT / "season_skill.csv", index=False)

    cols, plots = LADDER[CHOSEN]
    d = build(m, cols, plots, "lai", "known_plot")
    pred, chosen = cross_validate(d)
    oof = m.dropna(subset=cols + ["lai"])[
        ["date", "plot", "doy", "lai", "pai", "days_apart"] + cols].copy()
    oof["pred_lai"] = pred
    oof["resid"] = oof["lai"] - oof["pred_lai"]
    oof.to_csv(OUT / "oof_predictions.csv", index=False)

    fitted, dd = fit_final(m)
    pd.DataFrame({"term": dd.names, "coef": fitted.coef_}).to_csv(
        OUT / "coefficients.csv", index=False)

    summary = {
        "chosen": CHOSEN, "alpha": ALPHA,
        "target": "lai (= pai - min pai per plot, WP0 lai_subtractive_fx)",
        "n_pairs": int(len(m)), "n_plots": int(m["plot"].nunique()),
        "n_campaigns": int(m["campaign_id"].nunique()),
        "window": [str(m["date"].min().date()), str(m["date"].max().date())],
        "known_plot": chosen,
        "new_plot": cross_validate(
            build(m, SPECTRAL + CALENDAR, False, "lai", "new_plot"))[1],
        "baseline_calendar_only": cross_validate(
            build(m, CALENDAR, False, "lai", "known_plot"))[1],
        "variance_budget": variance_budget(m),
        "sza_vs_calendar": sza_is_the_calendar(m),
        "rmse_by_target": {
            t: cross_validate(build(m, cols, plots, t, "known_plot"))[1]["rmse"]
            for t in TARGETS},
    }
    (OUT / "results_summary.json").write_text(json.dumps(summary, indent=2), "utf8")
    return ladder, summary
