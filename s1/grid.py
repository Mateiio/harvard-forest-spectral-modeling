"""The T18TYN pixel grid, and the anchor check WP0 could not run.

WP0 built its HLS crosswalk on a 30 m grid anchored at the **UTM 18N origin**,
so that pixel column = ``floor(E/30)``. That equals the real HLS grid only if
the tile's upper-left corner is itself a multiple of 30 m in both axes. No
granule existed on disk, so every WP0 crosswalk row carries
``grid_verified=False``.

It is now verified, and without downloading anything: CMR's granule metadata
reports ``ULX = 699960.0`` and ``ULY = 4800000.0`` for every T18TYN granule,
and 699960 = 30 x 23332, 4800000 = 30 x 160000. **The anchor assumption holds.**

The CRS took more care. ``HORIZONTAL_CS_NAME`` is unreliable -- 308 of the 1098
granules do not report zone 18, one 2020 L30 granule says "UTM ZONE 19"
outright, and L30 carries no ``HORIZONTAL_CS_CODE`` at all. Zone 18 is settled
geometrically instead: with UL=(699960, 4800000) read as EPSG:32618 the tile's
SE corner computes to (-71.24214, 42.30245), matching CMR's own granule polygon
exactly, and the EMS tower falls inside the tile. Read as EPSG:32619 it lands
6 degrees away and the tower falls outside.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from s1 import schema


def tile_transform() -> tuple[float, float, float, float, float, float]:
    """Affine in rasterio order (a, b, c, d, e, f); c/f are the UL corner."""
    return (schema.RES_M, 0.0, schema.TILE_ULX,
            0.0, -schema.RES_M, schema.TILE_ULY)


def anchor_ok() -> tuple[bool, str]:
    """Does the tile origin sit on the global 30 m grid?"""
    dx = schema.TILE_ULX % schema.RES_M
    dy = schema.TILE_ULY % schema.RES_M
    ok = abs(dx) < 1e-6 and abs(dy) < 1e-6
    return ok, (f"UL=({schema.TILE_ULX}, {schema.TILE_ULY}); "
                f"x%30={dx:.6f}, y%30={dy:.6f}; "
                f"cols={schema.TILE_ULX / schema.RES_M:.0f}, "
                f"rows={schema.TILE_ULY / schema.RES_M:.0f}")


def global_to_tile(col: int | np.ndarray, row: int | np.ndarray):
    """WP0's global grid index -> (row, col) inside the tile array."""
    tile_col = np.asarray(col) - int(schema.TILE_ULX / schema.RES_M)
    tile_row = int(schema.TILE_ULY / schema.RES_M) - 1 - np.asarray(row)
    return tile_row, tile_col


def tile_to_global(tile_row: int | np.ndarray, tile_col: int | np.ndarray):
    col = np.asarray(tile_col) + int(schema.TILE_ULX / schema.RES_M)
    row = int(schema.TILE_ULY / schema.RES_M) - 1 - np.asarray(tile_row)
    return col, row


def window_for(pixels: pd.Series) -> dict:
    """Bounding read-window covering WP0's pixel ids, e.g. '24408_157110'."""
    idx = pixels.str.split("_", expand=True).astype(int)
    gcol, grow = idx[0].to_numpy(), idx[1].to_numpy()
    trow, tcol = global_to_tile(gcol, grow)
    r0, r1 = int(trow.min()), int(trow.max())
    c0, c1 = int(tcol.min()), int(tcol.max())
    return {"row_off": r0, "col_off": c0,
            "height": r1 - r0 + 1, "width": c1 - c0 + 1,
            "n_pixels_requested": int(len(set(zip(gcol, grow))))}


def verify_against_wp0() -> list[tuple[str, bool, str]]:
    """Feed the verified transform into WP0's own checker and re-derive A1."""
    from wp0 import crosswalk as wcross
    from wp0 import io as wio

    ok, detail = wcross.verify_grid_anchor(tile_transform())
    res = [("wp0.crosswalk.verify_grid_anchor accepts the T18TYN transform", ok, detail)]

    reg = pd.read_csv(wio.OUT / "plot_centroid_registry.csv")
    a1 = reg.loc[reg["plot"] == "A1"].iloc[0]
    gcol = int(np.floor(a1["utm18n_e"] / schema.RES_M))
    grow = int(np.floor(a1["utm18n_n"] / schema.RES_M))
    trow, tcol = global_to_tile(gcol, grow)
    inside = 0 <= trow < schema.TILE_NROWS and 0 <= tcol < schema.TILE_NCOLS
    res.append(("A1 lands in pixel 24408_157110", f"{gcol}_{grow}" == "24408_157110",
                f"{gcol}_{grow}"))
    res.append(("A1 is inside the tile array", inside,
                f"tile row {int(trow)}, col {int(tcol)} of {schema.TILE_NROWS}"))

    back_col, back_row = tile_to_global(trow, tcol)
    res.append(("tile<->global index round-trips",
                (int(back_col), int(back_row)) == (gcol, grow),
                f"{int(back_col)}_{int(back_row)}"))

    cw = pd.read_csv(wio.OUT / "crosswalk_plot_to_hls.csv")
    grid_plots = cw[cw["plot"].str.match(r"^[A-H][1-5]$")]
    w = window_for(grid_plots["hls_pixel"].drop_duplicates())
    res.append(("read window covers all 95 pixels of the 40 grid plots",
                w["n_pixels_requested"] == 95,
                f"{w['height']}x{w['width']} window, {w['n_pixels_requested']} distinct pixels"))
    return res
