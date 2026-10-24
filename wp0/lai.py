"""HF069-01 plot LAI: roster cleaning, campaign structure, and the PAI/LAI variants.

Three hazards in this file, all confirmed against the raw data:

  * **the roster is dirty.** 55 distinct ``plot`` labels, of which only 46 are
    EMS plots. The rest are ``1``, ``A1CAM``, ``BOG``, ``PAR``, ``RO``,
    ``RO TOWE`` (truncated), ``TS1``, ``TS2``, ``VAN``. They are rejected
    against the hf375-02 roster and written out rather than silently dropped.
  * **103 duplicate (date, plot) rows.** These are real repeat measurements, not
    a parsing artefact, and averaging them away inflates n and distorts any
    within-plot variance. They are collapsed to one row carrying ``n_reps`` and
    ``lai_sd``.
  * **the column is named ``lai`` but holds PAI.** hf069.xml is explicit: "The
    data reported in this file is of plant area index (PAI), and has not been
    corrected for woody material."

The woody correction is shipped as **variants, not as a decision.** The paper's
printed equations are ``Wf = (P - Pmin)/Pmax`` and ``LAI = P(1 - Wf)``, which
return ``LAI = Pmin`` at both ``P = Pmin`` and ``P = Pmax`` and give ``Wf = 0``
at leaf-off when the plant area is entirely woody -- both wrong. The likely
intent is ``Wf = Pmin/P``, giving ``LAI = P - Pmin``. WP0 cannot resolve which
was meant without the published version, so it emits both, under both extrema
scopes, and lets each downstream study state which series it rests on. S5's Arm
A specifically needs the raw PAI series alongside the corrected one, because a
per-plot-year correction is year-relative and partially normalises away the
between-year anomalies that study hunts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from wp0 import io

CAMPAIGN_GAP_DAYS = 3      # dates closer than this belong to one field campaign
INSTRUMENT_CHANGE_YEAR = 2015   # LAI-2000 -> LAI-2200, hf069.xml
PEAK_DOY = (180, 230)


def valid_plots() -> set[str]:
    plots = io.read_raw("hf375_plots")
    ems = plots[plots["NAME"].astype("string").str.startswith("EMS ", na=False)]
    return set(ems["NAME"].str.removeprefix("EMS ").str.strip())


def load(collapse_reps: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (clean long frame, rejected-label report)."""
    raw = io.read_raw("hf069_plot")
    raw["plot"] = raw["plot"].astype("string").str.strip()

    keep = valid_plots()
    mask = raw["plot"].isin(keep)
    rejects = (raw.loc[~mask].groupby("plot", dropna=False)
               .agg(n_rows=("lai", "size"),
                    first_date=("date", "min"), last_date=("date", "max"))
               .reset_index()
               .rename(columns={"plot": "rejected_label"}))
    df = raw.loc[mask].copy()

    df["date"] = pd.to_datetime(df["date"])
    df = df.rename(columns={"lai": "pai"})          # hf069.xml: this column is PAI

    # Campaign identity, so downstream interpolation never averages across two
    # visits that happen to fall in the same window.
    dates = pd.Index(sorted(df["date"].unique()))
    gap = dates.to_series().diff().dt.days.fillna(9999)
    camp = (gap > CAMPAIGN_GAP_DAYS).cumsum()
    df["campaign_id"] = df["date"].map(dict(zip(dates, camp)))

    df["n_reps"] = df.groupby(["date", "plot"])["pai"].transform("size")
    if collapse_reps:
        df = (df.groupby(["date", "plot"], as_index=False)
              .agg(pai=("pai", "mean"), pai_sd=("pai", "std"),
                   se=("se", "mean"), n_reps=("n_reps", "first"),
                   campaign_id=("campaign_id", "first"),
                   year=("year", "first"), doy=("doy", "first")))
    df["instrument"] = np.where(df["year"] >= INSTRUMENT_CHANGE_YEAR,
                                "LAI-2200", "LAI-2000")
    return df.sort_values(["date", "plot"], ignore_index=True), rejects


def _extrema(df: pd.DataFrame, scope: str) -> tuple[pd.Series, pd.Series]:
    keys = ["plot", "year"] if scope == "per_plot_year" else ["plot"]
    g = df.groupby(keys)["pai"]
    return g.transform("min"), g.transform("max")


def add_woody_variants(df: pd.DataFrame) -> pd.DataFrame:
    """Both equation readings x both extrema scopes, as explicit columns."""
    out = df.copy()
    for scope in ("per_plot_year", "fixed"):
        pmin, pmax = _extrema(out, scope)
        tag = "py" if scope == "per_plot_year" else "fx"
        # printed form, reproduced faithfully including its known pathology
        wf = (out["pai"] - pmin) / pmax.replace(0, np.nan)
        out[f"lai_printed_{tag}"] = out["pai"] * (1.0 - wf)
        # subtractive form, the likely intent
        out[f"lai_subtractive_{tag}"] = out["pai"] - pmin
    return out


def instrument_step_test(df: pd.DataFrame) -> dict:
    """Paired test for a LAI-2000 -> LAI-2200 step, blocked by plot.

    hf069.xml already says "comparisons between the two sensors showed
    consistent agreement", but gives no numbers, so this quantifies it rather
    than raising it with the authors as an open question.
    """
    peak = df[df["doy"].between(*PEAK_DOY)]
    pre = (peak[peak["year"].between(INSTRUMENT_CHANGE_YEAR - 5, INSTRUMENT_CHANGE_YEAR - 1)]
           .groupby("plot")["pai"].mean())
    post = (peak[peak["year"].between(INSTRUMENT_CHANGE_YEAR, INSTRUMENT_CHANGE_YEAR + 4)]
            .groupby("plot")["pai"].mean())
    both = pd.concat([pre.rename("pre"), post.rename("post")], axis=1).dropna()
    if len(both) < 5:
        return {"n_plots": len(both), "verdict": "insufficient overlap"}
    d = both["post"] - both["pre"]
    t, p = stats.ttest_rel(both["post"], both["pre"])
    w, pw = stats.wilcoxon(both["post"], both["pre"])
    return {
        "n_plots": int(len(both)),
        "window_pre": f"{INSTRUMENT_CHANGE_YEAR - 5}-{INSTRUMENT_CHANGE_YEAR - 1}",
        "window_post": f"{INSTRUMENT_CHANGE_YEAR}-{INSTRUMENT_CHANGE_YEAR + 4}",
        "mean_step_pai": float(d.mean()),
        "median_step_pai": float(d.median()),
        "sd_step_pai": float(d.std()),
        "t_stat": float(t), "p_paired_t": float(p),
        "p_wilcoxon": float(pw),
        "verdict": ("no detectable step" if p > 0.05 else
                    "step detected -- do not span the transition untreated"),
    }


def run() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    df, rejects = load()
    df = add_woody_variants(df)
    step = instrument_step_test(df)

    io.write(df, "hf069_plot_clean.csv")
    io.write(rejects, "hf069_roster_rejects.csv")
    io.record(
        stage="LAI",
        inputs=["hf069_plot", "hf375_plots", "eml_hf069"],
        params={"campaign_gap_days": CAMPAIGN_GAP_DAYS,
                "instrument_change_year": INSTRUMENT_CHANGE_YEAR,
                "peak_doy": list(PEAK_DOY),
                "woody_variants": ["printed", "subtractive"],
                "extrema_scopes": ["per_plot_year", "fixed"]},
        outputs=["hf069_plot_clean.csv", "hf069_roster_rejects.csv"],
        notes=f"Column renamed lai->pai per hf069.xml. Instrument step: {step['verdict']}.",
    )
    return df, rejects, step
