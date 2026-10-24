"""S7 results, and the uncertainty column that goes back onto the S1 product.

The deliverable is not a paper. It is a per-observation uncertainty attached to
``hf365_v2_candidate``, which is what CEOS LPV Stage 3 asks for -- characterised
uncertainty, not better estimates.

Uncertainty is made per-observation by stratifying: TC is run separately within
season x platform strata, and each observation inherits the error estimate of
its stratum. Strata too small to support an estimate are reported rather than
silently filled.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from s1 import io as sio
from s7 import collocate, tc

OUT = collocate.OUT
MIN_BLOCKS = 25          # a stratum needs this many (date, cell) blocks to be trusted
MIN_SIGNAL_VAR_FRAC = 0.5
"""Minimum share of the pooled signal variance a stratum must retain.

The bounds test on rho^2 catches strata that blow up past 1, but not ones that
collapse toward 0 -- ``growing / L30`` returns rho^2 = 0.09 for HLS against a
pooled 0.987, which is the same instability wearing a plausible number. Gating
on signal variance targets the mechanism directly: TC cannot separate error from
signal when the latent quantity barely moves, and the growing season holds only
18 % of the record's variance in plant area index.
"""


def _season(doy: pd.Series) -> pd.Series:
    return np.where(doy.between(150, 250), "growing", "off")


def stratified(t: pd.DataFrame) -> pd.DataFrame:
    t = t.copy()
    t["season"] = _season(t["doy"])
    pooled_var = float(t["pai"].var())
    rows = []
    # stratify on `product` (L30/S30), which is what hf365_v2_candidate carries;
    # `platform` (L8/L9/S2A...) would never match the lookup key
    for keys, g in list(t.groupby(["season"])) + list(t.groupby(["product"])) \
            + list(t.groupby(["season", "product"])):
        key = keys if isinstance(keys, tuple) else (keys,)
        nb = g.groupby(["ground_date", "appeears_pixel"]).ngroups
        r = tc.classical(g["pai"], g["hls"], g["modis_lai"])
        # A stratum is only trusted if every correlation-with-truth is a real
        # correlation. rho^2 outside (0,1) means the estimator has broken, not
        # that the system is unusually good or bad.
        rho_ok = bool(r) and all(0.0 < r[f"rho2_truth_{n}"] < 1.0 for n in tc.NAMES)
        var_frac = float(g["pai"].var()) / pooled_var
        var_ok = var_frac >= MIN_SIGNAL_VAR_FRAC
        why = ("" if rho_ok and var_ok else
               "rho2 outside (0,1)" if not rho_ok else
               f"retains only {100 * var_frac:.0f} % of the pooled signal variance")
        rows.append({
            "stratum": " / ".join(str(k) for k in key),
            "n_rows": len(g), "n_blocks": nb,
            "signal_var_pai": float(g["pai"].var()),
            "signal_var_frac": var_frac,
            "trusted": bool(nb >= MIN_BLOCKS and r and not r["negative_variance"]
                            and rho_ok and var_ok),
            "why_not": why,
            **({k: r[k] for k in r if k.startswith(("sd_err_", "rho2_truth_"))} if r else {}),
        })
    return pd.DataFrame(rows)


def attach_uncertainty(strata: pd.DataFrame, pooled_sd: float,
                       pooled_ci: list[float]) -> pd.DataFrame:
    """Write the TC error estimate onto every usable row of hf365_v2_candidate.

    Conditional (per-season, per-product) uncertainty is **not** supported by
    this data: every within-season stratum returns a correlation-with-truth
    outside (0, 1), because the growing season holds only 18 % of the record's
    signal variance and the shoulder seasons change fast enough that a +-4 day
    match is itself a source of disagreement. TC needs the latent quantity to
    vary, and within a season it does not.

    So the column carries the pooled estimate, and says so. Where a stratum does
    survive the validity test it is used in preference.
    """
    v2 = pd.read_csv(sio.OUT / "hf365_v2_candidate.csv")
    v2["season"] = _season(pd.to_datetime(v2["date"]).dt.dayofyear)

    good = strata[strata["trusted"]]
    combo = {s: v for s, v in zip(good["stratum"], good["sd_err_hls"]) if "/" in s}
    product_lut = {s: v for s, v in zip(good["stratum"], good["sd_err_hls"])
                   if s in ("L30", "S30")}
    season_lut = {s: v for s, v in zip(good["stratum"], good["sd_err_hls"])
                  if s in ("growing", "off")}

    # season x product is the finest split, but none of those survive the
    # validity gate; per-product does, and it is a real refinement -- the two
    # streams do not carry the same error.
    key = v2["season"] + " / " + v2["product"]
    by_combo = key.map(combo)
    by_product = v2["product"].map(product_lut)
    by_season = v2["season"].map(season_lut)

    v2["evi2_sd_tc"] = by_combo.fillna(by_product).fillna(by_season).fillna(pooled_sd)
    v2["evi2_sd_tc_source"] = np.where(
        by_combo.notna(), "season_x_product",
        np.where(by_product.notna(), "product",
                 np.where(by_season.notna(), "season", "pooled")))

    v2["evi2_sd_tc_ci_lo"], v2["evi2_sd_tc_ci_hi"] = pooled_ci
    v2.loc[~v2["single_usable"],
           ["evi2_sd_tc", "evi2_sd_tc_ci_lo", "evi2_sd_tc_ci_hi"]] = np.nan
    v2.loc[~v2["single_usable"], "evi2_sd_tc_source"] = ""
    sio.write(v2, "hf365_v2_candidate.csv")
    return v2


def run(measure: str = "evi2") -> dict:
    t, cstats = collocate.run(measure)
    t["ground_date"] = pd.to_datetime(t["ground_date"])
    lin = tc.linearity(t)
    base = tc.classical(t["pai"], t["hls"], t["modis_lai"])
    boot = tc.block_bootstrap(t, n_boot=2000)
    sens = tc.sensitivity(t)
    strata = stratified(t)

    # where does the sensitivity sweep become physically impossible?
    bad = sens[(sens["rho2_truth_ground"] > 1) | (sens["rho2_truth_ground"].isna())]
    bound = float(bad["assumed_err_corr_frac"].min()) if len(bad) else float("nan")

    lin.to_csv(OUT / "linearity.csv", index=False)
    sens.to_csv(OUT / "sensitivity_correlated_errors.csv", index=False)
    strata.to_csv(OUT / "tc_by_stratum.csv", index=False)
    boot.describe().to_csv(OUT / "bootstrap_describe.csv")

    pooled_ci = [float(boot["sd_err_hls"].quantile(.025)),
                 float(boot["sd_err_hls"].quantile(.975))]
    v2 = attach_uncertainty(strata, float(base["sd_err_hls"]), pooled_ci)

    res = {
        "collocation": cstats,
        "effective_n": tc.effective_n(t),
        "linearity": {r["pair"]: {"quadratic_p": round(r["quadratic_p"], 6),
                                  "curvature_reduces_ss_pct": round(
                                      r["curvature_reduces_ss_pct"], 4)}
                      for _, r in lin.iterrows()},
        "classical": {k: round(v, 5) for k, v in base.items()
                      if isinstance(v, float)},
        "bootstrap_95ci": {
            n: [round(float(boot[f"sd_err_{n}"].quantile(.025)), 5),
                round(float(boot[f"sd_err_{n}"].quantile(.975)), 5)]
            for n in tc.NAMES},
        "correlated_error_bound": {
            "impossible_at_frac": bound,
            "reading": "assuming the two satellite streams share more than this "
                       "fraction of their covariance as error drives the ground "
                       "correlation-with-truth above 1, which cannot happen -- so "
                       "the true error correlation is below it"},
        "uncertainty_column": {
            "column": "evi2_sd_tc",
            "n_rows_filled": int(v2["evi2_sd_tc"].notna().sum()),
            "by_source": v2["evi2_sd_tc_source"].value_counts().to_dict(),
        },
        "caveat": "No novelty is claimed. TC on LAI/fAPAR, correlated-error TC "
                  "(CTC/EQC) and representativeness-error decomposition are all "
                  "published; this applies them.",
    }
    (OUT / "results_summary.json").write_text(json.dumps(res, indent=2, default=str),
                                              encoding="utf8")
    return res
