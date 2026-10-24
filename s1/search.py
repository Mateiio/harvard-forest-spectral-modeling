"""Stage 0: CMR granule search -> manifest. Needs no credentials.

CMR's granule metadata carries more than a file list, and three fields change
what the rest of S1 can claim:

  * ``SENSING_TIME`` is the real acquisition instant. The timestamp in the
    granule name is **not** -- for S30 it is the time the sensor begins sensing
    the sunlit side of the orbit, not the tile overpass, and the two differ by
    minutes (known issue #10). Every join and every solar-geometry lookup uses
    SENSING_TIME.
  * ``PROCESSING_BASELINE`` (S30) is ESA's L1C baseline. That makes the
    Collection-1 discontinuity in known issue #12 a **measured** property of
    each granule rather than something inferred from its date.
  * ``LANDSAT_PRODUCT_ID`` / ``PRODUCT_URI`` name the platform, so the sensor
    mix (L8/L9/S2A/S2B/S2C) is known per observation. It is not constant:
    Landsat 9 arrives in 2022 and Sentinel-2C in late 2024.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd
import requests

from s1 import schema

CMR = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
PRODUCTS = {"L30": "HLSL30", "S30": "HLSS30"}
VERSION = "2.0"

# The plot network's bounding box, padded. Any granule intersecting this covers
# the 95 pixels the 40 grid plots touch.
BBOX = (-72.180, 42.532, -72.169, 42.542)
# HLS v2.0's Landsat record opens 2013-04-11; HLSS30 does not begin until
# 2015-11-28 globally and 2015-12-20 over this tile, so the two products start
# in different years and CMR simply returns nothing for S30 before then.
START = "2013-01-01T00:00:00Z"

# ESA reprocessed Sentinel-2 L1C into Collection 1 in phases, and HLS V2.0 was
# not rebuilt from either (known issue #12). Baselines are the ESA convention.
C1_PHASE1_END = "2021-12-31"
C1_PHASE2_END = "2023-12-13"


def _platform(attrs: dict) -> str:
    lp = attrs.get("LANDSAT_PRODUCT_ID", "")
    if lp.startswith("LC08"):
        return "L8"
    if lp.startswith("LC09"):
        return "L9"
    uri = attrs.get("PRODUCT_URI", "")
    m = re.match(r"S2([ABC])_", uri)
    if m:
        return f"S2{m.group(1)}"
    return "unknown"


def _l1c_baseline(product: str, sensing: pd.Timestamp, attrs: dict) -> str:
    """Which ESA L1C generation fed this granule."""
    if product == "L30":
        return "n/a_landsat"
    d = sensing.tz_convert("UTC").strftime("%Y-%m-%d")
    if d <= C1_PHASE1_END:
        return "pre_c1"
    if d <= C1_PHASE2_END:
        return "c1_phase1_era"
    return "c1_phase2_era"


def _sensing(raw: str) -> tuple[pd.Timestamp, int, float]:
    """Parse SENSING_TIME, which may list several times joined by ' + '.

    An L30 tile can be mosaicked from two consecutive Landsat scenes along a
    path, and HLS then reports both acquisition times in one field. The plot
    pixels come from exactly one of them and nothing in the metadata says which,
    so the acquisition instant is ambiguous within the reported span. The first
    time is used and the ambiguity is carried as ``sensing_span_s``.
    """
    parts = [p.strip() for p in raw.split("+") if p.strip()]
    ts = sorted(pd.Timestamp(p).tz_convert("UTC") for p in parts)
    span = (ts[-1] - ts[0]).total_seconds() if len(ts) > 1 else 0.0
    return ts[0], len(ts), span


def _query(short_name: str, end: str, page_size: int = 2000) -> list[dict]:
    out, page = [], 1
    while True:
        r = requests.get(CMR, timeout=120, params={
            "short_name": short_name, "version": VERSION,
            "temporal": f"{START},{end}",
            "bounding_box": ",".join(str(v) for v in BBOX),
            "page_size": page_size, "page_num": page,
        })
        r.raise_for_status()
        items = r.json().get("items", [])
        out.extend(items)
        if len(items) < page_size:
            return out
        page += 1


def build(end: str | None = None) -> pd.DataFrame:
    end = end or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for product, short_name in PRODUCTS.items():
        for it in _query(short_name, end):
            u = it["umm"]
            attrs = {a["Name"]: a["Values"][0] for a in u.get("AdditionalAttributes", [])
                     if a.get("Values")}
            ur = u["GranuleUR"]
            sensing, n_sensing, span_s = _sensing(attrs["SENSING_TIME"])
            urls = [x["URL"] for x in u.get("RelatedUrls", [])
                    if x.get("URL", "").startswith("https") and x["URL"].endswith(".tif")]
            base = urls[0].rsplit(".", 2)[0] if urls else ""
            rows.append({
                "granule_ur": ur,
                "product": product,
                "tile": attrs.get("MGRS_TILE_ID", ""),
                # the granule-name timestamp is orbit start for S30, not overpass
                "name_timestamp": re.search(r"\.(\d{7}T\d{6})\.", ur).group(1),
                "sensing_time_utc": sensing,
                "n_sensing_times": n_sensing,
                "sensing_span_s": span_s,
                "date": sensing.strftime("%Y-%m-%d"),
                "year": sensing.year,
                "platform": _platform(attrs),
                "l1c_baseline": _l1c_baseline(product, sensing, attrs),
                "processing_baseline": attrs.get("PROCESSING_BASELINE", ""),
                "accode": attrs.get("ACCODE", ""),
                "cloud_coverage_tile_pct": pd.to_numeric(
                    attrs.get("CLOUD_COVERAGE"), errors="coerce"),
                "spatial_coverage_pct": pd.to_numeric(
                    attrs.get("SPATIAL_COVERAGE"), errors="coerce"),
                "ulx": pd.to_numeric(attrs.get("ULX"), errors="coerce"),
                "uly": pd.to_numeric(attrs.get("ULY"), errors="coerce"),
                "cs_name_reported": attrs.get("HORIZONTAL_CS_NAME", ""),
                "mean_sza": pd.to_numeric(attrs.get("MEAN_SUN_ZENITH_ANGLE"), errors="coerce"),
                "mean_vza": pd.to_numeric(attrs.get("MEAN_VIEW_ZENITH_ANGLE"), errors="coerce"),
                "angle_provenance": schema.ANGLE_PROVENANCE[product],
                "url_base": base,
            })
    df = pd.DataFrame(rows).sort_values("sensing_time_utc", ignore_index=True)
    df["fmask_aux_deficient_2021"] = df["date"].between("2021-01-01", "2021-12-31")
    return df


def layer_url(url_base: str, layer_name: str) -> str:
    return f"{url_base}.{layer_name}.tif"


def density(man: pd.DataFrame) -> pd.DataFrame:
    """Observations per year per product per platform -- not stationary."""
    d = (man.groupby(["year", "product", "platform"]).size()
         .rename("n_granules").reset_index())
    tot = man.groupby("year").size().rename("n_total").reset_index()
    return d.merge(tot, on="year")


def _name_time_mismatch(man: pd.DataFrame) -> int:
    """How many granules whose filename timestamp is not the acquisition time."""
    name = pd.to_datetime(man["name_timestamp"], format="%Y%jT%H%M%S", utc=True)
    return int((abs((man["sensing_time_utc"] - name).dt.total_seconds()) > 60).sum())


def checks(man: pd.DataFrame) -> list[tuple[str, bool, str]]:
    n = man.groupby("product").size()
    tiles = set(man["tile"])
    ulx, uly = set(man["ulx"].dropna()), set(man["uly"].dropna())
    bad_crs = man[~man["cs_name_reported"].str.contains("18", na=False)]
    return [
        ("HLSL30 granule count >= 614", n.get("L30", 0) >= 614, str(n.get("L30", 0))),
        ("HLSS30 granule count >= 484", n.get("S30", 0) >= 484, str(n.get("S30", 0))),
        ("single tile T18TYN", tiles == {"18TYN"}, str(tiles)),
        ("tile origin is constant", len(ulx) == 1 and len(uly) == 1,
         f"ULX={ulx} ULY={uly}"),
        ("tile origin lands on the 30 m grid",
         all(abs(v % schema.RES_M) < 1e-6 for v in list(ulx) + list(uly)),
         f"{schema.TILE_ULX % 30}, {schema.TILE_ULY % 30}"),
        ("granule-name timestamp is not the acquisition time",
         _name_time_mismatch(man) > 0,
         f"{_name_time_mismatch(man)} granules disagree -- known issue #10, "
         "never parse the filename time"),
        ("CMR HORIZONTAL_CS_NAME is unreliable", len(bad_crs) > 0,
         f"{len(bad_crs)} granules do not report zone 18"),
    ]


def run(end: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    from s1 import io as sio
    man = build(end)
    dens = density(man)
    sio.write(man, "granule_manifest.csv")
    sio.write(dens, "observation_density.csv")
    sio.record("S1-0", inputs=[], params={
        "cmr": CMR, "version": VERSION, "bbox": list(BBOX), "start": START,
        "end": end or "now", "n_granules": int(len(man)),
        "per_product": {k: int(v) for k, v in man.groupby("product").size().items()},
    }, outputs=["granule_manifest.csv", "observation_density.csv"],
        notes="CMR search, no credentials required.")
    return man, dens
