"""Per-product layer schema for HLS v2.0.

There is no generic band loop here on purpose. ``B10`` and ``B11`` mean
different physical quantities on the two products:

  * on **L30** they are top-of-atmosphere **brightness temperature in degrees
    C**, scale 0.01;
  * on **S30** they are **reflectance**, scale 0.0001.

A loop that fetches "all bands" and applies one scale produces a column that
looks plausible and is wrong by a factor of 100. So every layer is typed.

Scales and fills are **hard-coded, never read from the COG metadata**. HLS
known issue #7: ``scale_factor`` and ``offset`` were not written into the COG
headers for some granules, and those granules were never reprocessed. The
values below are the ones CMR reports in ``REF_SCALE_FACTOR`` /
``THERM_SCALE_FACTOR`` / ``ANG_SCALE_FACTOR`` and that Tables 6-8 of the v2.0
User Guide document.
"""

from __future__ import annotations

from dataclasses import dataclass

REF_SCALE = 0.0001
REF_FILL = -9999
THERM_SCALE = 0.01          # L30 B10/B11 only, degrees C
ANG_SCALE = 0.01
ANG_FILL = 40000            # Table 8 -- NOT -9999
QA_FILL = 255
TILE = "T18TYN"
TILE_ULX = 699960.0         # CMR AdditionalAttributes ULX
TILE_ULY = 4800000.0        # CMR AdditionalAttributes ULY
TILE_NCOLS = TILE_NROWS = 3660
RES_M = 30.0
EPSG = 32618                # zone 18N; see CRS_ATTRIBUTE_IS_UNRELIABLE


@dataclass(frozen=True)
class Layer:
    name: str
    quantity: str        # reflectance | brightness_temperature | angle | qa
    units: str
    dtype: str
    scale: float | None
    fill: int
    nbar: bool           # BRDF-adjusted?
    note: str = ""

    @property
    def is_reflectance(self) -> bool:
        return self.quantity == "reflectance"


def _refl(name, nbar=True, note=""):
    return Layer(name, "reflectance", "reflectance", "int16", REF_SCALE, REF_FILL, nbar, note)


def _ang(name, note=""):
    return Layer(name, "angle", "degrees", "uint16", ANG_SCALE, ANG_FILL, False, note)


_ANGLES = [
    _ang("SZA", "sun zenith"), _ang("SAA", "sun azimuth"),
    _ang("VZA", "view zenith"), _ang("VAA", "view azimuth"),
]
_FMASK = Layer("Fmask", "qa", "bit flags", "uint8", None, QA_FILL, False,
               "see s1.qa -- Table 9")

L30: dict[str, Layer] = {ly.name: ly for ly in [
    _refl("B01"), _refl("B02"), _refl("B03"),
    _refl("B04", note="RED"),
    _refl("B05", note="NIR (0.85-0.88 um)"),
    _refl("B06"), _refl("B07"),
    _refl("B09", nbar=False, note="cirrus 1.36-1.38 um; not BRDF-adjusted"),
    Layer("B10", "brightness_temperature", "degC", "int16", THERM_SCALE, REF_FILL,
          False, "TOA BT -- NOT reflectance on L30"),
    Layer("B11", "brightness_temperature", "degC", "int16", THERM_SCALE, REF_FILL,
          False, "TOA BT -- NOT reflectance on L30"),
    *_ANGLES, _FMASK,
]}

S30: dict[str, Layer] = {ly.name: ly for ly in [
    _refl("B01"), _refl("B02"), _refl("B03"),
    _refl("B04", note="RED"),
    _refl("B05"), _refl("B06"), _refl("B07"),
    _refl("B08", note="NIR broad 0.78-0.88 um -- NOT the band HF365 uses"),
    _refl("B8A", note="NIR narrow 0.85-0.88 um -- matches L30 B05, use this one"),
    _refl("B09", nbar=False),
    _refl("B10", nbar=False, note="cirrus 1.36-1.39 um; TOA reflectance on S30"),
    _refl("B11"), _refl("B12"),
    *_ANGLES, _FMASK,
]}

PRODUCTS = {"L30": L30, "S30": S30}

# The two bands HF365's three indices need, per product.
RED_BAND = {"L30": "B04", "S30": "B04"}
NIR_BAND = {"L30": "B05", "S30": "B8A"}     # S30 is B8A, never B08
CIRRUS_BAND = {"L30": "B09", "S30": "B10"}

# Minimum set to fetch: the two index bands, the cirrus proxy, QA, all angles.
CORE_LAYERS = {
    p: [RED_BAND[p], NIR_BAND[p], CIRRUS_BAND[p], "Fmask", "SZA", "SAA", "VZA", "VAA"]
    for p in PRODUCTS
}

# Angle provenance differs by product and is coarser than "per-observation"
# suggests (User Guide 6.3): L30 angles are derived for the red band and applied
# to every band; S30 angles are interpolated from ESA's 5 km grid, taking the
# 2nd red-edge band's view angle for all bands.
ANGLE_PROVENANCE = {
    "L30": "L30_red_band_applied_to_all",
    "S30": "S30_rededge2_interpolated_from_5km_grid",
}

# CMR's HORIZONTAL_CS_NAME is not reliable: the 2020-07-08 L30 granule for this
# tile reports "UTM, WGS84, UTM ZONE 19" while the 2024 granule reports zone 18,
# and only S30 carries HORIZONTAL_CS_CODE at all. Zone 18 is confirmed
# geometrically: with UL=(699960, 4800000) in EPSG:32618 the tile's SE corner
# computes to (-71.24214, 42.30245), matching CMR's own polygon exactly, and the
# EMS tower falls inside the tile. Under EPSG:32619 it is 6 degrees off and the
# tower falls outside. Trust the tile ID and the COG's own CRS, not this field.
CRS_ATTRIBUTE_IS_UNRELIABLE = True


def layer(product: str, name: str) -> Layer:
    try:
        return PRODUCTS[product][name]
    except KeyError as e:
        raise KeyError(f"{name!r} is not a layer of HLS {product}") from e


def decode(product: str, name: str, raw):
    """Apply the hard-coded scale and fill for one layer. Returns float array."""
    import numpy as np
    ly = layer(product, name)
    arr = np.asarray(raw)
    if ly.scale is None:                      # Fmask stays integral
        return arr
    out = arr.astype("float64")
    out[arr == ly.fill] = np.nan
    return out * ly.scale
