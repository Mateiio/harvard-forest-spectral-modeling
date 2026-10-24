"""Archive-correction report, and the S6 answer key with contamination provenance.

Two audiences, one findings list:

  * the Harvard Forest information manager (``hf-im@lists.fas.harvard.edu``),
    who gets ``archive_corrections.md``;
  * S6's evaluation, which gets ``answer_key.jsonl``.

The second one needs care. The S6 detector in ``s6_audit/`` was written *after*
the eight findings in ``00-research-program.md`` were known, so those eight
cannot score it -- the design saw them. Every finding therefore carries a
``discovered_by`` tag, and only findings tagged ``planning_2026_08_07`` or
``wp0_code`` form a clean held-out set. Those tags are load-bearing; do not
merge them.

Every finding below was verified against the raw file named in ``evidence``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field

from wp0 import io

CONTAMINATED = "program_doc"       # s6_audit was built knowing these
CLEAN = ("planning_2026_08_07", "wp0_code")


@dataclass
class Finding:
    id: str
    dataset: str
    fault_class: str
    summary: str
    evidence: str
    discovered_by: str
    discovered_on: str
    verified: bool = True
    tags: list[str] = field(default_factory=list)

    @property
    def usable_for_s6_eval(self) -> bool:
        return self.discovered_by in CLEAN


FINDINGS: list[Finding] = [
    # ---------------- already in 00-research-program.md: contaminated ---------
    Finding("F01", "hf206-05", "unconverted_sentinel",
            "Campbell +-7999 error codes never converted to NA: 60 occurrences in "
            "par_f2_max, 6 in swc3_max.",
            "hf206-05-EMS-understory.csv: par_f2_max spans -7999..7999",
            CONTAMINATED, "2026-08-04"),
    Finding("F02", "hf206-05", "impossible_value",
            "Physically impossible extremes: par_c3_min = -1648 umol m-2 s-1; "
            "tsoil2_e_max = 101.8 C; tair_us_e_20cm_max = 88.5 C; "
            "swc4_max = 1.578 (and swc4_max min = -23.56).",
            "hf206-05-EMS-understory.csv column extrema",
            CONTAMINATED, "2026-08-04",
            tags=["swc4_max negative extreme is an extension of the original finding"]),
    Finding("F03", "hf206-05", "unit_error_in_eml",
            "par_*_max attributes are labelled dimensionless in the EML although "
            "they are photon flux density.",
            "hf206.xml attribute measurementScale", CONTAMINATED, "2026-08-04"),
    Finding("F04", "hf206-05", "metadata_self_contradiction",
            "_ave attribute descriptions assign all six PAR sensors to EMS1, while "
            "the methods text and the _max descriptions assign E3, F3, F2 to EMS2.",
            "hf206.xml", CONTAMINATED, "2026-08-04"),
    Finding("F05", "hf069 / hf375-02", "documentation_vs_data",
            "Transect count: plot coordinates resolve to eight lettered transects "
            "(A-H); hf069.xml says ten; the Lee et al. paper says six.",
            "hf375-02 coordinates vs hf069.xml abstract",
            CONTAMINATED, "2026-08-04"),

    # ---------------- surfaced 2026-08-07 in planning: clean ------------------
    Finding("F06", "hf375-02 / hf069", "same_entity_inconsistent_value",
            "Plot size disagreement: hf375-02 gives AreaGISm2 = 297 m2 for all 46 "
            "EMS plots, implying a 9.72 m radius; hf069.xml states 10 m radius "
            "(314.16 m2). The measurement protocol should win.",
            "hf375-02-field-sites-plots.csv AreaGISm2 vs hf069.xml abstract",
            "planning_2026_08_07", "2026-08-07"),
    Finding("F07", "hf365", "internal_inconsistency",
            "The three index files do not share a date index, and the mismatch is "
            "three-way and non-nested: 261 EVI2, 262 NDVI, 262 NIRv dates; 260 in "
            "all three; 263 in the union. NDVI has 2019-07-12 and 2019-09-10 that "
            "EVI2 lacks; EVI2 has 2020-07-21 that NDVI lacks.",
            "hf365-01/02/03 date columns", "planning_2026_08_07", "2026-08-07"),
    Finding("F08", "hf069-01", "dirty_categorical",
            "The plot column carries 55 distinct labels, 9 of which are not EMS "
            "plots: '1', 'A1CAM', 'BOG', 'PAR' (108 rows), 'RO', 'RO TOWE' "
            "(truncated), 'TS1', 'TS2', 'VAN'.",
            "hf069-01-lai-plot.csv plot column vs the hf375-02 roster",
            "planning_2026_08_07", "2026-08-07"),
    Finding("F09", "hf069-01", "attribute_name_vs_content",
            "The data column is named 'lai' but holds plant area index. The file's "
            "own EML says so: 'The data reported in this file is of plant area "
            "index (PAI), and has not been corrected for woody material.'",
            "hf069-01-lai-plot.csv header vs hf069.xml attributeDefinition",
            "planning_2026_08_07", "2026-08-07"),
    Finding("F10", "hf069-01", "duplicate_records",
            "103 duplicate (date, plot) rows. They are genuine repeat measurements, "
            "but nothing in the file distinguishes them, so a naive load "
            "double-counts those plot-dates.",
            "hf069-01-lai-plot.csv", "planning_2026_08_07", "2026-08-07"),

    # ---------------- produced by WP0 code: clean ----------------------------
    Finding("F11", "hf375-02", "documentation_vs_data",
            "All 46 EMS plots are marked Active='yes' with no EndDate, including "
            "G3, H3 and H4 -- removed in 2001 to beaver-pond inundation -- and X4, "
            "where measurement ceased in 2001 because the plot was unaffected by "
            "the harvest. hf069.xml documents all four.",
            "hf375-02 Active/EndDate vs hf069.xml abstract", "wp0_code", "2026-08-07"),
    Finding("F12", "hf375-02", "same_entity_inconsistent_value",
            "AreaGISm2 = 297 m2 is applied uniformly to the harvest group as well, "
            "but hf069.xml expands those plots to 15 m radius (706.86 m2) in summer "
            "2001. The field is therefore wrong for A4, A5, B5 and X1-X6 in a "
            "second, independent way -- a factor of 2.4 in area, not 5%.",
            "hf375-02 AreaGISm2 vs hf069.xml abstract", "wp0_code", "2026-08-07"),
    Finding("F13", "hf375-02", "documentation_vs_data",
            "StartDate = 1993 is given for the Simes Lot plots X1-X6, but hf069.xml "
            "states they were installed in 1999.",
            "hf375-02 StartDate vs hf069.xml abstract", "wp0_code", "2026-08-07"),
]


def to_markdown() -> str:
    lines = [
        "# Archive corrections: Harvard Forest EMS datasets",
        "",
        "Reported from WP0 of the Harvard Forest spectral modelling program. Every",
        "item was verified against the raw archive file named under *Evidence*.",
        "Contact: hf-im@lists.fas.harvard.edu",
        "",
    ]
    by_ds: dict[str, list[Finding]] = {}
    for f in FINDINGS:
        by_ds.setdefault(f.dataset, []).append(f)
    for ds, items in by_ds.items():
        lines += [f"## {ds}", ""]
        for f in items:
            lines += [f"**{f.id} - {f.fault_class.replace('_', ' ')}**",
                      "", f.summary, "",
                      f"*Evidence:* `{f.evidence}`", ""]
    lines += ["---", "",
              f"{len(FINDINGS)} findings. "
              f"{sum(f.usable_for_s6_eval for f in FINDINGS)} of them were surfaced "
              "after the S6 detector was written and are held out from its "
              "evaluation set; see `answer_key.jsonl`.", ""]
    return "\n".join(lines)


def run() -> dict:
    md = to_markdown()
    (io.OUT / "archive_corrections.md").parent.mkdir(parents=True, exist_ok=True)
    (io.OUT / "archive_corrections.md").write_text(md, encoding="utf8")

    with open(io.OUT / "answer_key.jsonl", "w", encoding="utf8") as fh:
        for f in FINDINGS:
            row = asdict(f)
            row["usable_for_s6_eval"] = f.usable_for_s6_eval
            fh.write(json.dumps(row) + "\n")

    counts = {
        "total": len(FINDINGS),
        "contaminated_program_doc": sum(f.discovered_by == CONTAMINATED for f in FINDINGS),
        "clean_planning": sum(f.discovered_by == "planning_2026_08_07" for f in FINDINGS),
        "clean_wp0_code": sum(f.discovered_by == "wp0_code" for f in FINDINGS),
    }
    counts["clean_total"] = counts["clean_planning"] + counts["clean_wp0_code"]
    io.record(
        stage="REPORT",
        inputs=["hf206_ems", "hf375_plots", "hf069_plot", "eml_hf069", "eml_hf206"],
        params=counts,
        outputs=["archive_corrections.md", "answer_key.jsonl"],
        notes="s6_audit was built after the program doc's findings were known, so "
              "those are contaminated; the rest are a held-out eval set.",
    )
    return counts
