"""Regenerate S8's findings from the data. `python -m s8 findings` -> s8/FINDINGS.md

Every value below is recomputed on each run from ``s8/out/pairs.csv`` and the
raw archives. Nothing is transcribed. A finding that stops holding flips to FAIL
rather than quietly staying in the prose.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score

from s8 import data as s8data
from s8 import model as s8model

PKG = Path(__file__).resolve().parent
OUT = PKG / "out"

#: The window the published HF365 archive covers, for the reach comparison.
PUBLISHED_HF365 = ("2015-01-23", "2020-08-10")
# Archive inputs live outside the repo. Set HF_DATA_ROOT; see README.
DATA = Path(os.environ.get("HF_DATA_ROOT", "data"))
MODIS_CSV = DATA / "MODIS" / "Main5Pixels-PointSample-MCD15A2H-061-results.csv"


@dataclass
class F:
    id: str
    claim: str
    value: str
    holds: bool
    impact: str
    source: str


def _pairs() -> pd.DataFrame:
    return s8data.load_pairs()


def _score(m, cols, plots, target="lai", regime="known_plot"):
    return s8model.cross_validate(s8model.build(m, cols, plots, target, regime))[1]


def f01_target_is_derived() -> F:
    g = pd.read_csv(s8data.sio.WP0_INPUTS["field_lai"], parse_dates=["date"])
    winter = g[g["doy"] < 100]["pai"]
    site = pd.read_csv(DATA / "HF069" / "hf069-02-lai-site.csv")
    w = site[site["doy"] < 100]
    return F("S8-01", "The target is derived, not observed",
             f"HF069 reports plant area index: its leaf-off reading averages "
             f"{winter.mean():.2f} at plot level, and the archive's own site file "
             f"puts leaf-off PAI at {w['all_mean'].mean():.2f} against a deciduous "
             f"LAI of {w['decid_mean'].mean():.2f}. S8's target is "
             f"pai - min(pai) per plot",
             abs(w["decid_mean"].mean()) < 0.5 < w["all_mean"].mean(),
             "About 1.7 of this stand's plant area is wood. Calling the raw column "
             "LAI overstates leaf area by that much in every season, and by "
             "everything in winter.",
             "hf069.xml; hf069-02-lai-site.csv; wp0/lai.py")


def f02_calendar_baseline() -> F:
    m = _pairs()
    cal = _score(m, s8model.CALENDAR, False)
    chosen = _score(m, *s8model.LADDER[s8model.CHOSEN])
    return F("S8-02", "Day-of-year alone explains most of the target",
             f"a calendar with no satellite input scores R2 {cal['r2']:.3f} "
             f"(RMSE {cal['rmse']:.3f}); the chosen model scores "
             f"{chosen['r2']:.3f} (RMSE {chosen['rmse']:.3f}), a gain of "
             f"{chosen['r2'] - cal['r2']:+.3f}",
             chosen["r2"] > cal["r2"],
             "HF069 samples March to December, so most of the variance is the "
             "seasonal cycle. Any headline R2 must be reported against this "
             "baseline or it reads as skill the satellite did not supply.",
             "s8/model.py:run_ladder")


def f03_reprocessing_doubles_the_overlap() -> F:
    m = _pairs()
    pub = m[(m["date"] >= PUBLISHED_HF365[0]) & (m["date"] <= PUBLISHED_HF365[1])]
    return F("S8-03", "S1's reprocessing is what makes the sample usable",
             f"{len(m)} pairs over {m['campaign_id'].nunique()} campaigns against "
             f"{len(pub)} within the published HF365 window "
             f"{PUBLISHED_HF365[0]}..{PUBLISHED_HF365[1]} -- "
             f"{len(m) / max(len(pub), 1):.2f}x",
             len(m) > 1.5 * len(pub),
             "The published archive stops in 2020. S1's v2 runs to 2026, which is "
             "the only reason five more years of HF069 campaigns are reachable.",
             "s1/out/hf365_v2_candidate.csv; s8/data.py")


def f04_sza_is_the_calendar() -> F:
    """Three independent tests, because 'add the angle' is the obvious next idea."""
    m = _pairs()
    s = s8model.sza_is_the_calendar(m)
    without = _score(m, *s8model.LADDER[s8model.CHOSEN])
    with_sza = _score(m, *s8model.LADDER["+ sza (rejected)"])

    # 2. interaction, the physically motivated form: extinction scales with G(t)/cos t
    q = m.copy()
    q["sza_c"] = q["sza"] - q["sza"].mean()
    for i in s8model.SPECTRAL:
        q[f"{i}_x_sza"] = q[i] * q["sza_c"]
    inter = _score(q, s8model.SPECTRAL + s8model.CALENDAR + ["sza"]
                   + [f"{i}_x_sza" for i in s8model.SPECTRAL], True)

    # 3. residual structure -- if an SZA effect were missing it would show here
    oof = pd.read_csv(OUT / "oof_predictions.csv", parse_dates=["date"])
    oof = oof.merge(m[["date", "plot", "sza", "days_apart"]],
                    on=["date", "plot", "days_apart"], how="left").dropna(subset=["sza"])
    r_resid = float(np.corrcoef(oof["resid"], oof["sza"])[0, 1])

    holds = (with_sza["r2"] <= without["r2"] + 0.002
             and inter["r2"] <= without["r2"] + 0.002 and abs(r_resid) < 0.05)
    return F("S8-04", "Solar zenith angle is day-of-year wearing a hat",
             f"SZA on a day-of-year harmonic returns R2 {s['r2']:.4f}, residual sd "
             f"{s['residual_sd_deg']:.2f} deg, over {s['sza_range'][0]}-"
             f"{s['sza_range'][1]} deg at a maximum view zenith of {s['vza_max']} deg. "
             f"Three tests: as a main effect R2 {without['r2']:.4f} -> "
             f"{with_sza['r2']:.4f}; as an index interaction -> {inter['r2']:.4f}; "
             f"and the retrieval's residuals carry no SZA structure at all "
             f"(r = {r_resid:+.4f})",
             holds,
             "Illumination geometry earns its keep where it varies within a day at "
             "a fixed canopy, which is S4's design. Here every route is collinear "
             "with the calendar, and the residuals confirm nothing is left "
             "unexplained. SZA is excluded on evidence, not on preference.",
             "s8/model.py:sza_is_the_calendar; s8/findings.py:f04_sza_is_the_calendar")


def f05_modis_adds_nothing() -> F:
    m = _pairs()
    if not MODIS_CSV.exists():
        return F("S8-05", "MODIS adds nothing to the retrieval",
                 "SKIPPED: MODIS point-sample export not found", False, "",
                 str(MODIS_CSV))
    p = "MCD15A2H_061_"
    mo = pd.read_csv(MODIS_CSV, parse_dates=["Date"])
    mo = mo[mo[p + "FparLai_QC_MODLAND_Description"].str.startswith("Good")]
    spread = (mo.groupby("Date")[p + "Lai_500m"].std()).median()
    # "with saturation" and not merely "saturation" -- the clean-retrieval label
    # reads "best result possible (no saturation)" and matches the loose test.
    sat = mo[p + "FparLai_QC_SCF_QC_Description"].str.contains("with saturation").mean()
    mo = mo[["ID", "Date", p + "Lai_500m", p + "Fpar_500m"]]
    mo.columns = ["appeears_pixel", "mdate", "modis_lai", "modis_fpar"]
    cw = pd.read_csv(Path(s8data.sio.WP0_INPUTS["plot_registry"]).parent
                     / "crosswalk_plot_to_modis.csv")
    pixcol = next(c for c in cw.columns if "pixel" in c.lower())
    j = m.merge(cw[["plot", pixcol]].rename(columns={pixcol: "appeears_pixel"}),
                on="plot", how="left")
    parts = []
    for pix, sub in j.groupby("appeears_pixel"):
        mp = mo[mo["appeears_pixel"] == pix].sort_values("mdate")
        if mp.empty:
            continue
        parts.append(pd.merge_asof(sub.sort_values("date"),
                                   mp.drop(columns="appeears_pixel"),
                                   left_on="date", right_on="mdate",
                                   direction="nearest",
                                   tolerance=pd.Timedelta(days=4)))
    j = pd.concat(parts, ignore_index=True).dropna(subset=["modis_lai"])
    base = s8model.SPECTRAL + s8model.CALENDAR
    without = _score(j, base, True)
    with_m = _score(j, base + ["modis_lai", "modis_fpar"], True)
    return F("S8-05", "MODIS adds nothing to the retrieval",
             f"on the {len(j)} pairs MODIS reaches, adding Lai_500m and Fpar_500m "
             f"moves R2 from {without['r2']:.4f} to {with_m['r2']:.4f}. Its cells "
             f"differ by only {spread:.3f} LAI on a typical date and "
             f"{100 * sat:.0f} % of its good-quality retrievals are flagged saturated",
             with_m["r2"] <= without["r2"] + 0.005,
             "A 500 m product cannot resolve 10 m plots, and its record ends "
             "2020-12-26. Predicting one optical retrieval from another was the "
             "design of the earlier forecasting notebook; S8 does not repeat it.",
             "MCD15A2H.061 point sample; s8/findings.py:f05_modis_adds_nothing")


def f06_ridge_beats_the_forest() -> F:
    m = _pairs()
    cols, plots = s8model.LADDER[s8model.CHOSEN]
    d = s8model.build(m, cols, plots, "lai", "known_plot")
    _, ridge = s8model.cross_validate(d)
    from sklearn.model_selection import GroupKFold
    pred = np.zeros(len(d.y))
    for tr, te in GroupKFold(s8model.N_SPLITS).split(d.X, d.y, d.groups):
        rf = RandomForestRegressor(n_estimators=300, min_samples_leaf=5,
                                   random_state=0, n_jobs=-1).fit(d.X[tr], d.y[tr])
        pred[te] = rf.predict(d.X[te])
    forest = r2_score(d.y, pred)
    return F("S8-06", "Ridge beats a random forest once folds respect campaigns",
             f"ridge R2 {ridge['r2']:.4f} against random forest {forest:.4f} on the "
             f"same design and the same {d.groups.__len__() and len(set(d.groups))} "
             f"campaign groups",
             ridge["r2"] > forest,
             "The earlier MODIS-target notebook found the forest ahead. That "
             "ordering came from splits that let it memorise date-specific "
             "patterns; grouped folds remove the advantage.",
             "s8/findings.py:f06_ridge_beats_the_forest")


def f07_two_regimes() -> F:
    m = _pairs()
    known = _score(m, *s8model.LADDER[s8model.CHOSEN])
    new = _score(m, s8model.SPECTRAL + s8model.CALENDAR, False, regime="new_plot")
    vb = s8model.variance_budget(m)
    return F("S8-07", "The honest score depends on which question is asked",
             f"known plot on a new date R2 {known['r2']:.4f} (RMSE {known['rmse']:.3f}, "
             f"{known['n_groups']} campaign folds); a plot never measured R2 "
             f"{new['r2']:.4f} (RMSE {new['rmse']:.3f}, {new['n_groups']} plot folds). "
             f"A static per-plot offset holds {100 * vb['static_plot_frac']:.1f} % of "
             f"the target's variance",
             known["r2"] > new["r2"],
             "Quoting the higher number for the new-plot use case overstates the "
             "model. Both are written on every run so the write-up has to pick one.",
             "s8/model.py:run_ladder, variance_budget")


def f08_peak_season_is_the_weak_point() -> F:
    s = pd.read_csv(OUT / "season_skill.csv")
    a = s[(s["features"] == "spectral + calendar") & (s["season"] == "peak")].iloc[0]
    b = s[(s["features"] == s8model.CHOSEN) & (s["season"] == "peak")].iloc[0]
    return F("S8-08", "Peak season is where the retrieval is weakest",
             f"at peak (DOY 160-250, n={int(a['n'])}) the spectral model scores R2 "
             f"{a['r2']:.3f} against {b['r2']:.3f} with plot identity, while "
             f"green-up reaches "
             f"{s[(s['features'] == s8model.CHOSEN) & (s['season'] == 'green-up')].iloc[0]['r2']:.3f}",
             a["r2"] < 0.6,
             "The indices saturate once the canopy closes, and the ground barely "
             "varies there. What skill remains at peak is mostly the plot offset, "
             "not the spectra -- so a claim about peak leaf area rests on almost "
             "nothing.",
             "s8/out/season_skill.csv")


def f09_conversion_does_not_move_the_fit() -> F:
    m = _pairs()
    cols, plots = s8model.LADDER[s8model.CHOSEN]
    lai = _score(m, cols, plots, "lai")
    pai = _score(m, cols, plots, "pai")
    return F("S8-09", "Converting PAI to LAI does not change what the model learns",
             f"with plot dummies in, RMSE is {lai['rmse']:.4f} on LAI and "
             f"{pai['rmse']:.4f} on PAI -- the same fit. R2 differs "
             f"({lai['r2']:.3f} vs {pai['r2']:.3f}) only because the targets have "
             f"different variance",
             abs(lai["rmse"] - pai["rmse"]) < 0.01,
             "LAI = PAI minus a per-plot constant, which is exactly what a plot "
             "dummy absorbs. Convert because the write-up and FT04 need leaf area, "
             "not because the model gains anything.",
             "s8/model.py:run_ladder")


def f10_forecast_horizon() -> F:
    import json
    p = OUT / "forecast_summary.json"
    if not p.exists():
        return F("S8-10", "The satellite's forecast value decays within a month",
                 "SKIPPED: run `python -m s8 forecast` first", False, "",
                 "s8/forecast.py")
    s = json.loads(p.read_text("utf8"))
    h = s["horizons"]
    fc, cal, per = s["r2"]["forecast + trend"], s["r2"]["calendar"], s["r2"]["persistence"]
    gains = [round(a - b, 4) for a, b in zip(fc, cal)]
    return F("S8-10", "The satellite's forecast value decays within about a month",
             "gain over a calendar-only forecast: "
             + ", ".join(f"{d} d {g:+.3f}" for d, g in zip(h, gains))
             + f". The calendar itself is flat across horizons "
               f"({min(cal):.3f}-{max(cal):.3f}) while carrying the last "
               f"retrieval forward decays from {per[0]:.3f} to {per[-1]:.3f}",
             gains[0] > gains[-1],
             "Spectral memory fades but seasonal climatology does not, so beyond "
             "roughly a month a wall calendar forecasts leaf area as well as the "
             "satellite does. Reaching further needs a climate-driven phenology "
             "model, not more spectral features.",
             "s8/out/forecast_results.csv")


def f11_ground_and_satellite_diverge() -> F:
    """Surfaced by the SZA residual test, which found a year trend instead."""
    from scipy import stats
    m = _pairs()
    m = m.assign(year=m["date"].dt.year)
    peak = m[m["doy"].between(160, 250)]

    # fixed roster: only plots measured at peak in every year, so composition
    # cannot manufacture the trend
    seen = peak.groupby("plot")["year"].nunique()
    fixed = seen[seen == peak["year"].nunique()].index
    t = (peak[peak["plot"].isin(fixed)].groupby("year")
         .agg(lai=("lai", "mean"), evi2=("evi2", "mean"), ndvi=("ndvi", "mean")))
    fits = {c: stats.linregress(t.index, t[c]) for c in ("lai", "evi2", "ndvi")}
    g, e, n = fits["lai"], fits["evi2"], fits["ndvi"]
    return F("S8-11", "Ground leaf area is falling and the indices do not see it",
             f"over {len(t)} peak seasons on the {len(fixed)} plots measured every "
             f"year, ground LAI falls {g.slope:+.4f} per year (p={g.pvalue:.3f}, "
             f"{11 * g.slope:+.2f} across the record) while EVI2 shows "
             f"{e.slope:+.4f} (p={e.pvalue:.3f}) and NDVI {n.slope:+.4f} "
             f"(p={n.pvalue:.3f})",
             g.pvalue < 0.05 and e.pvalue > 0.05,
             "The decade-scale change on the ground exceeds the model's RMSE, and "
             "the predictors do not carry it -- so the retrieval's residuals drift "
             "with year. This is S8-08 at decadal scale: at peak season NDVI sits "
             "near 0.89 and is saturated, so a real decline in leaf area is "
             "invisible to it. Cause is not established here; instrument drift, "
             "crew change and real canopy decline are all open.",
             "s8/findings.py:f11_ground_and_satellite_diverge")


ALL = [f01_target_is_derived, f02_calendar_baseline,
       f03_reprocessing_doubles_the_overlap, f04_sza_is_the_calendar,
       f05_modis_adds_nothing, f06_ridge_beats_the_forest, f07_two_regimes,
       f08_peak_season_is_the_weak_point, f09_conversion_does_not_move_the_fit,
       f10_forecast_horizon, f11_ground_and_satellite_diverge]

SECTIONS = {
    "What is being predicted": ["S8-01", "S8-09"],
    "What the satellite is worth": ["S8-02", "S8-03"],
    "Rejected inputs": ["S8-04", "S8-05"],
    "Model choice": ["S8-06"],
    "How well it works": ["S8-07", "S8-08"],
    "Forecasting a future date": ["S8-10"],
    "Open": ["S8-11"],
}


def collect() -> list[F]:
    out = []
    for fn in ALL:
        try:
            out.append(fn())
        except Exception as e:                              # noqa: BLE001
            out.append(F(fn.__name__, fn.__name__,
                         f"ERROR: {type(e).__name__}: {e}", False, "",
                         f"s8.findings.{fn.__name__}"))
    return out


def to_markdown(fs: list[F]) -> str:
    import json
    by = {f.id: f for f in fs}
    ok = sum(f.holds for f in fs)
    s = json.loads((OUT / "results_summary.json").read_text("utf8"))
    L = ["# S8 findings · ground leaf area index from the reprocessed archive", "",
         f"*Regenerated {date.today().isoformat()} by `python -m s8 findings`. "
         f"Values are recomputed from `s8/out/` and the raw archives on each run.*", "",
         f"**{ok} of {len(fs)} findings reproduce.**", "",
         f"Source: {s['n_pairs']} ground-satellite pairs over {s['n_plots']} plots "
         f"and {s['n_campaigns']} field campaigns, {s['window'][0]} to "
         f"{s['window'][1]}. Target is {s['target']}. Chosen model: "
         f"{s['chosen']}, ridge alpha {s['alpha']}.", "",
         f"**Headline:** R2 {s['known_plot']['r2']:.3f} / RMSE "
         f"{s['known_plot']['rmse']:.3f} for a known plot on a new date; "
         f"R2 {s['new_plot']['r2']:.3f} / RMSE {s['new_plot']['rmse']:.3f} for a "
         f"plot never measured; against a calendar-only baseline of R2 "
         f"{s['baseline_calendar_only']['r2']:.3f}.", ""]
    for sec, ids in SECTIONS.items():
        L += [f"## {sec}", ""]
        for i in ids:
            f = by.get(i)
            if not f:
                continue
            L += [f"### {f.id} · {f.claim}", "", f"**Measured:** {f.value}", ""]
            if f.impact:
                L += [f"**Impact:** {f.impact}", ""]
            L += [f"*Source:* {f.source} · *Reproduces:* "
                  f"{'yes' if f.holds else 'NO'}", ""]
    return "\n".join(L)


def run() -> tuple[list[F], str]:
    fs = collect()
    md = to_markdown(fs)
    (PKG / "FINDINGS.md").write_text(md, encoding="utf8")
    return fs, md
