"""S1 results: the three questions the study exists to answer.

1. **Which pixel-assignment convention tracks the ground better?** The archive
   uses the single containing pixel; WP0's crosswalk makes an area-weighted
   value possible. Field PAI decides.
2. **What changed between HLS v1.4 and v2.0, and in which band?** v1.4 is
   unobtainable, so the comparison runs against WP0's recovered reflectance,
   with its reconstruction noise floor drawn alongside.
3. **Are the shipped angle bands trustworthy?** Checked against WP0's
   independent pvlib solar geometry.

Everything writes to ``s1/out`` so the notebook only reads, never recomputes.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from s1 import compare, io as sio, validate

GROWING_DOY = (150, 250)


def _active_plots() -> set[str]:
    reg = sio.read_wp0("plot_registry")
    return set(reg.loc[reg["status"] == "active_tower", "plot"])


def run() -> dict:
    v20 = pd.read_csv(sio.OUT / "hf365_v2_candidate.csv")
    pix = pd.read_csv(sio.OUT / "hls_v2_pixels.csv")
    v14 = compare.load_v14()
    out: dict = {}

    # --- 1. assignment convention -------------------------------------------
    act = v20[v20["plot"].isin(_active_plots())]
    conv = pd.concat([validate.compare_conventions(act, measure=m, series="pai")
                      for m in ("ndvi", "evi2", "nirv")], ignore_index=True)
    band = validate.convention_by_overlap(act, "ndvi", "pai")
    sio.write(conv, "result_convention_vs_fieldlai.csv")
    sio.write(band, "result_convention_by_overlap.csv")
    ndvi = conv[conv["measure"] == "ndvi"]
    out["convention"] = {
        "winner": str(ndvi["winner"].iloc[0]) if "winner" in ndvi else None,
        "margin_r": float(ndvi["margin_r"].iloc[0]) if "margin_r" in ndvi else None,
        "r_single": float(ndvi.loc[ndvi["convention"] == "single", "pearson_r"].iloc[0]),
        "r_weighted": float(ndvi.loc[ndvi["convention"] == "weighted", "pearson_r"].iloc[0]),
        "worst_band_delta": float(band["r_weighted_minus_single"].abs().max()),
    }

    # --- 2. v1.4 vs v2.0 ----------------------------------------------------
    att = compare.attribute(compare.join(v14, v20, "intersection", "single"), "single")
    att["season"] = np.where(
        pd.to_datetime(att["date"]).dt.dayofyear.between(*GROWING_DOY),
        "growing", "off")
    att["rel_nir"] = att["d_nir"] / att["nir_v14"]
    att["rel_red"] = att["d_red"] / att["red_v14"]
    sio.write(att, "result_v14_vs_v20.csv")
    strat = (att.groupby(["product", "season"])
             .agg(n=("d_nir", "size"), d_nir=("d_nir", "median"),
                  d_red=("d_red", "median"), rel_nir=("rel_nir", "median"))
             .reset_index())
    sio.write(strat, "result_v14_vs_v20_stratified.csv")
    s = compare.summarise(att)
    out["v14_vs_v20"] = {
        **{k: s[k] for k in ("n_observations", "n_dates", "median_d_nir",
                             "median_d_red", "median_abs_d_nir", "median_abs_d_red",
                             "reconstruction_floor_nir", "reconstruction_floor_red",
                             "dominant_channel")},
        "rel_nir_median": float(att["rel_nir"].median()),
        "rel_red_median": float(att["rel_red"].median()),
        "growing_d_nir": float(att.loc[att["season"] == "growing", "d_nir"].median()),
        "off_d_nir": float(att.loc[att["season"] == "off", "d_nir"].median()),
        "frac_d_nir_positive": float((att["d_nir"] > 0).mean()),
    }
    ds = compare.date_sets(v14, v20)
    sio.write(ds, "result_date_sets.csv")
    out["coverage"] = compare.coverage_gain(ds)

    # --- 3. angle bands -----------------------------------------------------
    sza = validate.check_sza(pix)
    summ = validate.sza_summary(sza)
    sio.write(sza[["date", "product", "platform", "sza", "sza_pvlib",
                   "sza_residual", "angle_provenance"]], "result_sza_check.csv")
    sio.write(summ, "result_sza_summary.csv")
    out["sza"] = {
        "n": int(sza["sza_residual"].notna().sum()),
        "median_residual_deg": float(sza["sza_residual"].median()),
        "by_product": {r["product"]: round(float(r["median"]), 4)
                       for _, r in summ.iterrows()},
        "frac_over_1deg": float((sza["sza_residual"].abs() > 1).mean()),
    }

    # --- spatial homogeneity: why the convention does not matter -------------
    cw = sio.read_wp0("crosswalk_hls")
    g = cw[cw["plot"].str.match(r"^[A-H][1-5]$")][["plot", "hls_pixel"]]
    u = pix[pix["usable"]][["date", "product", "hls_pixel", "ndvi"]]
    sp = (g.merge(u, on="hls_pixel").groupby(["plot", "date", "product"])["ndvi"]
          .agg(["size", "std", "mean"]).reset_index())
    sp = sp[sp["size"] > 1]
    seas = (v20.dropna(subset=["ndvi_single"]).groupby("plot")["ndvi_single"]
            .agg(lambda x: x.quantile(0.95) - x.quantile(0.05)))
    out["homogeneity"] = {
        "n_plot_acquisitions": int(len(sp)),
        "between_pixel_ndvi_sd_median": float(sp["std"].median()),
        "as_pct_of_value": float(100 * (sp["std"] / sp["mean"]).median()),
        "seasonal_ndvi_range_median": float(seas.median()),
        "noise_as_pct_of_signal": float(100 * sp["std"].median() / seas.median()),
    }

    (sio.OUT / "results_summary.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf8")
    sio.record("S1-results", inputs=[], params={"growing_doy": list(GROWING_DOY)},
               outputs=["result_convention_vs_fieldlai.csv",
                        "result_convention_by_overlap.csv", "result_v14_vs_v20.csv",
                        "result_v14_vs_v20_stratified.csv", "result_date_sets.csv",
                        "result_sza_check.csv", "result_sza_summary.csv",
                        "results_summary.json"],
               notes="convention: %s; v1.4->v2.0 dominated by %s" % (
                   out["convention"]["winner"],
                   max(out["v14_vs_v20"]["dominant_channel"],
                       key=out["v14_vs_v20"]["dominant_channel"].get)))
    return out
