"""Emit the rebuild in HF365's own file shape.

`hf365_v2_candidate.csv` is long -- one row per plot per acquisition, carrying
masking state, angles and granule provenance. That is the right shape to work
from, but it is not the shape the archive publishes, so anyone with code written
against HF365 cannot read it.

This writes the same values back into HF365's layout: three CSVs, one per index,
each `date` plus one column per plot, one row per date.

Two decisions the wide layout forces, both recorded rather than hidden:

* **Same-day sensor overlap.** A wide date-by-plot table has one slot per date,
  but 21 of the 411 usable dates carry both a Landsat and a Sentinel-2 image.
  Landsat wins, because HLS bandpass-adjusts Sentinel-2 *onto* the Landsat 8
  reference -- so Landsat is the native scale and Sentinel-2 the converted one.
  On those dates the two agree to a median 0.010 NDVI anyway. Which product
  supplied each date is written to ``hf365_v2-04-source.csv``; nothing is lost.
* **Missing values are written ``NA``**, matching the archive.
* **The two NEON columns.** HF365 carries `HARV_049` and `HARV_050`; hf375-02
  has no coordinates for them, so they are emitted empty to keep the 42-column
  schema a caller may depend on.
"""

from __future__ import annotations

import pandas as pd

from s1 import io as sio

# HF365's own column order. The archive spells D1 and F1 with a trailing space;
# that is a defect (see wp0/out/archive_corrections.md) and is not reproduced.
GRID = [f"{r}{i}" for r in "ABCDEFGH" for i in range(1, 6)]
NEON = ["HARV_049", "HARV_050"]
PLOT_COLUMNS = GRID + NEON

MEASURES = {"evi2": "hf365_v2-01-hls-evi2.csv",
            "ndvi": "hf365_v2-02-hls-ndvi.csv",
            "nirv": "hf365_v2-03-hls-nirv.csv"}
QUALITY_FILE = "hf365_v2-05-hls-coverage.csv"
PRODUCT_PRIORITY = ["L30", "S30"]   # Landsat first -- the harmonisation target
DECIMALS = 6                        # the archive stores 3; that floor cost us dearly


def _resolved(convention: str = "single") -> pd.DataFrame:
    """Usable plot-observations, one per (date, plot), Landsat preferred."""
    c = pd.read_csv(sio.OUT / "hf365_v2_candidate.csv", low_memory=False)
    flag = "single_usable" if convention == "single" else "weight_coverage"
    keep = c[flag].astype(bool) if convention == "single" else c[flag].fillna(0) > 0
    u = c[keep].copy()
    u["_rank"] = u["product"].map({p: i for i, p in enumerate(PRODUCT_PRIORITY)})
    return (u.sort_values(["date", "plot", "_rank"])
             .drop_duplicates(["date", "plot"], keep="first"))


def wide(measure: str, convention: str = "single") -> pd.DataFrame:
    u = _resolved(convention)
    t = (u.pivot(index="date", columns="plot", values=f"{measure}_{convention}")
          .reindex(columns=PLOT_COLUMNS)      # adds the empty NEON columns
          .round(DECIMALS)
          .reset_index())
    t.columns.name = None
    return t


def coverage(convention: str = "single") -> pd.DataFrame:
    """Per-cell quality: the fraction of the plot the surviving pixels cover.

    HF365 ships no quality field at all -- a value is either present or NA,
    with no way to tell a whole-plot observation from one built on a corner of
    it. This is that missing number, on the same date-by-plot grid as the
    indices, so a cell here lines up with the cell in the index files.

    1.0 means every pixel touching the plot passed masking. Lower means part of
    the plot was cloud, shadow, snow, water or high aerosol and the remaining
    pixels were renormalised to cover it. Blank where the index is blank.
    """
    u = _resolved(convention)
    col = "weight_coverage" if convention == "single" else "weight_coverage"
    t = (u.pivot(index="date", columns="plot", values=col)
          .reindex(columns=PLOT_COLUMNS)
          .round(4)
          .reset_index())
    t.columns.name = None
    return t


def source_table(convention: str = "single") -> pd.DataFrame:
    s = (_resolved(convention).groupby("date")
           .agg(product=("product", "first"), platform=("platform", "first"),
                n_plots=("plot", "nunique"))
           .reset_index())
    # count the overlap on the *unresolved* frame -- after dedup the dropped
    # product is gone and cannot be counted
    c = pd.read_csv(sio.OUT / "hf365_v2_candidate.csv", low_memory=False)
    flag = "single_usable" if convention == "single" else "weight_coverage"
    keep = c[flag].astype(bool) if convention == "single" else c[flag].fillna(0) > 0
    n_prod = c[keep].groupby("date")["product"].nunique()
    s["same_day_alternate_dropped"] = s["date"].map(n_prod).fillna(1).gt(1)
    return s


def checks(tables: dict[str, pd.DataFrame], src: pd.DataFrame) -> list:
    n_dates = len(src)
    res = [("all three indices share one date axis",
            len({len(t) for t in tables.values()}) == 1, f"{n_dates} dates"),
           ("42 plot columns, matching HF365's schema",
            all(list(t.columns) == ["date"] + PLOT_COLUMNS for t in tables.values()),
            f"{len(PLOT_COLUMNS)} plots + date"),
           ("no trailing-space column names",
            all(c == c.strip() for c in tables["ndvi"].columns), "D1/F1 cleaned"),
           ("one row per date",
            all(t["date"].is_unique for t in tables.values()), ""),
           ("the two NEON columns are empty, not fabricated",
            bool(tables["ndvi"][NEON].isna().all().all()), "no coordinates for them")]
    vals = tables["ndvi"][GRID].stack().dropna()   # dropna: blanks are not values
    res.append(("NDVI stays inside [-1, 1]",
                bool(vals.between(-1, 1).all()),
                f"{vals.min():.3f} to {vals.max():.3f} over {len(vals):,} values"))
    return res


def run(convention: str = "single") -> dict:
    tables = {m: wide(m, convention) for m in MEASURES}
    cov = coverage(convention)
    src = source_table(convention)
    # NA, not blank -- HF365 spells its gaps "NA" and a reader should not
    # have to guess whether an empty field means zero or no observation
    for m, name in MEASURES.items():
        sio.write(tables[m], name, na_rep="NA")
    sio.write(src, "hf365_v2-04-source.csv", na_rep="NA")
    sio.write(cov, QUALITY_FILE, na_rep="NA")
    return {"files": list(MEASURES.values()) + ["hf365_v2-04-source.csv", QUALITY_FILE],
            "dates": int(len(src)),
            "plot_columns": len(PLOT_COLUMNS),
            "date_range": [src["date"].min(), src["date"].max()],
            "dates_with_alternate_dropped": int(src["same_day_alternate_dropped"].sum()),
            "checks": checks(tables, src) + _coverage_checks(tables["ndvi"], cov)}


def _coverage_checks(ndvi: pd.DataFrame, cov: pd.DataFrame) -> list:
    a = ndvi.set_index("date")[PLOT_COLUMNS].notna()
    b = cov.set_index("date")[PLOT_COLUMNS].notna()
    v = cov.set_index("date")[GRID].stack().dropna()
    return [("coverage grid aligns cell-for-cell with the indices",
             bool(a.equals(b)), f"{int(a.values.sum()):,} filled cells in both"),
            ("coverage lies in (0, 1]",
             bool(v.gt(0).all() and v.le(1.0).all()),
             f"min {v.min():.4f}, max {v.max():.4f}")]
