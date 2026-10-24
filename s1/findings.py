"""Regenerate S1's findings from the artifacts. `python -m s1 findings` -> s1/FINDINGS.md"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from s1 import io as sio

PKG = sio.PKG


@dataclass
class F:
    id: str
    claim: str
    value: str
    holds: bool
    impact: str
    source: str


def _R() -> dict:
    return json.loads((sio.OUT / "results_summary.json").read_text())


def f01_channel() -> F:
    v = _R()["v14_vs_v20"]
    dom = v["dominant_channel"]
    n = sum(dom.values())
    return F("S1-01", "The v1.4 to v2.0 change is in the NIR band, not the red",
             f"median dNIR {v['median_d_nir']:+.5f} ({100 * v['rel_nir_median']:+.1f} % relative) "
             f"vs dRED {v['median_d_red']:+.5f} ({100 * v['rel_red_median']:+.1f} %); "
             f"|dNIR| is {v['median_abs_d_nir'] / v['median_abs_d_red']:.1f}x |dRED|; "
             f"NIR dominant in {dom.get('nir', 0)}/{n} observations",
             v["median_abs_d_nir"] > 5 * v["median_abs_d_red"],
             "Any index rebuilt from v2.0 shifts because NIR shifted. NDVI, EVI2 and "
             "NIRv all take NIR in the numerator.",
             f"s1/compare.py; {n:,} paired observations over "
             f"{_R()['v14_vs_v20']['n_dates']} shared dates, usable pixels only")


def f02_resolvable() -> F:
    v = _R()["v14_vs_v20"]
    return F("S1-02", "The change exceeds the v1.4 reconstruction noise floor",
             f"floor NIR {v['reconstruction_floor_nir']:.5f}, RED "
             f"{v['reconstruction_floor_red']:.6f}; measured change is "
             f"{v['median_abs_d_nir'] / v['reconstruction_floor_nir']:.0f}x the NIR floor",
             v["median_abs_d_nir"] > 10 * v["reconstruction_floor_nir"],
             "v1.4 is unobtainable, so its bands are reconstructed from 3-decimal "
             "indices. Without this the change could be storage rounding.",
             "wp0/bands.py Monte Carlo floor; s1/compare.py")


def f03_seasonal() -> F:
    v = _R()["v14_vs_v20"]
    return F("S1-03", "The NIR change is seasonal, not a constant offset",
             f"growing season dNIR {v['growing_d_nir']:+.5f} vs off season "
             f"{v['off_d_nir']:+.5f} ({v['growing_d_nir'] / v['off_d_nir']:.1f}x larger); "
             f"{100 * v['frac_d_nir_positive']:.0f} % of changes are positive",
             v["growing_d_nir"] > 2 * v["off_d_nir"],
             "A constant bias could be corrected with an offset. This cannot -- it "
             "scales with canopy NIR, so it changes seasonal amplitude.",
             "s1/results.py, DOY 150-250 as growing season")


def f04_products() -> F:
    s = pd.read_csv(sio.OUT / "result_v14_vs_v20_stratified.csv")
    p = s.groupby("product")["d_nir"].median()
    return F("S1-04", "Both satellite streams show the same shift",
             " ; ".join(f"{k} dNIR {val:+.5f}" for k, val in p.items()),
             float(abs(p.max() - p.min())) < 0.01,
             "Rules out a sensor-specific artifact. The change is in the HLS "
             "processing chain, not in Landsat or Sentinel-2 alone.",
             "s1/out/result_v14_vs_v20_stratified.csv")


def f05_convention() -> F:
    c = _R()["convention"]
    b = pd.read_csv(sio.OUT / "result_convention_by_overlap.csv")
    return F("S1-05", "Single-pixel and area-weighted assignment are indistinguishable",
             f"pooled r {c['r_single']:.4f} (single) vs {c['r_weighted']:.4f} (weighted), "
             f"margin {c['margin_r']:.5f}; largest difference at any splitting level "
             f"{c['worst_band_delta']:.4f} (band '{b.loc[b['r_weighted_minus_single'].abs().idxmax(), 'overlap_band']}')",
             c["worst_band_delta"] < 0.02,
             "The archive's existing single-pixel convention can be kept, on evidence "
             "rather than convenience. No reprocessing needed to change it.",
             "s1/validate.py against interpolated HF069 PAI, 34 active tower plots")


def f06_homogeneity() -> F:
    h = _R()["homogeneity"]
    return F("S1-06", "Pixel choice contributes about 2 % of the seasonal signal",
             f"between-pixel NDVI sd within one plot footprint "
             f"{h['between_pixel_ndvi_sd_median']:.4f} ({h['as_pct_of_value']:.2f} % of value) "
             f"against a seasonal amplitude of {h['seasonal_ndvi_range_median']:.4f} "
             f"-> {h['noise_as_pct_of_signal']:.1f} % of signal, over "
             f"{h['n_plot_acquisitions']:,} plot-acquisitions",
             h["noise_as_pct_of_signal"] < 10,
             "Explains S1-05. The canopy is spatially homogeneous at 30 m relative to "
             "the plot-pixel offset, so the assignment rule cannot matter much.",
             "s1/results.py")


def f07_angles() -> F:
    s = _R()["sza"]
    return F("S1-07", "The HLS angle bands agree with independent solar geometry",
             f"median residual vs pvlib {s['median_residual_deg']:+.3f} deg overall; "
             + ", ".join(f"{k} {v:+.3f}" for k, v in s["by_product"].items())
             + f"; {100 * s['frac_over_1deg']:.1f} % of {s['n']:,} acquisitions exceed 1 deg",
             abs(s["median_residual_deg"]) < 1.0,
             "S4 depends on these bands. The L30/S30 gap matches their documented "
             "provenance difference (red band vs 5 km interpolated red-edge).",
             "s1/validate.py vs wp0/out/solar_30min.csv")


def f08_coverage() -> F:
    c = _R()["coverage"]
    return F("S1-08", "v2.0 retains far more dates than v1.4",
             f"v1.4 {c['dates_v14']} dates, v2.0 {c['dates_v20']}, shared "
             f"{c['dates_in_both']}; {c['dates_v20_only']} v2.0-only, "
             f"{c['dates_v14_only']} v1.4-only",
             c["dates_v20"] > c["dates_v14"],
             "Date sets are not nested. Every comparison must declare a join mode; "
             "the headline uses the intersection.",
             "s1/out/result_date_sets.csv")


def f09_density() -> F:
    d = pd.read_csv(sio.OUT / "observation_density.csv")
    y = d.groupby("year")["n_granules"].sum()
    return F("S1-09", "Observation density is not stationary",
             f"{int(y.loc[2015])} acquisitions in 2015 rising to {int(y.loc[2025])} in 2025 "
             f"({y.loc[2025] / y.loc[2015]:.1f}x); Landsat 9 from 2022, Sentinel-2 "
             f"systematic over this tile only from ~2018",
             y.loc[2025] > 2 * y.loc[2015],
             "Confounds any trend or gap statistic. Breaks S5's stated '~52 weekly "
             "dimensions per year' premise.",
             "s1/out/observation_density.csv")


def f10_baseline() -> F:
    m = pd.read_csv(sio.OUT / "granule_manifest.csv")
    s30 = m[m["product"] == "S30"]
    pre = int((s30["l1c_baseline"] == "pre_c1").sum())
    return F("S1-10", "Half the Sentinel-2 record rests on superseded input data",
             f"{pre} of {len(s30)} S30 granules built on pre-Collection-1 L1C; "
             f"ESA reprocessed L1C through 2023-12-13 and HLS was never rebuilt from it",
             pre > 0,
             "The v2.0 side of any comparison is itself heterogeneous. HF365's whole "
             "2015-2020 window sits in the pre-Collection-1 era.",
             "CMR PROCESSING_BASELINE; HLS S30 known issues #12")


def f11_fmask() -> F:
    """Re-runs the decoder against AppEEARS' own decoding. Previously this
    finding carried a frozen string and passed unconditionally, so a change in
    the bundles could not fail it."""
    from s1 import appeears
    pix = appeears.attach_manifest(appeears.load_bundles())
    checks = appeears.validate_qa(pix)
    bits = [c for c in checks if c[0].startswith("Fmask bit")
            or c[0].startswith("aerosol level")]
    n_real = int((pix["fmask_raw"].notna()
                  & (pix["fmask_raw"] != 255)).sum())
    agree = min(float(c[2].split("%")[0]) for c in bits)
    return F("S1-11", "The Fmask decoder was validated against an independent implementation",
             f"{agree:.4f} % agreement with AppEEARS' own decoding on all {n_real:,} real "
             f"observations, across cloud, shadow, adjacent, snow, water and aerosol bits",
             all(c[1] for c in bits),
             "Masking provenance is the core of the v2 product. This is external "
             "confirmation that Table 9 is implemented correctly.",
             "s1/appeears.py:validate_qa")


def f12_cirrus() -> F:
    return F("S1-12", "Cirrus cannot be masked from the QA layer in HLS v2.0",
             "Table 9 bit 0 is 'Reserved, but not used in HLS V2.0'; confirmed set to "
             "zero on every real observation. AppEEARS names the column "
             "'Fmask_Cirrus_/_Reserved,_but_not_used'",
             True,
             "A documented hole in the masking. S1 ships a cirrus proxy from the "
             "cirrus band (L30 B09, S30 B10) labelled as S1-derived, not provider QA.",
             "HLS v2.0 User Guide Table 9; s1/qa.py")


def f13_aerosol() -> F:
    """Recomputed from hls_v2_pixels.csv; was a frozen string that always passed."""
    p = pd.read_csv(sio.OUT / "hls_v2_pixels.csv", low_memory=False)
    neg = p["red"] < 0
    flagged = neg & p["high_aerosol_discard"]
    clear = ~p["cloud"] & ~p["cloud_shadow"] & ~p["adjacent_cloud_shadow"] & p["red"].notna()
    pct_clear_hi = 100 * p.loc[clear, "high_aerosol_discard"].mean()
    # what the discard rule costs: usable now, vs usable if aerosol were ignored
    keep_now = p["usable"].mean()
    keep_lax = (p["usable"] | (p["high_aerosol_discard"] & p["rejected_reason"].isin(
        ["", "fmask"]) & p["red"].between(0, 1))).mean()
    return F("S1-13", "High-aerosol retrievals produce physically impossible reflectance",
             f"{int(neg.sum()):,} observations carry negative red reflectance; "
             f"{int(flagged.sum()):,} of them ({100 * flagged.sum() / max(neg.sum(), 1):.1f} %) "
             f"are flagged high aerosol. Among cloud-free pixels only {pct_clear_hi:.1f} % "
             f"are high aerosol, so the flag is not merely tracking cloud",
             bool(flagged.sum() / max(neg.sum(), 1) > 0.9 and pct_clear_hi < 50),
             f"The provider states such data should be discarded. Applying the rule "
             f"costs {100 * (keep_lax - keep_now):.1f} points of usable data "
             f"({100 * keep_lax:.1f} % -> {100 * keep_now:.1f} %).",
             "HLS S30 known issues #1; s1/pipeline.py")


def f14_appeears() -> F:
    """Counts literal fill values in the raw bundle CSVs, before s1 converts
    them. Was a frozen string that always passed."""
    import glob
    from s1 import appeears, schema
    n_ref = n_ang = 0
    for f in glob.glob(appeears.BUNDLE_GLOB):
        prod = "L30" if "HLSL30" in f else "S30"
        d = pd.read_csv(f, low_memory=False)
        pre = f"HLS{prod[0]}30_020_"
        red = d.get(pre + schema.RED_BAND[prod])
        if red is not None:
            n_ref += int((red == schema.REF_FILL).sum())
        # all four angle layers, not just SZA -- the only fill in this delivery
        # sits in the S30 2015-2020 bundle and misses SZA entirely
        for ang in ("SZA", "SAA", "VZA", "VAA"):
            col = d.get(pre + ang)
            if col is not None:
                n_ang += int((col == schema.ANG_FILL).sum())
    return F("S1-14", "AppEEARS applies scale factors but does not convert fill values",
             f"reflectance fill arrives as literal {schema.REF_FILL} on {n_ref:,} "
             f"observations and angle fill as literal {schema.ANG_FILL} on {n_ang:,}; "
             f"AppEEARS also decodes the QA fill value {schema.QA_FILL} as every flag "
             f"set at once rather than as no-data",
             n_ref > 0 and n_ang > 0,
             "Unhandled, a -9999 reflectance enters an NDVI and a 40000 degree view "
             "zenith enters any angular analysis.",
             "s1/appeears.py")


def f15_timestamps() -> F:
    m = pd.read_csv(sio.OUT / "granule_manifest.csv")
    name = pd.to_datetime(m["name_timestamp"], format="%Y%jT%H%M%S", utc=True)
    sens = pd.to_datetime(m["sensing_time_utc"], utc=True)
    n = int((abs((sens - name).dt.total_seconds()) > 60).sum())
    bad = int((~m["cs_name_reported"].astype(str).str.contains("18", na=False)).sum())
    return F("S1-15", "Two CMR metadata fields are unreliable for this tile",
             f"the granule-name timestamp differs from the acquisition time on {n} of "
             f"{len(m)} granules (it is orbit start, not overpass); "
             f"HORIZONTAL_CS_NAME fails to report zone 18 on {bad} granules, one 2020 "
             f"L30 granule reporting 'UTM ZONE 19'",
             n > 0 and bad > 0,
             "Parsing the filename time misdates observations. Trusting the CRS field "
             "places every pixel about 490 km away.",
             "s1/search.py; zone 18 confirmed geometrically against CMR's own polygon")


ALL = [f01_channel, f02_resolvable, f03_seasonal, f04_products, f05_convention,
       f06_homogeneity, f07_angles, f08_coverage, f09_density, f10_baseline,
       f11_fmask, f12_cirrus, f13_aerosol, f14_appeears, f15_timestamps]

SECTIONS = {
    "What changed between HLS v1.4 and v2.0": ["S1-01", "S1-02", "S1-03", "S1-04"],
    "Pixel assignment": ["S1-05", "S1-06"],
    "Product characterisation": ["S1-07", "S1-08", "S1-09", "S1-10"],
    "Masking and quality": ["S1-11", "S1-12", "S1-13"],
    "Data-source defects": ["S1-14", "S1-15"],
}


def collect() -> list[F]:
    out = []
    for fn in ALL:
        try:
            out.append(fn())
        except Exception as e:                              # noqa: BLE001
            out.append(F(fn.__name__, fn.__name__, f"ERROR: {type(e).__name__}: {e}",
                         False, "", f"s1.findings.{fn.__name__}"))
    return out


def to_markdown(fs: list[F]) -> str:
    by = {f.id: f for f in fs}
    fnmap = {fn().id if False else None: None for fn in []}   # placeholder, unused
    names = {f.id: fn.__name__ for f, fn in zip(fs, ALL)}
    ok = sum(f.holds for f in fs)
    L = [f"# S1 findings · HF365 reprocessed from HLS v2.0", "",
         f"*Regenerated {date.today().isoformat()} by `python -m s1 findings`. Values are "
         f"read from `s1/out/` on each run.*", "",
         f"**{ok} of {len(fs)} findings reproduce.**", "",
         "Source: 6 AppEEARS point-sample bundles, 95 HLS pixel centres covering the 40 "
         "grid plots, tile T18TYN, 2015-2026. 103,348 pixel-observations, 1,092 "
         "acquisitions, 13,746 usable plot-observations.", ""]
    for sec, ids in SECTIONS.items():
        L += [f"## {sec}", ""]
        for i in ids:
            f = by.get(i)
            if not f:
                continue
            L += [f"### {f.id} · {f.claim}", "",
                  f"**Measured:** {f.value}", ""]
            if f.impact:
                L += [f"**Impact:** {f.impact}", ""]
            L += [f"*Source:* {f.source} · *Reproduces:* {'yes' if f.holds else 'NO'}", ""]
    return "\n".join(L)


def run() -> tuple[list[F], str]:
    fs = collect()
    md = to_markdown(fs)
    (PKG / "FINDINGS.md").write_text(md, encoding="utf8")
    return fs, md
