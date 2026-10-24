"""Stage A: the plot centroid registry -- the single source of truth for geometry.

hf375-02 is a *centroid* table, not a polygon layer: one WGS84 lat/lon per plot
plus a scalar ``AreaGISm2``. Plot footprints are therefore reconstructed as
circles from the radius stated in hf069.xml, and the two archive sources
disagree about how big that circle is (see :data:`RADIUS_CONFLICT`).

Plot status and radius both come from the hf069.xml abstract, which is more
specific than the program document:

    "In 2001, we removed three plots (G3, H3, H4) ... due to their inundation
    by a beaver pond. In 1999, we installed 6 additional circular, 10 m radius
    biometric plots on the Simes Lot ... In the summer of 2001, we expanded the
    harvested plots in size to 15 m radius and ceased measurements at one plot
    (X4) because it was unaffected by the harvest. The harvest also affected
    three of the original tower plots (A4, A5, B5), which were expanded in size
    as a part of the harvest plot group. Consequently, there are 34 tower plots
    and 8 harvest plots."

Two consequences the program document misses, and that v0 did not implement:

  * the harvest group is **15 m radius from summer 2001**, not 10 m, so a single
    global radius is wrong for A4/A5/B5 and X1-X6;
  * **X4 ceased measurement in 2001** and is not part of the active 8.
"""

from __future__ import annotations

import pandas as pd
from pyproj import Geod, Transformer

from wp0 import io

GEOD = Geod(ellps="WGS84")

# hf069.xml abstract. Dates are the archive's own wording ("in 2001",
# "in the summer of 2001"); day precision is not stated, so July 1 is used as a
# stable midpoint and recorded as an assumption rather than a fact.
BEAVER = {"G3", "H3", "H4"}
MOVED_TO_HARVEST = {"A4", "A5", "B5"}
SIMES = {"X1", "X2", "X3", "X4", "X5", "X6"}
HARVEST_CEASED = {"X4"}
HARVEST_EXPANSION_DATE = "2001-07-01"

TOWER_RADIUS_M = 10.0      # hf069.xml, unchanged throughout
HARVEST_RADIUS_M = 15.0    # hf069.xml, from summer 2001

RADIUS_CONFLICT = (
    "hf069.xml states 10 m radius (= 314.16 m2) for the tower plots; hf375-02 "
    "gives AreaGISm2 = 297 for all 46 EMS rows (= 9.7228 m radius), and gives "
    "297 for the harvest plots too even though hf069.xml expanded them to 15 m "
    "(= 706.86 m2) in 2001. hf069.xml is the measurement protocol and is "
    "preferred; hf375-02's AreaGISm2 is carried as a variant."
)


def _status(plot: str) -> str:
    if plot in BEAVER:
        return "dropped_beaver_2001"
    if plot in MOVED_TO_HARVEST:
        return "moved_to_harvest_2001"
    if plot in HARVEST_CEASED:
        return "harvest_ceased_2001"
    if plot in SIMES:
        return "harvest_active"
    return "active_tower"


def _radius(plot: str) -> tuple[float, float]:
    """(radius before summer 2001, radius after) in metres."""
    if plot in MOVED_TO_HARVEST or plot in SIMES:
        return TOWER_RADIUS_M, HARVEST_RADIUS_M
    return TOWER_RADIUS_M, TOWER_RADIUS_M


def build() -> pd.DataFrame:
    plots = io.read_raw("hf375_plots")
    ems = plots[plots["NAME"].astype("string").str.startswith("EMS ", na=False)].copy()
    ems["plot"] = ems["NAME"].str.removeprefix("EMS ").str.strip()

    if len(ems) != 46:
        raise ValueError(f"expected 46 EMS rows in hf375-02, found {len(ems)}")

    tx = Transformer.from_crs("EPSG:4326", f"EPSG:{io.EPSG_UTM18N}", always_xy=True)
    east, north = tx.transform(ems["Longitude"].to_numpy(), ems["Latitude"].to_numpy())

    # Forward azimuth tower -> plot, and geodesic distance, on the WGS84
    # ellipsoid that hf375.xml declares.
    az, _, dist = GEOD.inv(
        [io.TOWER_LON] * len(ems), [io.TOWER_LAT] * len(ems),
        ems["Longitude"].to_numpy(), ems["Latitude"].to_numpy(),
    )

    reg = pd.DataFrame({
        "plot": ems["plot"].to_numpy(),
        "status": [_status(p) for p in ems["plot"]],
        "group": ["harvest" if p in SIMES or p in MOVED_TO_HARVEST else "tower"
                  for p in ems["plot"]],
        "lat": ems["Latitude"].to_numpy(),
        "lon": ems["Longitude"].to_numpy(),
        "datum": io.DATUM,
        "utm18n_e": east,
        "utm18n_n": north,
        "bearing_from_tower_deg": (pd.Series(az) % 360.0).to_numpy(),
        "dist_from_tower_m": dist,
        "transect": [p[0] if p[0] != "X" else "X" for p in ems["plot"]],
        "radius_m_pre2001": [_radius(p)[0] for p in ems["plot"]],
        "radius_m_post2001": [_radius(p)[1] for p in ems["plot"]],
        "radius_m_hf375_area": (ems["AreaGISm2"].to_numpy() / 3.141592653589793) ** 0.5,
        "area_gis_m2_hf375": ems["AreaGISm2"].to_numpy(),
    }).sort_values("plot", ignore_index=True)

    return reg


def checks(reg: pd.DataFrame) -> list[tuple[str, bool, str]]:
    """Two-key checks. Each is verified against a source outside v0/."""
    counts = reg["status"].value_counts()
    grid = reg[reg["plot"].str.match(r"^[A-H][1-5]$")]
    a1 = reg.loc[reg["plot"] == "A1"].iloc[0]
    return [
        ("46 EMS rows in hf375-02", len(reg) == 46, f"{len(reg)}"),
        ("40 grid plots A1-H5", len(grid) == 40, f"{len(grid)}"),
        ("6 Simes plots X1-X6", len(reg[reg['plot'].str.match(r'^X[1-6]$')]) == 6, ""),
        ("34 active tower plots (hf069.xml)",
         counts.get("active_tower", 0) == 34, f"{counts.get('active_tower', 0)}"),
        ("8 harvest plots (hf069.xml)",
         counts.get("harvest_active", 0) + counts.get("moved_to_harvest_2001", 0)
         + counts.get("harvest_ceased_2001", 0) == 9,
         "6 Simes + 3 moved = 9 rows; hf069.xml says 8 active because X4 ceased"),
        ("A1 == hf375-02 raw coordinate",
         (round(a1["lat"], 6), round(a1["lon"], 6)) == (42.537359, -72.171761),
         f"{a1['lat']}, {a1['lon']}"),
        ("8 lettered transects, not the ten hf069.xml claims",
         grid["transect"].nunique() == 8, f"{sorted(grid['transect'].unique())}"),
    ]


def run() -> pd.DataFrame:
    reg = build()
    io.write(reg, "plot_centroid_registry.csv")
    io.record(
        stage="A",
        inputs=["hf375_plots", "hf375_points", "eml_hf069", "eml_hf375"],
        params={
            "tower": [io.TOWER_LAT, io.TOWER_LON],
            "datum": io.DATUM,
            "crs": f"EPSG:{io.EPSG_UTM18N}",
            "harvest_expansion_date": HARVEST_EXPANSION_DATE,
            "radius_conflict": RADIUS_CONFLICT,
        },
        outputs=["plot_centroid_registry.csv"],
        notes="Status and radii from the hf069.xml abstract, not the program doc. "
              "Harvest group is 15 m radius from summer 2001; X4 ceased in 2001.",
    )
    return reg
