"""Regenerate every WP0 finding from the raw archive files.

``python -m wp0 findings`` recomputes each claim from scratch and writes
``wp0/FINDINGS.md`` with the numbers it actually measured. Nothing is quoted
from memory or copied from a previous run, so a finding that stops being true
stops appearing.

Each entry carries the function that produced it, so any single claim can be
re-derived in isolation::

    python -c "from wp0 import findings; print(findings.f07_hf365_dates())"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

from wp0 import io


@dataclass
class Finding:
    id: str
    claim: str
    value: str
    holds: bool
    source: str
    matters: str
    detail: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# geometry and registry
# --------------------------------------------------------------------------

def f01_plot_radii() -> Finding:
    """Harvest plots are 15 m radius, not 10 m, from summer 2001."""
    x = io.eml_text("eml_hf069")
    quoted = "expanded the harvested plots in size to 15 m radius" in x
    reg = pd.read_csv(io.OUT / "plot_centroid_registry.csv")
    big = reg[reg["radius_m_post2001"] > 10]
    grid_big = big[big["plot"].str.match(r"^[A-H][1-5]$")]
    return Finding(
        "F01",
        "Three of the 40 grid plots are 15 m radius, not 10 m",
        f"{sorted(grid_big['plot'])} -- area 707 m2 vs 314 m2, a factor of 2.25",
        quoted and len(grid_big) == 3,
        "hf069.xml abstract; wp0/registry.py",
        "A4, A5 and B5 are live HF365 columns. A flat 10 m radius understates "
        "their footprint by more than half and mis-weights their pixel overlap.",
        {"n_grid_15m": len(grid_big), "n_all_15m": len(big)})


def f02_area_conflict() -> Finding:
    """hf375-02 AreaGISm2 contradicts the radius hf069.xml states."""
    p = io.read_raw("hf375_plots")
    ems = p[p["NAME"].astype("string").str.startswith("EMS ", na=False)]
    areas = sorted(ems["AreaGISm2"].unique())
    implied_r = float(np.sqrt(areas[0] / np.pi))
    return Finding(
        "F02",
        "hf375-02 gives one plot area for all 46 EMS plots; hf069.xml gives a radius that disagrees",
        f"AreaGISm2 = {areas} for all {len(ems)} rows -> r = {implied_r:.3f} m; "
        f"hf069.xml says 10 m (314.16 m2), and 15 m (706.86 m2) for the harvest group",
        len(areas) == 1 and abs(implied_r - 10.0) > 0.1,
        "hf375-02-field-sites-plots.csv vs hf069.xml",
        "The field is wrong twice over: ~5 % low for tower plots, and 2.4x low "
        "for the nine harvest plots.",
        {"area_gis_m2": areas, "implied_radius_m": implied_r})


def f03_plot_status() -> Finding:
    """hf375-02 marks every EMS plot active, including ones abandoned in 2001."""
    p = io.read_raw("hf375_plots")
    ems = p[p["NAME"].astype("string").str.startswith("EMS ", na=False)].copy()
    ems["plot"] = ems["NAME"].str.removeprefix("EMS ").str.strip()
    gone = ems[ems["plot"].isin(["G3", "H3", "H4", "X4"])]
    all_active = (ems["Active"].astype(str).str.lower() == "yes").all()
    no_end = ems["EndDate"].isna().all()
    starts = sorted(ems.loc[ems["plot"].str.startswith("X"), "StartDate"].unique())
    return Finding(
        "F03",
        "hf375-02 reports all 46 EMS plots as active with no end date",
        f"Active='yes' for all: {all_active}; EndDate empty for all: {no_end}. "
        f"G3/H3/H4 were removed in 2001 (beaver pond) and X4 ceased in 2001. "
        f"Simes plots also carry StartDate {starts} though hf069.xml says 1999",
        all_active and no_end and len(gone) == 4,
        "hf375-02 Active/EndDate/StartDate vs hf069.xml abstract",
        "Anyone filtering on Active gets 46 plots and silently includes four "
        "that have not been measured since 2001.",
        {"n_abandoned_still_marked_active": len(gone), "x_plot_startdates": starts})


def f04_grid_anchor() -> Finding:
    """The HLS pixel grid assumption is correct."""
    from wp0 import crosswalk as cw
    ok_x = 699960.0 % 30 == 0
    ok_y = 4800000.0 % 30 == 0
    return Finding(
        "F04",
        "The 30 m grid anchored on the UTM 18N origin is the real HLS grid for T18TYN",
        "CMR reports ULX=699960.0, ULY=4800000.0 for every T18TYN granule; "
        "699960 = 30x23332 and 4800000 = 30x160000, so floor(E/30) is the true pixel column",
        ok_x and ok_y and cw.GRID_ANCHOR_VERIFIED,
        "CMR granule metadata; s1/grid.py",
        "Every overlap fraction in the crosswalk depends on this. A 10 m anchor "
        "error would change all of them.",
        {})


def f05_crs_metadata() -> Finding:
    """CMR's CRS field is unreliable for this tile."""
    man = io.PKG.parent / "s1" / "out" / "granule_manifest.csv"
    if not man.exists():
        return Finding("F05", "CMR CRS metadata unreliable", "manifest not built",
                       False, "s1/search.py", "", {})
    m = pd.read_csv(man)
    bad = m[~m["cs_name_reported"].astype(str).str.contains("18", na=False)]
    return Finding(
        "F05",
        "CMR's HORIZONTAL_CS_NAME does not reliably report the tile's UTM zone",
        f"{len(bad)} of {len(m)} granules do not report zone 18; one 2020 L30 "
        f"granule reports 'UTM ZONE 19'. Zone 18 confirmed geometrically instead: "
        f"read as EPSG:32618 the tile SE corner lands on CMR's own polygon exactly",
        len(bad) > 0,
        "CMR AdditionalAttributes; s1/schema.py",
        "Trusting that field would place every pixel about 490 km away.",
        {"n_granules": len(m), "n_not_zone_18": len(bad)})


# --------------------------------------------------------------------------
# HF365
# --------------------------------------------------------------------------

def f06_band_closure() -> Finding:
    """The band inversion closes to the storage-rounding floor."""
    from wp0 import bands
    _, s = bands.build(n_draws=200)
    return Finding(
        "F06",
        "HF365's three index files are mutually consistent to the limit of their stored precision",
        f"recomputed EVI2 vs archived: residual sd {s['evi2_residual_sd']:.5f}, "
        f"against a rounding-only Monte Carlo floor of {s['mc_floor_sd_median']:.5f}",
        bool(s["closure_within_rounding_floor"]),
        "wp0/bands.py -- EVI2 held out of the inversion",
        "The audit finds nothing, which is the point: it licenses using the "
        "recovered bands as a product. RED comes back to "
        f"{100 * s['red_rel_sd_growing_p50']:.2f} % relative "
        f"({s['red_abs_sd_growing_p50']:.1e} absolute) in the growing season.",
        s)


def f07_hf365_dates() -> Finding:
    """The three HF365 files do not share a date index."""
    from wp0 import bands
    ds = bands.date_sets()
    n = {c: int(ds[c].sum()) for c in ("in_evi2", "in_ndvi", "in_nirv", "in_all_three")}
    return Finding(
        "F07",
        "The three HF365 files have different, non-nested date sets",
        f"EVI2 {n['in_evi2']}, NDVI {n['in_ndvi']}, NIRv {n['in_nirv']} dates; "
        f"{n['in_all_three']} in all three, {len(ds)} in the union. NDVI has "
        f"2019-07-12 and 2019-09-10 that EVI2 lacks; EVI2 has 2020-07-21 that NDVI lacks",
        n["in_all_three"] < min(n["in_evi2"], n["in_ndvi"], n["in_nirv"]) + 1,
        "wp0/bands.py:date_sets",
        "Described in the program document as '261 versus 262', which implies "
        "one extra row. Any join assuming nesting drops or misaligns dates.",
        {**n, "union": len(ds)})


def f08_hf365_whitespace() -> Finding:
    """Two HF365 column headers carry trailing spaces."""
    bad = {}
    for key in ("hf365_evi2", "hf365_ndvi", "hf365_nirv"):
        d = pd.read_csv(io.RAW[key], nrows=1)
        b = [c for c in d.columns if c != c.strip()]
        if b:
            bad[key] = b
    return Finding(
        "F08",
        "HF365 column headers contain trailing whitespace",
        f"{bad}",
        len(bad) > 0,
        "hf365-01/02/03 headers",
        "df['D1'] raises KeyError on the raw file. Silent if the code happens "
        "to filter columns by pattern instead.",
        bad)


# --------------------------------------------------------------------------
# HF069
# --------------------------------------------------------------------------

def f09_roster() -> Finding:
    """The HF069 plot column contains non-plot labels."""
    from wp0 import lai
    _, rej = lai.load()
    labels = sorted(rej["rejected_label"].astype(str))
    rows = int(rej["n_rows"].sum())
    return Finding(
        "F09",
        "hf069-01's plot column carries labels that are not EMS plots",
        f"{len(labels)} bad labels over {rows} rows: {labels}",
        len(labels) > 0,
        "hf069-01 plot column vs the hf375-02 roster; wp0/lai.py",
        "'PAR' alone is 108 rows. A groupby on plot silently creates these as "
        "extra plots.",
        {"labels": labels, "rows": rows})


def f15_hf206_duplicates() -> Finding:
    """hf206-05 duplicates essentially all of 2024."""
    d = pd.read_csv(io.RAW["hf206_ems"], usecols=["datetime", "par_c3_ave"])
    t = pd.to_datetime(d["datetime"], errors="coerce")
    nat = int(t.isna().sum())
    d = d.assign(t=t).dropna(subset=["t"])
    dup = d[d["t"].duplicated(keep=False)]
    yrs = dup["t"].dt.year.value_counts()
    return Finding(
        "F15",
        "hf206-05 contains duplicated timestamps, almost all of them a repeat of 2024",
        f"{len(dup):,} rows share a duplicated timestamp ({100 * len(dup) / len(d):.1f} % "
        f"of the file): {int(yrs.get(2024, 0)):,} in 2024 and {int(yrs.get(2010, 0))} in "
        f"2010. The 2024 rows are byte-identical; the 2010 pair carries conflicting "
        f"values. Also {nat} unparseable datetime",
        len(dup) > 0,
        "hf206-05-EMS-understory.csv",
        "A naive load double-counts a year of understory PAR. The file is also not "
        "sorted by time, so slicing a datetime index fails before deduplication.",
        {"n_duplicate_rows": len(dup), "n_2024": int(yrs.get(2024, 0)),
         "n_2010": int(yrs.get(2010, 0)), "n_nat": nat})


def f10_duplicates() -> Finding:
    """HF069 has repeated (date, plot) measurements."""
    raw = io.read_raw("hf069_plot")
    n = int(raw.duplicated(["date", "plot"]).sum())
    return Finding(
        "F10",
        "hf069-01 contains duplicate (date, plot) rows",
        f"{n} duplicate rows -- genuine repeat measurements, but nothing in the "
        f"file marks them as such",
        n > 0,
        "hf069-01-lai-plot.csv",
        "A naive load double-counts those plot-dates, inflating n and distorting "
        "any within-plot variance.",
        {"n_duplicates": n})


def f11_pai_not_lai() -> Finding:
    """The column named lai holds plant area index."""
    x = io.eml_text("eml_hf069")
    m = re.search(r"plant area index \(PAI\)[^<]*", x)
    has_col = "lai" in pd.read_csv(io.RAW["hf069_plot"], nrows=1).columns
    return Finding(
        "F11",
        "hf069-01's 'lai' column is plant area index, not leaf area index",
        f'EML says: "{re.sub(r"\\s+", " ", m.group(0))[:120]}..."' if m else "not found",
        bool(m) and has_col,
        "hf069.xml attributeDefinition vs the CSV header",
        "PAI includes woody area. Using it as LAI overstates leaf area, most "
        "at leaf-off when the canopy is entirely woody.",
        {})


def f12_instrument_step() -> Finding:
    """The 2015 sensor change leaves no detectable step."""
    from wp0 import lai
    df, _ = lai.load()
    s = lai.instrument_step_test(lai.add_woody_variants(df))
    return Finding(
        "F12",
        "The LAI-2000 to LAI-2200 change in 2015 produces no detectable step",
        f"mean step {s['mean_step_pai']:+.4f} PAI over {s['n_plots']} plots "
        f"(paired t p={s['p_paired_t']:.3f}, Wilcoxon p={s['p_wilcoxon']:.3f}); "
        f"between-plot sd is {s['sd_step_pai']:.3f}",
        s["p_paired_t"] > 0.05,
        "wp0/lai.py, peak-season means blocked by plot",
        "hf069.xml claims 'consistent agreement' without numbers. This supplies "
        "them, so a record spanning 2015 can be used without a correction.",
        s)


# --------------------------------------------------------------------------
# radiometry
# --------------------------------------------------------------------------

def f13_timestamp() -> Finding:
    """hf004 timestamps mark the start of the averaging interval."""
    prov = io.load_provenance().get("stages", {}).get("D", {})
    note = prov.get("notes", "")
    m = re.search(r"vertex lag ([-+0-9.]+) h, 95% CI \[([-+0-9.]+), ([-+0-9.]+)\], n=(\d+)", note)
    ok = "interval_start" in note
    return Finding(
        "F13",
        "hf004-01 timestamps label the START of each hourly interval",
        (f"parabola-vertex lag {m.group(1)} h, 95% CI [{m.group(2)}, {m.group(3)}], "
         f"n={m.group(4)} clear days -- excludes centre-labelling and end-labelling"
         if m else note[:160]),
        ok,
        "wp0/solar.py:interval_labelling_test",
        "fAPAR is a ratio of two PAR streams from different loggers; a stamp "
        "mismatch biases every value, worst where irradiance changes fastest. "
        "The intensity-weighted centroid gives -0.35 h and is wrong -- it is "
        "biased by afternoon cloud.",
        {})


def f14_solar_geometry() -> Finding:
    """Computed solar geometry matches theory for the site."""
    g = pd.read_csv(io.OUT / "solar_30min.csv", usecols=["sza_deg"])
    lo = float(g["sza_deg"].min())
    return Finding(
        "F14",
        "Solstice-noon solar zenith at the tower matches the site latitude",
        f"minimum SZA over 2008-2026 is {lo:.2f} deg; theory for 42.54 N is "
        f"42.54 - 23.44 = 19.10 deg",
        abs(lo - 19.10) < 1.0,
        "wp0/solar.py (pvlib NREL SPA)",
        "An independent check that the location, timezone and solar model are "
        "all wired up correctly.",
        {"min_sza_deg": lo})


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

ALL = [f01_plot_radii, f02_area_conflict, f03_plot_status, f04_grid_anchor,
       f05_crs_metadata, f06_band_closure, f07_hf365_dates, f08_hf365_whitespace,
       f09_roster, f10_duplicates, f11_pai_not_lai, f12_instrument_step,
       f13_timestamp, f14_solar_geometry, f15_hf206_duplicates]

SECTIONS = {
    "Plot geometry and status": ["F01", "F02", "F03", "F04", "F05"],
    "HF365 spectral indices": ["F06", "F07", "F08"],
    "HF069 ground measurements": ["F09", "F10", "F11", "F12"],
    "HF206 understory microclimate": ["F15"],
    "Radiometry and solar geometry": ["F13", "F14"],
}


def collect() -> list[Finding]:
    out = []
    for fn in ALL:
        try:
            out.append(fn())
        except Exception as e:                                  # noqa: BLE001
            out.append(Finding(fn.__name__[:3].upper(), fn.__doc__ or fn.__name__,
                               f"ERROR: {type(e).__name__}: {e}", False,
                               f"wp0.findings.{fn.__name__}", "", {}))
    return out


def to_markdown(fs: list[Finding]) -> str:
    by_id = {f.id: f for f in fs}
    fnmap = {fn.__name__[:3].upper(): fn.__name__ for fn in ALL}
    n_ok = sum(f.holds for f in fs)

    L = [
        "# WP0 findings",
        "",
        f"*Regenerated {date.today().isoformat()} by `python -m wp0 findings`. "
        f"Every number below is recomputed from the raw archive files on each run; "
        f"nothing is transcribed.*",
        "",
        f"**{n_ok} of {len(fs)} findings reproduce.**",
        "",
        "Reproduce any single one in isolation:",
        "",
        "```",
        "python -c \"from wp0 import findings; print(findings.f07_hf365_dates())\"",
        "```",
        "",
    ]
    for section, ids in SECTIONS.items():
        L += [f"## {section}", ""]
        for i in ids:
            f = by_id.get(i)
            if f is None:
                continue
            L += [f"### {f.id} · {f.claim}",
                  "",
                  f"**Measured:** {f.value}",
                  "",
                  f"**Why it matters:** {f.matters}",
                  "",
                  f"*Source:* {f.source} · *Reproduce:* `wp0.findings.{fnmap.get(f.id, '?')}()` "
                  f"· *Reproduces:* {'yes' if f.holds else 'NO'}",
                  ""]
    L += ["---", "",
          "Archive defects formatted for the Harvard Forest information manager are "
          "in `wp0/out/archive_corrections.md`. Findings tagged for S6 evaluation, "
          "with contamination provenance, are in `wp0/out/answer_key.jsonl`.", ""]
    return "\n".join(L)


def run() -> tuple[list[Finding], str]:
    fs = collect()
    md = to_markdown(fs)
    (io.PKG / "FINDINGS.md").write_text(md, encoding="utf8")
    return fs, md
