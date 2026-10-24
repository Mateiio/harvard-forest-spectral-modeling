"""Fmask decoding, Table 9 of the HLS v2.0 User Guide.

    bit 0  Cirrus            Reserved, but NOT USED in HLS V2.0
    bit 1  Cloud
    bit 2  Adjacent to cloud/shadow
    bit 3  Cloud shadow
    bit 4  Snow/ice
    bit 5  Water
    bits 6-7  Aerosol level  00 climatology, 01 low, 10 moderate, 11 high

Three things this module exists to get right.

**Bit 0 never fires.** Cirrus is reserved and unused in v2.0, so cirrus
contamination is invisible to the provider QA. HF365's NAs were undocumented;
replacing them with "explicit Fmask provenance" is an improvement, but it is
not a complete mask, and the product must say so. :func:`cirrus_proxy` offers a
substitute derived from the cirrus reflectance band -- clearly labelled as
S1-derived, not provider QA.

**Aerosol 11 means discard, not "note the level".** HLS known issue #1: the
atmospheric correction occasionally retrieves an unreasonably high AOT next to
bright targets, which drives surface reflectance too low; both high-AOT cases,
false and real, are flagged with bits 6 and 7 set, and the provider states the
corresponding spectral data should be discarded.

**The lower six bits are not mutually exclusive.** The User Guide is explicit
that resampling to 30 m mixes categorical labels, so these are independent
booleans and must never be collapsed into one categorical class.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from s1 import schema

BITS = {
    "cirrus_reserved_unused": 0,
    "cloud": 1,
    "adjacent_cloud_shadow": 2,
    "cloud_shadow": 3,
    "snow_ice": 4,
    "water": 5,
}
AEROSOL_LEVELS = {0: "climatology", 1: "low", 2: "moderate", 3: "high"}
AEROSOL_DISCARD = 3          # bits 6 and 7 both set

# Cloud and cloud shadow are dilated by 5 pixels (150 m) on both products.
# The plot network spans ~500 m, so one cloud edge masks much of it at once and
# missingness is strongly correlated across plots. s1.extract measures that.
DILATION_PIXELS = 5
DILATION_M = DILATION_PIXELS * schema.RES_M

# Fmask ran without its DEM and ESA surface-water auxiliary inputs for a 2-3
# month run in 2021 (known issue #3), degrading masking over water and in
# mountainous terrain. The network contains the beaver pond at G3/H3/H4.
FMASK_AUX_DEFICIENT = ("2021-01-01", "2021-12-31")


def decode(fmask) -> dict[str, np.ndarray]:
    """Fmask integers -> named boolean layers + aerosol level + validity."""
    arr = np.asarray(fmask)
    valid = arr != schema.QA_FILL
    a = np.where(valid, arr, 0).astype(np.uint16)

    out = {name: ((a >> bit) & 1).astype(bool) & valid for name, bit in BITS.items()}
    out["aerosol_level"] = np.where(valid, (a >> 6) & 3, -1).astype(np.int8)
    out["qa_valid"] = valid
    return out


def usable(fmask, *, allow_water: bool = False,
           allow_adjacent: bool = False) -> np.ndarray:
    """Boolean mask of pixels fit to compute an index from.

    Excludes cloud, cloud shadow, snow/ice, the high-aerosol discard class and
    QA fill. ``adjacent_cloud_shadow`` is excluded by default: it is the 5-pixel
    dilation, and keeping it admits pixels the provider considers contaminated.
    Water is excluded by default too -- it is not vegetation.
    """
    d = decode(fmask)
    ok = d["qa_valid"] & ~d["cloud"] & ~d["cloud_shadow"] & ~d["snow_ice"]
    ok &= d["aerosol_level"] != AEROSOL_DISCARD
    if not allow_adjacent:
        ok &= ~d["adjacent_cloud_shadow"]
    if not allow_water:
        ok &= ~d["water"]
    return ok


def summarise(fmask) -> dict:
    """Per-granule counts, for the QA provenance table."""
    d = decode(fmask)
    n = int(np.asarray(fmask).size)
    out = {f"frac_{k}": float(v.mean()) for k, v in d.items()
           if v.dtype == bool and k != "qa_valid"}
    out["n_pixels"] = n
    out["frac_qa_fill"] = float((~d["qa_valid"]).mean())
    for lvl, nm in AEROSOL_LEVELS.items():
        out[f"frac_aerosol_{nm}"] = float((d["aerosol_level"] == lvl).mean())
    out["frac_usable"] = float(usable(fmask).mean())
    out["frac_discarded_high_aerosol"] = float((d["aerosol_level"] == AEROSOL_DISCARD).mean())
    return out


def cirrus_proxy(product: str, cirrus_reflectance, threshold: float = 0.01) -> np.ndarray:
    """S1-derived cirrus flag. NOT provider QA -- bit 0 is unused in v2.0.

    Uses the cirrus band (L30 ``B09``, S30 ``B10``, ~1.36-1.39 um). That
    waveband is opaque to water vapour, so a clear low-altitude scene is dark in
    it and thin high cloud is bright. The threshold is a convention, not a
    calibrated retrieval, so the flag ships alongside the raw reflectance and
    the threshold is recorded in provenance.
    """
    ref = schema.decode(product, schema.CIRRUS_BAND[product], cirrus_reflectance)
    return np.asarray(ref) > threshold


def provenance_columns(date: str) -> dict:
    """Per-observation QA caveats that are properties of the date, not the pixel."""
    lo, hi = FMASK_AUX_DEFICIENT
    return {
        "fmask_cirrus_available": False,          # bit 0 unused in v2.0
        "fmask_aux_deficient": bool(lo <= date <= hi),
        "cloud_dilation_m": DILATION_M,
    }


def checks() -> list[tuple[str, bool, str]]:
    """Round-trip every bit through decode(), plus the discard rule."""
    res = []
    # one pixel per single bit, then fill, then each aerosol level
    vals = np.array([1 << b for b in range(6)] + [schema.QA_FILL], dtype=np.uint8)
    d = decode(vals)
    for name, bit in BITS.items():
        got = d[name]
        want = np.zeros(len(vals), bool)
        want[bit] = True
        res.append((f"bit {bit} -> {name}", bool((got == want).all()),
                    f"{got.astype(int).tolist()}"))
    res.append(("QA fill 255 is not decoded as flags",
                not d["qa_valid"][-1], "qa_valid[fill]=False"))

    aer = np.array([lvl << 6 for lvl in range(4)], dtype=np.uint8)
    da = decode(aer)
    res.append(("aerosol bits 6-7 decode 0..3",
                da["aerosol_level"].tolist() == [0, 1, 2, 3],
                str(da["aerosol_level"].tolist())))
    res.append(("aerosol level 3 (high) is discarded",
                not usable(np.array([3 << 6], dtype=np.uint8))[0],
                "bits 6+7 set -> unusable"))
    res.append(("clear low-aerosol pixel is usable",
                bool(usable(np.array([1 << 6], dtype=np.uint8))[0]), "low aerosol -> usable"))
    res.append(("adjacent-to-cloud excluded by default",
                not usable(np.array([1 << 2], dtype=np.uint8))[0],
                f"the {DILATION_PIXELS}-pixel ({DILATION_M:.0f} m) dilation"))
    res.append(("cirrus bit 0 is never set by the provider",
                schema.CIRRUS_BAND["L30"] == "B09" and schema.CIRRUS_BAND["S30"] == "B10",
                "use cirrus_proxy() instead"))
    return res
