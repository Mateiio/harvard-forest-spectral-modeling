"""Load the six AppEEARS point-sample bundles into the S1 pixel frame.

AppEEARS does two things the native-COG path does not, and both must be
respected rather than repeated:

  * **it has already applied the scale factors.** Values arrive as reflectance
    in 0-1, not int16. Running :func:`s1.schema.decode` over them would divide
    by 10,000 a second time.
  * **but it does NOT convert fill values.** Reflectance fill arrives as a
    literal ``-9999.0`` and angle fill as a literal ``40000`` -- neither blank
    nor NaN. Left alone, a -9999 reflectance sails straight into an NDVI and a
    40000-degree view zenith into any angular analysis. Both are converted here,
    using the two *different* fill values the two quantity types actually use.
  * **it has already decoded the Fmask bits** into named columns. The raw
    integer is kept too, so :mod:`s1.qa` can decode it independently and the two
    can be compared -- an external check on the Table 9 implementation. Note
    AppEEARS names one column ``Fmask_Cirrus_/_Reserved,_but_not_used``, which
    is the provider confirming bit 0 is inert in v2.0.

One trap: **AppEEARS strips the underscore from the point ID.** The pixel
``24393_157112`` comes back as ``24393157112``. Rather than guess a split
position, the mapping is rebuilt from the very file that was uploaded.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path

import numpy as np
import pandas as pd

from s1 import io as sio, schema

DATA = Path(r"c:\crtusers\matei\prj\data")
BUNDLE_GLOB = str(DATA / "HLSV2*" / "*" / "*-results.csv")

# AppEEARS' pre-decoded QA columns -> the names s1.qa uses
APPEEARS_QA = {
    "Fmask_Cloud": "cloud",
    "Fmask_Cloud_shadow": "cloud_shadow",
    "Fmask_Adjacent_to_cloud/shadow": "adjacent_cloud_shadow",
    "Fmask_Snow/ice": "snow_ice",
    "Fmask_Water": "water",
}


def pixel_id_map() -> dict[int, str]:
    """AppEEARS' underscore-stripped ID -> WP0's hls_pixel id."""
    pts = pd.read_csv(sio.OUT / "appeears_hls_pixel_centres.csv")
    return {int(str(p).replace("_", "")): p for p in pts["ID"]}


def _norm(df: pd.DataFrame, product: str) -> pd.DataFrame:
    prefix = f"HLS{product[0]}30_020_"
    ren = {c: c[len(prefix):] for c in df.columns if c.startswith(prefix)}
    return df.rename(columns=ren)


def _fill_to_nan(s: pd.Series, fill: float) -> pd.Series:
    """AppEEARS passes fill through unconverted; reflectance and angles differ."""
    v = pd.to_numeric(s, errors="coerce")
    return v.mask(np.isclose(v, fill))


def _bits(s: pd.Series) -> pd.Series:
    """'0b11' / '0b0' -> int."""
    return pd.to_numeric(s.astype(str).str.replace("0b", "", regex=False),
                         errors="coerce").fillna(-1).astype(int).map(
        lambda v: int(str(v), 2) if v >= 0 else -1)


def load_bundles(pattern: str = BUNDLE_GLOB) -> pd.DataFrame:
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"no AppEEARS results under {pattern}")
    idmap = pixel_id_map()

    frames = []
    for f in files:
        product = "L30" if "HLSL30" in f else "S30"
        raw = pd.read_csv(f, low_memory=False)
        raw = raw[[c for c in raw.columns if not c.endswith("_Description")]]
        d = _norm(raw, product)

        d["product"] = product
        d["hls_pixel"] = d["ID"].astype("int64").map(idmap)
        if d["hls_pixel"].isna().any():
            bad = d.loc[d["hls_pixel"].isna(), "ID"].unique()[:3]
            raise ValueError(f"unmapped AppEEARS IDs in {f}: {bad}")
        d["date"] = pd.to_datetime(d["Date"]).dt.strftime("%Y-%m-%d")

        # the two index bands, under a product-neutral name
        d["red"] = _fill_to_nan(d[schema.RED_BAND[product]], schema.REF_FILL)
        d["nir"] = _fill_to_nan(d[schema.NIR_BAND[product]], schema.REF_FILL)
        d["cirrus_reflectance"] = _fill_to_nan(d[schema.CIRRUS_BAND[product]],
                                               schema.REF_FILL)
        for ang in ("SZA", "SAA", "VZA", "VAA"):
            d[ang] = _fill_to_nan(d[ang], schema.ANG_FILL)

        d["fmask_raw"] = pd.to_numeric(d["Fmask"], errors="coerce")
        d["aerosol_level_appeears"] = _bits(d["Fmask_Aerosol_level"])
        for src, dst in APPEEARS_QA.items():
            d[f"{dst}_appeears"] = _bits(d[src]).astype("Int8")
        d["cirrus_bit_appeears"] = _bits(d["Fmask_Cirrus_/_Reserved,_but_not_used"])

        keep = (["hls_pixel", "date", "product", "Latitude", "Longitude", "HLS_Tile",
                 "red", "nir", "cirrus_reflectance", "SZA", "SAA", "VZA", "VAA",
                 "fmask_raw", "aerosol_level_appeears", "cirrus_bit_appeears"]
                + [f"{v}_appeears" for v in APPEEARS_QA.values()])
        frames.append(d[keep])

    out = pd.concat(frames, ignore_index=True)
    out = out.rename(columns={"SZA": "sza", "SAA": "saa", "VZA": "vza", "VAA": "vaa",
                              "Latitude": "lat", "Longitude": "lon"})
    return out.sort_values(["date", "product", "hls_pixel"], ignore_index=True)


def attach_manifest(pix: pd.DataFrame) -> pd.DataFrame:
    """Add platform / l1c_baseline / sensing time from the CMR manifest."""
    man = pd.read_csv(sio.OUT / "granule_manifest.csv")
    man = man[["date", "product", "granule_ur", "platform", "l1c_baseline",
               "processing_baseline", "sensing_time_utc", "cloud_coverage_tile_pct",
               "spatial_coverage_pct", "n_sensing_times", "sensing_span_s"]]
    # a date can host two granules of the same product; keep the first
    man = man.drop_duplicates(["date", "product"], keep="first")
    return pix.merge(man, on=["date", "product"], how="left")


def validate_qa(pix: pd.DataFrame) -> list[tuple[str, bool, str]]:
    """Compare s1.qa's Table 9 decode against AppEEARS' own decoding.

    Fill rows are excluded, because AppEEARS decodes the QA fill value 255 as
    ``0b11111111`` -- cloud, shadow, adjacent, snow, water, high aerosol *and*
    the inert cirrus bit all set at once -- rather than recognising it as "no
    data". On real rows the two implementations agree exactly.
    """
    from s1 import qa
    real = pix["fmask_raw"].notna() & (pix["fmask_raw"] != schema.QA_FILL)
    fill = pix["fmask_raw"] == schema.QA_FILL
    mine = qa.decode(pix.loc[real, "fmask_raw"].to_numpy().astype(int))

    res = []
    for name in APPEEARS_QA.values():
        theirs = pix.loc[real, f"{name}_appeears"].to_numpy()
        agree = (mine[name].astype(int) == theirs).mean()
        res.append((f"Fmask bit '{name}' matches AppEEARS", agree == 1.0,
                    f"{100 * agree:.4f}% of {int(real.sum()):,} real rows"))
    aer = pix.loc[real, "aerosol_level_appeears"].to_numpy()
    res.append(("aerosol level matches AppEEARS",
                bool((mine["aerosol_level"] == aer).all()),
                f"{100 * (mine['aerosol_level'] == aer).mean():.4f}%"))
    res.append(("cirrus bit 0 never set on any real observation",
                bool((pix.loc[real, "cirrus_bit_appeears"] == 0).all()),
                f"0 of {int(real.sum()):,} -- bit 0 is inert in v2.0, as Table 9 says"))
    res.append(("AppEEARS decodes QA fill 255 as every flag set",
                bool(fill.sum() > 0
                     and (pix.loc[fill, "cloud_appeears"] == 1).all()),
                f"{int(fill.sum())} fill rows; s1.qa treats them as no-data instead"))
    res.append(("reflectance fill -9999 converted to NaN",
                bool(pix.loc[fill, "red"].isna().all()),
                f"{int(fill.sum())} rows"))
    return res
