"""v1.4 versus v2.0 at the HF365 pixels, and the red-vs-NIR attribution.

v1.4 is unobtainable through any NASA channel, so the only surviving record of
it at these pixels is HF365 itself. WP0 recovered NIR and RED from the three
archived indices in closed form. **That makes this comparison
reconstruction-versus-measurement, not measurement-versus-measurement**, and
the reconstruction has a noise floor: HF365 stores three decimals, which puts
the recovered RED at about 0.33 % relative, 7.3e-5 absolute, in the growing
season. A v1.4-to-v2.0 difference smaller than that is not reportable, so the
floor travels with every row.

Two structural cautions the join has to respect.

**The date sets do not nest.** HF365 kept 261-262 dates out of roughly 370
granule-dates available in its window; v2.0 under different masking keeps a
different set. So ``join_mode`` is explicit and the headline uses the
intersection, with the coverage gain reported separately as a count rather than
folded into the comparison.

**The v2.0 side is not one homogeneous product.** ESA reprocessed Sentinel-2
L1C into Collection 1 after HLS V2.0's historical run, and HLS was never
rebuilt from it (known issue #12), so 224 of the 484 S30 granules over this
tile rest on pre-Collection-1 input. Every row carries ``l1c_baseline``, and the
headline comparison is restricted to a window where it is uniform.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from s1 import io as sio

JOIN_MODES = ("intersection", "v14_only", "v20_only", "union")
HF365_WINDOW = ("2015-01-23", "2020-08-10")


def load_v14() -> pd.DataFrame:
    v = sio.read_wp0("v14_reflectance")
    keep = ["date", "plot", "nir", "red", "sd_nir", "sd_red", "ndvi", "nirv", "season"]
    return v[[c for c in keep if c in v.columns]].rename(
        columns={"nir": "nir_v14", "red": "red_v14", "ndvi": "ndvi_v14",
                 "nirv": "nirv_v14", "sd_nir": "sd_nir_v14", "sd_red": "sd_red_v14"})


def date_sets(v14: pd.DataFrame, v20: pd.DataFrame) -> pd.DataFrame:
    a, b = set(v14["date"]), set(v20["date"])
    alld = sorted(a | b)
    return pd.DataFrame({"date": alld,
                         "in_v14": [d in a for d in alld],
                         "in_v20": [d in b for d in alld],
                         "in_both": [d in a and d in b for d in alld]})


def join(v14: pd.DataFrame, v20: pd.DataFrame, mode: str = "intersection",
         convention: str = "single") -> pd.DataFrame:
    if mode not in JOIN_MODES:
        raise ValueError(f"join_mode must be one of {JOIN_MODES}")
    how = {"intersection": "inner", "v14_only": "left",
           "v20_only": "right", "union": "outer"}[mode]
    suf = f"_{convention}"
    cols = ["date", "plot", f"nir{suf}", f"red{suf}", f"ndvi{suf}"]
    right = v20[[c for c in cols if c in v20.columns]
                + [c for c in ("l1c_baseline", "platform", "product") if c in v20.columns]]

    # Only compare against v2.0 pixels that survived masking. `nir_single` and
    # `red_single` are carried from the dominant pixel whether or not it passed
    # -- only the *indices* are nulled -- so an unfiltered join silently
    # compares a clean v1.4 value against clouded v2.0 reflectance and charges
    # the difference to the version change. 30 % of rows were affected.
    ok = "single_usable" if convention == "single" else "weight_coverage"
    if ok in v20.columns:
        keep = (v20[ok].astype(bool) if ok == "single_usable"
                else v20[ok].fillna(0) > 0)
        right = right[keep.to_numpy()]

    m = v14.merge(right, on=["date", "plot"], how=how)
    m["join_mode"] = mode
    m["convention"] = convention
    return m


def attribute(m: pd.DataFrame, convention: str = "single") -> pd.DataFrame:
    """Per-observation v1.4->v2.0 change, split into the red and NIR channels."""
    suf = f"_{convention}"
    out = m.copy()
    out["d_nir"] = out[f"nir{suf}"] - out["nir_v14"]
    out["d_red"] = out[f"red{suf}"] - out["red_v14"]
    # is the change larger than what the v1.4 reconstruction can resolve?
    out["d_nir_resolvable"] = out["d_nir"].abs() > 2 * out["sd_nir_v14"]
    out["d_red_resolvable"] = out["d_red"].abs() > 2 * out["sd_red_v14"]
    denom = out["d_nir"].abs() + out["d_red"].abs()
    out["red_share"] = np.where(denom > 0, out["d_red"].abs() / denom, np.nan)
    out["dominant_channel"] = np.where(
        out["d_red"].abs() > out["d_nir"].abs(), "red", "nir")
    out.loc[~(out["d_nir_resolvable"] | out["d_red_resolvable"]),
            "dominant_channel"] = "below_reconstruction_floor"
    return out


def summarise(att: pd.DataFrame) -> dict:
    res = att.dropna(subset=["d_nir", "d_red"])
    if res.empty:
        return {"n": 0}
    return {
        "n_observations": int(len(res)),
        "n_dates": int(res["date"].nunique()),
        "median_d_nir": float(res["d_nir"].median()),
        "median_d_red": float(res["d_red"].median()),
        "median_abs_d_nir": float(res["d_nir"].abs().median()),
        "median_abs_d_red": float(res["d_red"].abs().median()),
        "reconstruction_floor_red": float(res["sd_red_v14"].median()),
        "reconstruction_floor_nir": float(res["sd_nir_v14"].median()),
        "frac_red_resolvable": float(res["d_red_resolvable"].mean()),
        "frac_nir_resolvable": float(res["d_nir_resolvable"].mean()),
        "dominant_channel": res["dominant_channel"].value_counts().to_dict(),
    }


def coverage_gain(ds: pd.DataFrame) -> dict:
    """Extra dates v2.0 brings -- reported as a count, never folded into the delta."""
    return {
        "dates_v14": int(ds["in_v14"].sum()),
        "dates_v20": int(ds["in_v20"].sum()),
        "dates_in_both": int(ds["in_both"].sum()),
        "dates_v20_only": int((ds["in_v20"] & ~ds["in_v14"]).sum()),
        "dates_v14_only": int((ds["in_v14"] & ~ds["in_v20"]).sum()),
    }
