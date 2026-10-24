"""WP0 foundation -- command line entry point.

    python -m wp0 check                environment, inputs, and what is built
    python -m wp0 run                  every stage, in dependency order
    python -m wp0 stage A --check      one stage, with its pass/fail assertions
    python -m wp0 verify               re-hash inputs against recorded stages
    python -m wp0 report               archive corrections + S6 answer key

Stage order is A -> B -> {C, D} -> LAI -> REPORT. Each stage's failure
invalidates only what follows it.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings

from wp0 import io

STAGES = ["A", "B", "C", "D", "LAI"]


def _mark(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def cmd_check(args):
    print(f"data root   : {io.DATA}")
    missing = [k for k, p in io.RAW.items() if not p.exists()]
    print(f"raw inputs  : {len(io.RAW) - len(missing)}/{len(io.RAW)} present"
          + (f"  MISSING: {', '.join(missing)}" if missing else ""))
    built = sorted(p.name for p in io.OUT.glob("*")) if io.OUT.exists() else []
    print(f"artifacts   : {len(built)} in {io.OUT}")
    for b in built:
        print(f"              {b}")
    prov = io.load_provenance()
    print(f"stages run  : {', '.join(prov.get('stages', {})) or 'none'}")
    frz = prov.get("s6_freeze", {})
    print(f"s6 freeze   : {len(frz.get('hashes', {}))} modules hashed"
          + (f" at {frz['frozen_at'][:19]}" if frz.get("frozen_at") else " (not yet)"))
    print("hls grid    : anchor UNVERIFIED -- no T18TYN granule on disk")


def cmd_verify(args):
    ok, problems = io.verify()
    print(_mark(ok), "input hashes and s6 freeze")
    for p in problems:
        print("  !", p)
    return 0 if ok else 1


def cmd_stage(args):
    from wp0 import registry, crosswalk, bands, solar, lai
    name = args.name.upper()
    fails = 0

    if name == "A":
        reg = registry.run()
        if args.check:
            for label, ok, detail in registry.checks(reg):
                print(_mark(ok), label, f"| {detail}" if detail else "")
                fails += not ok

    elif name == "B":
        reg = registry.build()
        if args.check:
            for label, ok, detail in crosswalk.validate_modis_grid():
                print(_mark(ok), label)
                fails += not ok
        out = crosswalk.run(reg)
        if args.check:
            hls, flips = out["hls"], out["flips"]
            grid_plots = flips[flips["plot"].str.match(r"^[A-H][1-5]$")]
            n_inside = int(grid_plots["inside_epoch_radius"].sum())
            med = float(hls[hls["is_dominant"] & (hls["radius_m"] == 10.0)]
                        ["overlap_frac"].median())
            checks = [
                ("7 of 40 grid plots wholly inside one HLS pixel", n_inside == 7, str(n_inside)),
                ("median dominant overlap ~0.7687 for 10 m plots",
                 abs(med - 0.7687) < 0.01, f"{med:.4f}"),
                ("fully_inside set is robust to radius choice",
                 not flips["flips"].any(), f"{int(flips['flips'].sum())} flips"),
            ]
            for label, ok, detail in checks:
                print(_mark(ok), label, f"| {detail}")
                fails += not ok
            m = out["modis"]
            print("\nMODIS assignment, 34 active tower plots "
                  "(validated against AppEEARS line/sample):")
            print(m[m["status"] == "active_tower"]["appeears_pixel"]
                  .value_counts().to_string())

    elif name == "C":
        long, stats = bands.run()
        print(json.dumps(stats, indent=2))
        if args.check:
            checks = [
                ("EVI2 closure within the storage-rounding floor",
                 stats["closure_within_rounding_floor"],
                 f"sd {stats['evi2_residual_sd']:.5f} vs floor "
                 f"{stats['mc_floor_sd_median']:.5f}"),
                ("RED recovered to better than 1% relative in the growing season",
                 stats["red_rel_sd_growing_p50"] < 0.01,
                 f"{100 * stats['red_rel_sd_growing_p50']:.2f}%"),
            ]
            for label, ok, detail in checks:
                print(_mark(ok), label, f"| {detail}")
                fails += not ok

    elif name == "D":
        g, res, info = solar.run()
        print(f"solar grid: {len(g)} rows, SZA {g['sza_deg'].min():.2f}-"
              f"{g['sza_deg'].max():.2f} deg")
        print(f"stamp convention: {info['verdict']}")
        print(f"  {info['detail']}")
        if args.check:
            checks = [
                ("solstice-noon SZA near 19 deg at 42.54N",
                 abs(g["sza_deg"].min() - 19.2) < 1.0, f"{g['sza_deg'].min():.2f}"),
                ("stamp convention resolved",
                 info["verdict"] != "unknown", info["verdict"]),
            ]
            for label, ok, detail in checks:
                print(_mark(ok), label, f"| {detail}")
                fails += not ok

    elif name == "LAI":
        df, rejects, step = lai.run()
        print(f"clean rows {len(df)}, {df['plot'].nunique()} plots, "
              f"{df['campaign_id'].nunique()} campaigns")
        print(f"rejected labels: {', '.join(rejects['rejected_label'].astype(str))}")
        print(f"instrument step: {step['verdict']} "
              f"(mean {step['mean_step_pai']:+.3f} PAI, p={step['p_paired_t']:.3f})")
    else:
        print(f"unknown stage {name}; choose from {', '.join(STAGES)}", file=sys.stderr)
        return 2
    return 1 if fails else 0


def cmd_run(args):
    rc = 0
    for s in STAGES:
        print(f"\n=== stage {s} " + "=" * 50)
        rc |= cmd_stage(argparse.Namespace(name=s, check=True))
    print("\n=== report " + "=" * 51)
    rc |= cmd_report(args)
    return rc


def cmd_findings(args):
    """Recompute every finding from the raw files and rewrite FINDINGS.md."""
    from wp0 import findings
    fs, _ = findings.run()
    fails = 0
    for f in fs:
        print(_mark(f.holds), f.id, f.claim)
        print(f"      {f.value[:150]}")
        fails += not f.holds
    print(f"\n{len(fs) - fails} of {len(fs)} findings reproduce")
    print(f"written: {io.PKG / 'FINDINGS.md'}")
    return 1 if fails else 0


def cmd_report(args):
    from wp0 import report
    counts = report.run()
    print(json.dumps(counts, indent=2))
    print(f"\nwritten: {io.OUT / 'archive_corrections.md'}")
    print(f"written: {io.OUT / 'answer_key.jsonl'}")
    return 0


def main(argv=None):
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(prog="wp0", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("verify").set_defaults(fn=cmd_verify)
    sub.add_parser("run").set_defaults(fn=cmd_run)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    sub.add_parser("findings").set_defaults(fn=cmd_findings)
    sp = sub.add_parser("stage")
    sp.add_argument("name", choices=STAGES + [s.lower() for s in STAGES])
    sp.add_argument("--check", action="store_true")
    sp.set_defaults(fn=cmd_stage)
    args = ap.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
