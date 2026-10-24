"""Stage B: plot-to-pixel crosswalks for HLS (30 m) and MODIS (500 m).

**HLS.** Plot footprints are circles (hf069.xml), HLS pixels are squares on the
UTM 18N grid, so the overlap is an exact circle-rectangle intersection via
shapely. Two things the v0 crosswalk got wrong and this fixes:

  * it applied a 10 m radius to every plot, but hf069.xml expands the harvest
    group (A4, A5, B5, X1-X6) to 15 m in summer 2001 -- and HF365 covers
    2015-2020, entirely inside that epoch;
  * the 30 m grid is anchored on the UTM 18N origin, which equals the real HLS
    grid only if tile T18TYN's upper-left corner is a multiple of 30 m in both
    axes. **This is now verified** -- see :data:`GRID_ANCHOR_EVIDENCE`.

**MODIS.** The sinusoidal grid is computed from the published MCD15A2H
definition and validated against the tile/line/sample that AppEEARS returns for
the five downloaded pixels -- an external key, independent of anything in v0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point, box

from wp0 import io

# --------------------------------------------------------------------------
# MODIS sinusoidal grid (MCD15A2H v061, 500 m)
# --------------------------------------------------------------------------
SINU = ("+proj=sinu +lon_0=0 +x_0=0 +y_0=0 "
        "+a=6371007.181 +b=6371007.181 +units=m +no_defs")
MODIS_UL_X = -20015109.354
MODIS_UL_Y = 10007554.677
MODIS_TILE_M = 1111950.5196666666
MODIS_CELLS_PER_TILE = 2400
MODIS_CELL_M = MODIS_TILE_M / MODIS_CELLS_PER_TILE   # 463.31271652777775

# AppEEARS Main5Pixels point sample: the external validation key.
APPEEARS_PIXELS = {
    (1790, 1636): "pixel1",
    (1790, 1637): "pixel2",
    (1791, 1635): "pixel3",
    (1791, 1636): "pixel4",
    (1791, 1637): "pixel5",
}


def _sinu_tx() -> Transformer:
    return Transformer.from_crs("EPSG:4326", SINU, always_xy=True)


def modis_cell(lat, lon) -> pd.DataFrame:
    """Containing MODIS cell for each coordinate, as (h, v, line, sample)."""
    x, y = _sinu_tx().transform(np.asarray(lon), np.asarray(lat))
    h = np.floor((x - MODIS_UL_X) / MODIS_TILE_M).astype(int)
    v = np.floor((MODIS_UL_Y - y) / MODIS_TILE_M).astype(int)
    sample = np.floor((x - (MODIS_UL_X + h * MODIS_TILE_M)) / MODIS_CELL_M).astype(int)
    line = np.floor(((MODIS_UL_Y - v * MODIS_TILE_M) - y) / MODIS_CELL_M).astype(int)
    return pd.DataFrame({"h": h, "v": v, "line": line, "sample": sample,
                         "sinu_x": x, "sinu_y": y})


def validate_modis_grid() -> list[tuple[str, bool, str]]:
    """Round-trip the five AppEEARS pixel centres through the grid math."""
    rows = []
    for (line, sample), name in APPEEARS_PIXELS.items():
        cx = MODIS_UL_X + 12 * MODIS_TILE_M + (sample + 0.5) * MODIS_CELL_M
        cy = MODIS_UL_Y - 4 * MODIS_TILE_M - (line + 0.5) * MODIS_CELL_M
        lon, lat = Transformer.from_crs(SINU, "EPSG:4326", always_xy=True).transform(cx, cy)
        # bracket access throughout: `.sample` resolves to Series.sample, not the column
        got = modis_cell([lat], [lon]).iloc[0]
        gl, gs, gh, gv = (int(got["line"]), int(got["sample"]),
                          int(got["h"]), int(got["v"]))
        ok = (gl, gs, gh, gv) == (line, sample, 12, 4)
        rows.append((f"AppEEARS {name} round-trips to h12v04 line={line} sample={sample}",
                     ok, f"got h{gh}v{gv} line={gl} sample={gs}"))
    return rows


# --------------------------------------------------------------------------
# HLS 30 m grid on UTM 18N
# --------------------------------------------------------------------------

# Verified 2026-08-07 from CMR granule metadata, without downloading a granule:
# every HLS T18TYN granule reports ULX = 699960.0 and ULY = 4800000.0, and
# 699960 = 30 x 23332, 4800000 = 30 x 160000. So the tile origin lies on the
# global 30 m grid and floor(E/30) is the true HLS pixel column.
#
# The CRS needed separate care. CMR's HORIZONTAL_CS_NAME is unreliable -- 308 of
# 1098 granules do not report zone 18, and one 2020 L30 granule says "UTM ZONE
# 19" outright. Zone 18 is settled geometrically: read as EPSG:32618 the tile's
# SE corner computes to (-71.24214, 42.30245), matching CMR's own granule
# polygon exactly, and the EMS tower falls inside the tile. Read as EPSG:32619
# it lands 6 degrees away and the tower falls outside.
GRID_ANCHOR_VERIFIED = True
GRID_ANCHOR_EVIDENCE = (
    "CMR AdditionalAttributes ULX=699960.0 ULY=4800000.0 for HLS T18TYN; "
    "both exact multiples of 30 m. CRS confirmed EPSG:32618 geometrically "
    "against the granule polygon. See s1.grid."
)

def hls_cell_bounds(col: int, row: int) -> tuple[float, float, float, float]:
    return (col * io.HLS_RES_M, row * io.HLS_RES_M,
            (col + 1) * io.HLS_RES_M, (row + 1) * io.HLS_RES_M)


def _plot_radius(reg: pd.DataFrame, epoch: str) -> pd.Series:
    col = "radius_m_post2001" if epoch == "post2001" else "radius_m_pre2001"
    return reg[col]


def hls_overlaps(reg: pd.DataFrame, epoch: str = "post2001",
                 radius_override: float | None = None) -> pd.DataFrame:
    """Exact circle-rectangle intersection of every plot against the 30 m grid."""
    radii = (pd.Series(radius_override, index=reg.index)
             if radius_override is not None else _plot_radius(reg, epoch))
    inv = Transformer.from_crs(f"EPSG:{io.EPSG_UTM18N}", "EPSG:4326", always_xy=True)

    rows = []
    # Bracket access only. `p.plot` resolves to the pandas plotting accessor and
    # `p.sample` to Series.sample -- and both `plot` and `sample` are column
    # names in this program.
    for (_, p), r in zip(reg.iterrows(), radii):
        e, n = p["utm18n_e"], p["utm18n_n"]
        circle = Point(e, n).buffer(r, quad_segs=256)
        c0 = int(np.floor((e - r) / io.HLS_RES_M))
        c1 = int(np.floor((e + r) / io.HLS_RES_M))
        r0 = int(np.floor((n - r) / io.HLS_RES_M))
        r1 = int(np.floor((n + r) / io.HLS_RES_M))
        for col in range(c0, c1 + 1):
            for row in range(r0, r1 + 1):
                inter = circle.intersection(box(*hls_cell_bounds(col, row)))
                if inter.is_empty or inter.area <= 0:
                    continue
                clon, clat = inv.transform((col + 0.5) * io.HLS_RES_M,
                                           (row + 0.5) * io.HLS_RES_M)
                rows.append({
                    "plot": p["plot"], "status": p["status"], "radius_m": r,
                    "hls_pixel": f"{col}_{row}", "hls_col": col, "hls_row": row,
                    "pix_centre_lat": clat, "pix_centre_lon": clon,
                    "overlap_m2": inter.area,
                    "overlap_frac": inter.area / circle.area,
                })

    cw = pd.DataFrame(rows)
    cw["rank"] = cw.groupby("plot")["overlap_frac"].rank(ascending=False, method="first").astype(int)
    cw["is_dominant"] = cw["rank"] == 1
    cw["n_pixels_touched"] = cw.groupby("plot")["hls_pixel"].transform("size")
    cw["fully_inside"] = cw.groupby("plot")["overlap_frac"].transform("max") >= 1.0 - 1e-9
    cw["epoch"] = epoch
    cw["grid_verified"] = GRID_ANCHOR_VERIFIED
    cw["grid_anchor"] = "utm18n_origin"
    return cw.sort_values(["plot", "rank"], ignore_index=True)


def verify_grid_anchor(geotransform: tuple[float, ...]) -> tuple[bool, str]:
    """Check a real HLS granule's geotransform against the assumed anchor.

    Pass the rasterio ``dataset.transform`` as (a, b, c, d, e, f); c and f are
    the upper-left x and y. The assumption holds only if both are multiples of
    30 m, which is what makes ``floor(E/30)`` equal the true pixel column.
    """
    ul_x, ul_y = geotransform[2], geotransform[5]
    ok = abs(ul_x % io.HLS_RES_M) < 1e-6 and abs(ul_y % io.HLS_RES_M) < 1e-6
    return ok, (f"UL=({ul_x}, {ul_y}); x%30={ul_x % io.HLS_RES_M:.6f}, "
                f"y%30={ul_y % io.HLS_RES_M:.6f}")


# --------------------------------------------------------------------------
# stage runner
# --------------------------------------------------------------------------

def run(reg: pd.DataFrame) -> dict[str, pd.DataFrame]:
    # --- B1: HLS, primary (epoch-correct radii) and the hf375 area variant ---
    primary = hls_overlaps(reg, epoch="post2001")
    variant = hls_overlaps(reg, radius_override=io.PLOT_RADIUS_ALT_M)
    v0_like = hls_overlaps(reg, radius_override=io.PLOT_RADIUS_M)

    def inside_set(cw):
        return set(cw.loc[cw.fully_inside, "plot"])

    flips = pd.DataFrame({
        "plot": sorted(set(reg["plot"])),
    })
    flips["inside_epoch_radius"] = flips["plot"].isin(inside_set(primary))
    flips["inside_r10_flat"] = flips["plot"].isin(inside_set(v0_like))
    flips["inside_r9723_hf375"] = flips["plot"].isin(inside_set(variant))
    flips["flips"] = flips[["inside_epoch_radius", "inside_r10_flat",
                            "inside_r9723_hf375"]].nunique(axis=1) > 1

    # --- B2: MODIS, authoritative ---
    cells = modis_cell(reg["lat"].to_numpy(), reg["lon"].to_numpy())
    modis = pd.concat([reg[["plot", "status"]].reset_index(drop=True), cells], axis=1)
    modis["modis_cell"] = (modis["sample"] + modis["h"] * MODIS_CELLS_PER_TILE).astype(str) \
        + "_" + (modis["line"] + modis["v"] * MODIS_CELLS_PER_TILE).astype(str)
    modis["appeears_pixel"] = [
        APPEEARS_PIXELS.get((l, s), "NOT_DOWNLOADED")
        for l, s in zip(modis["line"], modis["sample"])
    ]
    modis["grid_validated_against"] = "AppEEARS MODIS_Tile/Line_Y/Sample_X"

    reverse = (primary.groupby("hls_pixel")
               .agg(n_plots=("plot", "nunique"),
                    plots=("plot", lambda s: ",".join(sorted(set(s)))),
                    total_overlap_m2=("overlap_m2", "sum"))
               .reset_index())

    io.write(primary, "crosswalk_plot_to_hls.csv")
    io.write(reverse, "crosswalk_hls_to_plot.csv")
    io.write(variant, "crosswalk_plot_to_hls_r9723.csv")
    io.write(flips, "hls_fully_inside_flips.csv")
    io.write(modis, "crosswalk_plot_to_modis.csv")

    io.record(
        stage="B",
        inputs=["hf375_plots", "eml_hf069", "modis_main"],
        params={
            "hls_res_m": io.HLS_RES_M, "hls_grid_anchor": "utm18n_origin",
            "hls_grid_verified": GRID_ANCHOR_VERIFIED,
            "hls_grid_anchor_evidence": GRID_ANCHOR_EVIDENCE,
            "hls_tile": io.HLS_TILE,
            "radii": {"tower": 10.0, "harvest_post2001": 15.0,
                      "hf375_area_variant": io.PLOT_RADIUS_ALT_M},
            "modis_cell_m": MODIS_CELL_M,
            "modis_grid_validated": [r[1] for r in validate_modis_grid()],
        },
        outputs=["crosswalk_plot_to_hls.csv", "crosswalk_hls_to_plot.csv",
                 "crosswalk_plot_to_hls_r9723.csv", "hls_fully_inside_flips.csv",
                 "crosswalk_plot_to_modis.csv"],
        notes="MODIS grid validated against AppEEARS line/sample for all 5 pixels. "
              "HLS grid anchor VERIFIED from CMR ULX/ULY: " + GRID_ANCHOR_EVIDENCE,
    )
    return {"hls": primary, "hls_reverse": reverse, "hls_variant": variant,
            "flips": flips, "modis": modis}
