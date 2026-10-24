"""S1 end-to-end: AppEEARS bundles -> hf365_v2_candidate.

Named *candidate* deliberately. This is a proposed successor to the archived
HF365, not an archive release -- publishing it as a new version needs the
original dataset lead's sign-off.

Order matters here. Masking is applied **before** any index is computed, so a
contaminated reflectance never reaches an NDVI. That includes the provider's
own discard rule for high-aerosol retrievals, which is not optional: HLS known
issue #1 states such pixels should be dropped, and in this record 98.8 % of the
negative red reflectances carry that flag.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from s1 import appeears, extract, io as sio, qa

MEASURES = ("ndvi", "evi2", "nirv", "nir", "red")


def build_pixels() -> pd.DataFrame:
    """Every pixel-date, with indices, usability and granule provenance."""
    pix = appeears.attach_manifest(appeears.load_bundles())

    ok = pix["fmask_raw"].notna()
    usable = np.zeros(len(pix), bool)
    usable[ok.to_numpy()] = qa.usable(pix.loc[ok, "fmask_raw"].to_numpy().astype(int))
    # reflectance fill and out-of-range values are unusable regardless of QA
    bad = pix[["red", "nir"]].isna().any(axis=1).to_numpy()
    oob = ((pix["red"] < 0) | (pix["nir"] < 0)
           | (pix["red"] > 1) | (pix["nir"] > 1)).fillna(True).to_numpy()
    pix["usable"] = usable & ~bad & ~oob
    pix["rejected_reason"] = np.where(
        bad, "fill",
        np.where(oob, "reflectance_out_of_range",
                 np.where(~usable, "fmask", "")))

    idx = extract.indices(pix["nir"].to_numpy(), pix["red"].to_numpy())
    for k, v in idx.items():
        pix[k] = v
    pix.loc[~pix["usable"], list(idx)] = np.nan

    d = qa.decode(np.where(ok, pix["fmask_raw"].fillna(0), 0).astype(int))
    for k in ("cloud", "cloud_shadow", "adjacent_cloud_shadow", "snow_ice", "water"):
        pix[k] = d[k] & ok.to_numpy()
    pix["aerosol_level"] = np.where(ok, d["aerosol_level"], -1)
    pix["high_aerosol_discard"] = pix["aerosol_level"] == qa.AEROSOL_DISCARD
    pix["cirrus_proxy_flag"] = pix["cirrus_reflectance"] > 0.01
    return pix


def to_plots(pix: pd.DataFrame) -> pd.DataFrame:
    """Both assignment conventions, per plot per acquisition."""
    cw = extract.crosswalk()
    keep = ["hls_pixel", "usable", "sza", "vza", *MEASURES]
    out = []
    for (date, product), g in pix.groupby(["date", "product"], sort=True):
        p = extract.to_plots(g[keep], cw, measures=MEASURES)
        p["date"] = date
        p["product"] = product
        out.append(p)
    res = pd.concat(out, ignore_index=True)

    meta = (pix.drop_duplicates(["date", "product"])
            [["date", "product", "granule_ur", "platform", "l1c_baseline",
              "sensing_time_utc", "cloud_coverage_tile_pct"]])
    res = res.merge(meta, on=["date", "product"], how="left")
    res["year"] = pd.to_datetime(res["date"]).dt.year
    return res


def run() -> dict:
    pix = build_pixels()
    plots = to_plots(pix)
    miss = extract.missingness_structure(plots)

    sio.write(pix.drop(columns=[c for c in pix.columns if c.endswith("_appeears")]),
              "hls_v2_pixels.csv")
    sio.write(plots, "hf365_v2_candidate.csv")
    sio.write(miss, "missingness_structure.csv")

    stats = {
        "pixel_rows": int(len(pix)),
        "acquisitions": int(pix.groupby(["date", "product"]).ngroups),
        "usable_pixel_rows": int(pix["usable"].sum()),
        "frac_usable": float(pix["usable"].mean()),
        "rejected": pix.loc[~pix["usable"], "rejected_reason"].value_counts().to_dict(),
        "high_aerosol_rows": int(pix["high_aerosol_discard"].sum()),
        "plot_rows": int(len(plots)),
        "plot_rows_single_usable": int(plots["single_usable"].sum()),
        "plot_rows_weighted": int(plots["ndvi_weighted"].notna().sum()),
        **extract.effective_dates(miss),
    }
    sio.record("S1-extract", inputs=[], params={
        "measures": list(MEASURES),
        "bundles": appeears.BUNDLE_GLOB,
        "masking": "qa.usable (cloud, shadow, adjacent, snow, water, aerosol==3) "
                   "applied before indices; fill and out-of-range reflectance dropped",
    }, outputs=["hls_v2_pixels.csv", "hf365_v2_candidate.csv",
                "missingness_structure.csv"],
        notes=f"{stats['acquisitions']} acquisitions, "
              f"{100 * stats['frac_usable']:.1f}% of pixel-dates usable")
    return stats
