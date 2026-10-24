"""Export the S1 download footprint as KML for Google Earth Pro.

Draws what is actually being requested, as geometry rather than as pins:

  * the **95 HLS pixels** as true 30 m squares on the T18TYN grid, shaded by how
    much of a plot each one captures;
  * the **40 biometry plots** as circles at their surveyed radius (10 m for the
    tower plots, 15 m for the harvest group after 2001);
  * the EMS tower.

Each pixel square is built by transforming its four UTM corners individually
rather than projecting a centre and offsetting, and each plot circle by 72
points around its rim, so the outlines are correct on the globe rather than
approximately correct.

Google Earth Pro's marker clustering is what makes the AppEEARS preview look
like a spiral; polygons are not clustered, so this shows the real lattice.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pyproj import Transformer

from s1 import io as sio, schema

TO_WGS84 = Transformer.from_crs(f"EPSG:{schema.EPSG}", "EPSG:4326", always_xy=True)
TOWER = (-72.171479, 42.537764)

# KML colours are aabbggrr, not rrggbb. Sequential blue ramp, low -> high overlap.
PIXEL_BINS = [(0.05, "5bfbe2cd"), (0.20, "60f4c59e"), (0.40, "70ece76d"),
              (0.60, "78e58739"), (0.80, "82d6782a"), (1.01, "8c6b3610")]
PLOT_COLOR = "ff3468eb"        # orange outline
GRID_LINE = "ff909090"


def _style(sid: str, line: str, fill: str | None, width: float = 1.2) -> str:
    poly = (f"<PolyStyle><color>{fill}</color><fill>1</fill><outline>1</outline></PolyStyle>"
            if fill else "<PolyStyle><fill>0</fill><outline>1</outline></PolyStyle>")
    return (f'<Style id="{sid}"><LineStyle><color>{line}</color>'
            f"<width>{width}</width></LineStyle>{poly}</Style>")


def _poly(coords: list[tuple[float, float]], style: str, name: str, desc: str) -> str:
    ring = " ".join(f"{lon:.8f},{lat:.8f},0" for lon, lat in coords)
    return (f"<Placemark><name>{name}</name><description><![CDATA[{desc}]]></description>"
            f"<styleUrl>#{style}</styleUrl><Polygon><altitudeMode>clampToGround</altitudeMode>"
            f"<outerBoundaryIs><LinearRing><coordinates>{ring}</coordinates>"
            f"</LinearRing></outerBoundaryIs></Polygon></Placemark>")


def _pixel_ring(col: int, row: int) -> list[tuple[float, float]]:
    r = schema.RES_M
    corners = [(col * r, row * r), ((col + 1) * r, row * r),
               ((col + 1) * r, (row + 1) * r), (col * r, (row + 1) * r),
               (col * r, row * r)]
    return [TO_WGS84.transform(x, y) for x, y in corners]


def _circle_ring(e: float, n: float, radius: float, k: int = 72):
    th = np.linspace(0, 2 * np.pi, k + 1)
    return [TO_WGS84.transform(e + radius * np.cos(t), n + radius * np.sin(t)) for t in th]


def _bin_style(frac: float) -> str:
    for i, (hi, _) in enumerate(PIXEL_BINS):
        if frac < hi:
            return f"px{i}"
    return f"px{len(PIXEL_BINS) - 1}"


def build() -> str:
    reg = sio.read_wp0("plot_registry")
    cw = sio.read_wp0("crosswalk_hls")
    grid = cw[cw["plot"].str.match(r"^[A-H][1-5]$")]
    plots = reg[reg["plot"].str.match(r"^[A-H][1-5]$")]

    styles = "".join(_style(f"px{i}", "ff707070", c, 1.0)
                     for i, (_, c) in enumerate(PIXEL_BINS))
    styles += _style("plot", PLOT_COLOR, None, 2.0)
    styles += ('<Style id="tower"><IconStyle><scale>1.2</scale><Icon>'
               "<href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href>"
               "</Icon></IconStyle></Style>")

    # --- pixels ---
    per_pixel = (grid.groupby("hls_pixel")
                 .apply(lambda g: pd.Series({
                     "max_overlap": g["overlap_frac"].max(),
                     "n_plots": g["plot"].nunique(),
                     "detail": ", ".join(f"{r['plot']} {r['overlap_frac']:.3f}"
                                         for _, r in g.sort_values(
                                             "overlap_frac", ascending=False).iterrows()),
                 }), include_groups=False)
                 .reset_index())

    pix_parts = []
    for _, r in per_pixel.iterrows():
        col, row = (int(v) for v in r["hls_pixel"].split("_"))
        lon, lat = TO_WGS84.transform((col + 0.5) * schema.RES_M,
                                      (row + 0.5) * schema.RES_M)
        desc = (f"<b>HLS pixel {r['hls_pixel']}</b><br/>"
                f"tile {schema.TILE}, 30 m, EPSG:{schema.EPSG}<br/>"
                f"centre {lat:.6f}, {lon:.6f}<br/><br/>"
                f"covers {int(r['n_plots'])} plot(s)<br/>"
                f"overlap fraction: {r['detail']}")
        pix_parts.append(_poly(_pixel_ring(col, row), _bin_style(r["max_overlap"]),
                               r["hls_pixel"], desc))

    # --- plots ---
    dom = grid[grid["is_dominant"]].set_index("plot")
    plot_parts = []
    for _, p in plots.iterrows():
        name = p["plot"]
        n_px = int(grid[grid["plot"] == name]["hls_pixel"].nunique())
        d = dom.loc[name] if name in dom.index else None
        desc = (f"<b>Biometry plot {name}</b><br/>"
                f"status {p['status']}<br/>"
                f"radius {p['radius_m_post2001']:.0f} m "
                f"(area {np.pi * p['radius_m_post2001'] ** 2:.0f} m2)<br/>"
                f"transect {p['transect']}, "
                f"{p['dist_from_tower_m']:.0f} m from tower at "
                f"{p['bearing_from_tower_deg']:.0f}&#176;<br/><br/>"
                f"touches {n_px} HLS pixel(s)<br/>"
                + (f"dominant pixel {d['hls_pixel']} "
                   f"({d['overlap_frac']:.1%} of the plot)" if d is not None else ""))
        plot_parts.append(_poly(
            _circle_ring(p["utm18n_e"], p["utm18n_n"], p["radius_m_post2001"]),
            "plot", name, desc))

    tower = (f"<Placemark><name>EMS Tower</name><styleUrl>#tower</styleUrl>"
             f"<description>Harvard Forest EMS flux tower (HF004)</description>"
             f"<Point><coordinates>{TOWER[0]:.6f},{TOWER[1]:.6f},0</coordinates></Point>"
             f"</Placemark>")

    legend = "<br/>".join(
        f"{int(100 * (0 if i == 0 else PIXEL_BINS[i-1][0]))}-{int(100 * hi)}% overlap"
        for i, (hi, _) in enumerate(PIXEL_BINS[:-1]))

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        "<name>HF EMS - S1 HLS download footprint</name>"
        f"<description><![CDATA[The {len(per_pixel)} HLS v2.0 pixels S1 requests, "
        f"and the {len(plots)} biometry plots they cover.<br/><br/>"
        f"Pixels are true 30 m squares on tile {schema.TILE}, shaded by how much of "
        f"a plot each captures (darker = more):<br/>{legend}<br/><br/>"
        "Plot circles are drawn at their surveyed radius: 10 m for tower plots, "
        "15 m for the harvest group (A4, A5, B5) after 2001.]]></description>"
        + styles
        + f"<Folder><name>HLS pixels ({len(per_pixel)})</name><open>1</open>"
        + "".join(pix_parts) + "</Folder>"
        + f"<Folder><name>Biometry plots ({len(plots)})</name><open>1</open>"
        + "".join(plot_parts) + "</Folder>"
        + "<Folder><name>Reference</name>" + tower + "</Folder>"
        + "</Document></kml>"
    )


def run(name: str = "hf_ems_s1_hls_footprint.kml"):
    sio.OUT.mkdir(parents=True, exist_ok=True)
    path = sio.OUT / name
    path.write_text(build(), encoding="utf8")
    return path


if __name__ == "__main__":
    print(run())
