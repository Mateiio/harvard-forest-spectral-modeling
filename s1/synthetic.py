"""A synthetic T18TYN granule, so the whole pipeline is testable without credentials.

The point is not to fake data that looks realistic. It is to exercise every
place the pipeline can be silently wrong:

  * the geotransform is the **real** one -- ``UL = (699960, 4800000)``,
    30 m, EPSG:32618 -- so the index arithmetic is tested against the true grid,
    not a convenient one;
  * reflectance is written as raw ``int16`` with fill ``-9999`` and angles as
    ``uint16`` with fill ``40000``, so the decode path is exercised on the real
    dtypes and the two different fill values;
  * the COGs are written **without** ``scale_factor``/``offset`` tags, which is
    the condition HLS known issue #7 describes; a loader that reads the scale
    from metadata instead of hard-coding it fails here;
  * Fmask is seeded with every flag combination that matters, including the
    high-aerosol discard class.

Values are planted so the expected answers are known in closed form: a chosen
plot's pixels carry a known NDVI, so the extracted single-pixel and
area-weighted values can be asserted rather than eyeballed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import Affine

from s1 import schema

TRUE_NIR = 0.3000
TRUE_RED = 0.0500
# NDVI = (0.30-0.05)/(0.30+0.05) = 0.714285...
TRUE_NDVI = (TRUE_NIR - TRUE_RED) / (TRUE_NIR + TRUE_RED)


def _write(path: Path, arr: np.ndarray, transform, dtype, nodata):
    with rasterio.open(
        path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1],
        count=1, dtype=dtype, crs=f"EPSG:{schema.EPSG}", transform=transform,
        nodata=nodata, tiled=True, blockxsize=16, blockysize=16,
    ) as dst:
        dst.write(arr.astype(dtype), 1)
        # deliberately NOT setting scales/offsets -- see module docstring


def make(outdir: Path, pixels: pd.Series, product: str = "L30",
         name: str = "HLS.L30.T18TYN.2020190T152632.v2.0",
         cloud_pixels: set[tuple[int, int]] | None = None,
         high_aerosol_pixels: set[tuple[int, int]] | None = None,
         fill_pixels: set[tuple[int, int]] | None = None) -> str:
    """Write one synthetic granule covering ``pixels``. Returns the url_base."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    idx = pixels.str.split("_", expand=True).astype(int)
    gcol, grow = idx[0].to_numpy(), idx[1].to_numpy()
    c0, c1 = int(gcol.min()), int(gcol.max())
    r0, r1 = int(grow.min()), int(grow.max())
    pad = 2
    c0, c1, r0, r1 = c0 - pad, c1 + pad, r0 - pad, r1 + pad
    width, height = c1 - c0 + 1, r1 - r0 + 1

    # Real grid: left edge of column c0, top edge of row r1.
    transform = Affine(schema.RES_M, 0, c0 * schema.RES_M,
                       0, -schema.RES_M, (r1 + 1) * schema.RES_M)

    nir = np.full((height, width), int(round(TRUE_NIR / schema.REF_SCALE)), np.int16)
    red = np.full((height, width), int(round(TRUE_RED / schema.REF_SCALE)), np.int16)
    cirrus = np.full((height, width), 50, np.int16)          # 0.005, below threshold
    fmask = np.zeros((height, width), np.uint8)
    fmask |= (1 << 6)                                        # low aerosol everywhere

    def to_rc(col, row):
        return r1 - row, col - c0

    for col, row in (cloud_pixels or set()):
        rr, cc = to_rc(col, row)
        fmask[rr, cc] |= (1 << 1)                            # cloud
    for col, row in (high_aerosol_pixels or set()):
        rr, cc = to_rc(col, row)
        fmask[rr, cc] = (fmask[rr, cc] & 0b00111111) | (3 << 6)   # high aerosol

    sza = np.full((height, width), int(round(35.0 / schema.ANG_SCALE)), np.uint16)
    saa = np.full((height, width), int(round(150.0 / schema.ANG_SCALE)), np.uint16)
    vza = np.full((height, width), int(round(4.0 / schema.ANG_SCALE)), np.uint16)
    vaa = np.full((height, width), int(round(100.0 / schema.ANG_SCALE)), np.uint16)

    # Fill must be planted on pixels the caller actually reads, otherwise the
    # -9999 / 40000 decode paths are never exercised. Reflectance and angles use
    # different fill values on purpose.
    for col, row in (fill_pixels or set()):
        rr, cc = to_rc(col, row)
        nir[rr, cc] = schema.REF_FILL
        red[rr, cc] = schema.REF_FILL
        sza[rr, cc] = schema.ANG_FILL

    base = outdir / name
    layers = {
        schema.RED_BAND[product]: (red, "int16", schema.REF_FILL),
        schema.NIR_BAND[product]: (nir, "int16", schema.REF_FILL),
        schema.CIRRUS_BAND[product]: (cirrus, "int16", schema.REF_FILL),
        "Fmask": (fmask, "uint8", schema.QA_FILL),
        "SZA": (sza, "uint16", schema.ANG_FILL),
        "SAA": (saa, "uint16", schema.ANG_FILL),
        "VZA": (vza, "uint16", schema.ANG_FILL),
        "VAA": (vaa, "uint16", schema.ANG_FILL),
    }
    for lname, (arr, dtype, nodata) in layers.items():
        _write(Path(f"{base}.{lname}.tif"), arr, transform, dtype, nodata)
    return str(base)


def expected() -> dict:
    return {"nir": TRUE_NIR, "red": TRUE_RED, "ndvi": TRUE_NDVI,
            "evi2": 2.5 * (TRUE_NIR - TRUE_RED) / (TRUE_NIR + 2.4 * TRUE_RED + 1),
            "nirv": TRUE_NDVI * TRUE_NIR}
