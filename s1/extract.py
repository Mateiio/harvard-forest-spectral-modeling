"""Pixel -> plot, under both assignment conventions, plus missingness structure.

**Single pixel** is the archive's convention: the value of the one pixel with
the largest overlap. **Area weighted** uses every pixel the plot circle touches,
weighted by WP0's exact circle-rectangle overlap fractions. Which one tracks
field LAI better is S1's fastest defensible result, and it is only decidable
because both are computed from the same download.

Two details that decide whether the area-weighted value is honest:

  * weights are **renormalised over the usable pixels only**, so a plot whose
    outer pixel is clouded is not silently pulled toward zero;
  * ``weight_coverage`` records how much of the plot's area survived masking, so
    a value built from 30 % of the plot is distinguishable from a clean one.

:func:`missingness_structure` exists because Fmask dilates cloud and shadow by
5 pixels (150 m) while the whole plot network spans about 500 m. One cloud edge
can therefore mask most of the network on the same date, which makes
missingness correlated across plots rather than independent. Anything that
treats 40 plots as 40 independent samples on a given date needs this number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from s1 import io as sio, qa, schema

GRID_PLOT = r"^[A-H][1-5]$"


def crosswalk(grid_only: bool = True) -> pd.DataFrame:
    cw = sio.read_wp0("crosswalk_hls")
    if grid_only:
        cw = cw[cw["plot"].str.match(GRID_PLOT)]
    return cw.reset_index(drop=True)


def indices(nir: np.ndarray, red: np.ndarray) -> dict[str, np.ndarray]:
    """The three HF365 indices, exactly as hf365.xml defines them."""
    ndvi = (nir - red) / (nir + red)
    return {"ndvi": ndvi,
            "evi2": 2.5 * (nir - red) / (nir + 2.4 * red + 1.0),
            "nirv": ndvi * nir}


def pixel_frame(layers: dict, product: str) -> pd.DataFrame:
    """Windowed arrays -> one tidy row per pixel, with QA and usability."""
    from s1.fetch import pixel_index
    tf = layers["_transform"]
    red = layers[schema.RED_BAND[product]]
    nir = layers[schema.NIR_BAND[product]]
    h, w = red.shape
    cols, rows = pixel_index(tf, h, w)
    cc, rr = np.meshgrid(cols, rows)

    fmask = layers["Fmask"]
    ok = qa.usable(fmask)
    d = qa.decode(fmask)
    idx = indices(nir, red)

    out = pd.DataFrame({
        "hls_pixel": [f"{c}_{r}" for c, r in zip(cc.ravel(), rr.ravel())],
        "nir": nir.ravel(), "red": red.ravel(),
        "usable": ok.ravel(),
        "cloud": d["cloud"].ravel(),
        "cloud_shadow": d["cloud_shadow"].ravel(),
        "adjacent_cloud_shadow": d["adjacent_cloud_shadow"].ravel(),
        "snow_ice": d["snow_ice"].ravel(),
        "water": d["water"].ravel(),
        "aerosol_level": d["aerosol_level"].ravel(),
        "high_aerosol_discard": (d["aerosol_level"] == qa.AEROSOL_DISCARD).ravel(),
    })
    for k, v in idx.items():
        out[k] = v.ravel()
    for ang in ("SZA", "SAA", "VZA", "VAA"):
        if ang in layers:
            out[ang.lower()] = layers[ang].ravel()
    cb = schema.CIRRUS_BAND[product]
    if cb in layers:
        out["cirrus_reflectance"] = layers[cb].ravel()
        out["cirrus_proxy_flag"] = out["cirrus_reflectance"] > 0.01
    # reflectance fill and QA fill are different things; both make a pixel unusable
    out.loc[out[["nir", "red"]].isna().any(axis=1), "usable"] = False
    return out


def to_plots(pix: pd.DataFrame, cw: pd.DataFrame,
             measures=("ndvi", "evi2", "nirv", "nir", "red")) -> pd.DataFrame:
    """Both conventions, per plot."""
    j = cw.merge(pix, on="hls_pixel", how="left")

    single = (j[j["is_dominant"]]
              .set_index("plot")[list(measures) + ["usable", "sza", "vza"]]
              .add_suffix("_single"))
    single = single.rename(columns={"usable_single": "single_usable",
                                    "sza_single": "sza", "vza_single": "vza"})

    u = j[j["usable"].fillna(False)].copy()
    wsum = u.groupby("plot")["overlap_frac"].sum().rename("weight_coverage")
    rows = {}
    for m in measures:
        num = (u[m] * u["overlap_frac"]).groupby(u["plot"]).sum()
        rows[f"{m}_weighted"] = num / wsum
    weighted = pd.DataFrame(rows).join(wsum)

    total_w = cw.groupby("plot")["overlap_frac"].sum().rename("weight_total")
    n_touched = cw.groupby("plot")["hls_pixel"].nunique().rename("n_pixels_touched")
    n_usable = u.groupby("plot")["hls_pixel"].nunique().rename("n_pixels_usable")

    out = (pd.concat([single, weighted], axis=1)
           .join(total_w).join(n_touched).join(n_usable))
    out["n_pixels_usable"] = out["n_pixels_usable"].fillna(0).astype(int)
    out["weight_coverage"] = (out["weight_coverage"].fillna(0.0)
                              / out["weight_total"]).clip(upper=1.0)
    out["single_usable"] = out["single_usable"].fillna(False).astype(bool)
    return out.reset_index().rename(columns={"index": "plot"})


def missingness_structure(per_date: pd.DataFrame) -> pd.DataFrame:
    """Per date: how much of the network was masked at once.

    ``frac_plots_usable`` near 0 or 1 and rarely in between is the signature of
    the 150 m dilation acting on a network only ~500 m across -- missingness is
    a property of the date, not of the plot.
    """
    g = per_date.groupby("date")
    out = pd.DataFrame({
        "n_plots": g["plot"].nunique(),
        "frac_plots_single_usable": g["single_usable"].mean(),
        "mean_weight_coverage": g["weight_coverage"].mean(),
    }).reset_index()
    out["all_or_nothing"] = (out["frac_plots_single_usable"] < 0.05) | \
                            (out["frac_plots_single_usable"] > 0.95)
    return out


def effective_dates(miss: pd.DataFrame) -> dict:
    """Dates with any usable plot, and how many are all-or-nothing."""
    any_usable = miss[miss["frac_plots_single_usable"] > 0]
    return {
        "n_dates": int(len(miss)),
        "n_dates_any_usable": int(len(any_usable)),
        "n_dates_fully_usable": int((miss["frac_plots_single_usable"] > 0.95).sum()),
        "frac_all_or_nothing": float(miss["all_or_nothing"].mean()),
        "note": ("missingness is correlated across plots by construction: Fmask "
                 f"dilates cloud/shadow {qa.DILATION_PIXELS} pixels "
                 f"({qa.DILATION_M:.0f} m) and the network spans ~500 m"),
    }
