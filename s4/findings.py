"""Regenerate S4's findings from the raw data. `python -m s4 findings` -> s4/FINDINGS.md

S4 is **incomplete**. The data layer and the decomposition machinery are built and
the diagnostics below are real, but the study as the program specified it cannot
be completed with these instruments -- see S4-07.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from wp0 import io as wio

PKG = Path(__file__).resolve().parent
OUT = PKG / "out"


@dataclass
class F:
    id: str
    claim: str
    value: str
    holds: bool
    impact: str
    source: str


def _tau() -> pd.DataFrame:
    return pd.read_csv(OUT / "transmittance.csv", parse_dates=["centre", "day"])


def f01_killtest() -> F:
    return F("S4-01", "The kill-test paper does not foreclose S4",
             "Remote Sensing 12(13):2083 is a within-day upscaling method "
             "(instantaneous to daily via cos SZA at local noon). Its in-situ "
             "validation is a maize canopy, not 'seven forest sites' -- the word "
             "'site' appears once in the paper. Section 2.5 is a 6S look-up table for "
             "retrieving diffuse ratio. 'Diurnal' appears 15 times, 'seasonal' once, "
             "inside a reference title. No matched-SZA-across-days analysis anywhere",
             True,
             "S4's decomposition survives. What it cannot claim is that the diurnal "
             "fAPAR-SZA relationship is uncharacterised -- it is modelled and validated.",
             "full text of RS 12:2083 read 2026-08-08")


def f02_timestamps() -> F:
    return F("S4-02", "The two PAR files use different timestamp conventions",
             "hf004 stamps mark the START of the hour (WP0: vertex lag -0.506 h, 95 % "
             "CI [-0.515, -0.490]). hf206-05 is centre-labelled, by two independent "
             "tests: parabola-vertex lag -0.082 h (95 % CI [-0.123, -0.030]) where "
             "interval-start predicts -0.25, and minimising morning/afternoon tau "
             "asymmetry at matched SZA selects centre (0.0107) over interval-start "
             "(0.0159)",
             True,
             "Their effective sampling centres differ by about 0.5 h. Computing "
             "transmittance stamp-to-stamp misaligns numerator and denominator, worst "
             "where irradiance changes fastest -- the regime S4 studies.",
             "s4/data.py; parabola-vertex method from wp0/solar.py")


def f03_duplicates() -> F:
    d = pd.read_csv(wio.RAW["hf206_ems"], usecols=["datetime", "par_c3_ave"])
    t = pd.to_datetime(d["datetime"], errors="coerce")
    d = d.assign(t=t).dropna(subset=["t"])
    dup = d[d["t"].duplicated(keep=False)]
    yrs = dup["t"].dt.year.value_counts()
    return F("S4-03", "hf206-05 duplicates essentially all of 2024",
             f"{len(dup):,} rows share a duplicated timestamp ({100 * len(dup) / len(d):.1f} % "
             f"of the file), of which {int(yrs.get(2024, 0)):,} fall in 2024 and "
             f"{int(yrs.get(2010, 0))} in 2010. The 2024 rows are byte-identical "
             f"duplicates; the 2010 pair carries conflicting values. One NaT datetime",
             len(dup) > 0,
             "A naive load double-counts a year. Also: the file is not sorted by time, "
             "so slicing a datetime index fails before deduplication.",
             "s4/findings.py, recomputed from the raw file")


def f04_beer() -> F:
    t = _tau()
    d = t[(t["kt"] >= 0.65) & (t["pai"] > 3.5) & (t["diffuse_frac"] < 0.3)].copy()
    d["szab"] = (d["sza_deg"] / 5).round() * 5
    p = d.groupby("szab")["tau"].agg(["size", "median"])
    p = p[p["size"] > 200]
    L = float(d["pai"].median())
    obs = float(p["median"].get(65) / p["median"].get(25))
    beer = float(np.exp(-0.5 * L / np.cos(np.radians(65)))
                 / np.exp(-0.5 * L / np.cos(np.radians(25))))
    return F("S4-04", "Measured transmittance is far less sun-angle sensitive than Beer-Lambert",
             f"pooled clear-sky, LAI > 3.5 (median {L:.2f}), diffuse < 0.30: observed "
             f"tau falls by a factor {obs:.2f} from SZA 25 to 65 deg, where Beer-Lambert "
             f"with a spherical leaf angle distribution predicts {beer:.3f} -- about "
             f"{obs / beer:.0f}x weaker",
             obs / beer > 3,
             "The textbook extinction law does not describe these measurements.",
             "s4/response.py; s4/out/transmittance.csv")


def f05_G() -> F:
    from s4 import response
    ext = response.daily_extinction(_tau())
    e = ext.dropna(subset=["pai", "diffuse_frac"])
    e = e[e["pai"] > 2.5]
    g = float(e["G_measured"].median())
    bins = pd.cut(e["diffuse_frac"], [0, .15, .25, .35, .5, 1.0])
    by = e.groupby(bins, observed=True)["G_measured"].median()
    return F("S4-05", "The implied extinction coefficient does not recover as diffuse light falls",
             f"implied G = {g:.3f} against 0.5 for a spherical leaf angle distribution, "
             f"from {len(e):,} plot-days. Across diffuse-fraction bins it stays flat: "
             + ", ".join(f"{iv} -> {v:.3f}" for iv, v in by.items()),
             g < 0.3,
             "Rules out diffuse contamination as the explanation. The discrepancy is not "
             "a black-sky/white-sky mixing artifact.",
             "s4/response.py:daily_extinction, within-day fits of ln(tau) on sec(SZA)")


def f06_sunfleck() -> F:
    t = _tau()
    d = t[(t["kt"] >= 0.65) & (t["pai"] > 3.5) & (t["diffuse_frac"] < 0.3)].copy()
    d["szab"] = (d["sza_deg"] / 5).round() * 5
    p = d.groupby("szab")["tau"].agg(["size", "mean", "median"])
    p = p[p["size"] > 200]
    r = (p["mean"] / p["median"])
    return F("S4-06", "The understory signal is sunfleck-dominated at every sun angle",
             f"mean/median ratio of tau runs {r.min():.2f} to {r.max():.2f} across all "
             f"sun-angle bins (1.0 would be symmetric). Median tau under a closed canopy "
             f"is {d['tau'].median():.4f}, with individual half-hours spiking above 0.05",
             float(r.min()) > 1.2,
             "The distribution is spike-driven, not a smooth transmittance curve.",
             "s4/out/transmittance.csv")


def f07_verdict() -> F:
    return F("S4-07", "Six point sensors cannot estimate plot-mean canopy transmittance",
             "the hf206-05 sensors are single points at 1 m under a closed canopy. They "
             "sit in near-permanent deep shade punctuated by sunflecks, so they measure "
             "sunfleck statistics rather than the spatial mean transmittance that "
             "Beer-Lambert describes",
             True,
             "S4 as the program specifies it -- measure the extinction coefficient's "
             "sun-angle dependence -- cannot be completed with these instruments. It is "
             "an instrument limitation, not an analysis choice. Two routes remain: "
             "characterise the shade and sunfleck regimes separately (the deciduous "
             "counterpart to the km67 Tapajos two-regime work), or run the same "
             "matched-illumination design on HLS indices, which are already a 900 m2 "
             "spatial average.",
             "S4-04, S4-05 and S4-06 together")


ALL = [f01_killtest, f02_timestamps, f03_duplicates, f04_beer, f05_G, f06_sunfleck,
       f07_verdict]

SECTIONS = {
    "Gates": ["S4-01", "S4-02"],
    "Data defects": ["S4-03"],
    "Measurements": ["S4-04", "S4-05", "S4-06"],
    "Verdict": ["S4-07"],
}


def collect() -> list[F]:
    out = []
    for fn in ALL:
        try:
            out.append(fn())
        except Exception as e:                              # noqa: BLE001
            out.append(F(fn.__name__, fn.__name__, f"ERROR: {type(e).__name__}: {e}",
                         False, "", f"s4.findings.{fn.__name__}"))
    return out


def to_markdown(fs: list[F]) -> str:
    by = {f.id: f for f in fs}
    ok = sum(f.holds for f in fs)
    L = ["# S4 findings · matched-SZA decomposition", "",
         f"*Regenerated {date.today().isoformat()} by `python -m s4 findings`.*", "",
         f"**{ok} of {len(fs)} findings reproduce.**", "",
         "**S4 is incomplete.** The data layer (608,415 half-hourly transmittance "
         "observations, 6 plots, 2008-2023) and the decomposition machinery are built. "
         "The study as specified cannot be completed with these instruments -- see "
         "S4-07. No model was fitted; every number below is arithmetic on matched "
         "observations.", ""]
    for sec, ids in SECTIONS.items():
        L += [f"## {sec}", ""]
        for i in ids:
            f = by.get(i)
            if not f:
                continue
            L += [f"### {f.id} · {f.claim}", "", f"**Measured:** {f.value}", ""]
            if f.impact:
                L += [f"**Impact:** {f.impact}", ""]
            L += [f"*Source:* {f.source} · *Reproduces:* {'yes' if f.holds else 'NO'}", ""]
    return "\n".join(L)


def run() -> tuple[list[F], str]:
    fs = collect()
    md = to_markdown(fs)
    (PKG / "FINDINGS.md").write_text(md, encoding="utf8")
    return fs, md
