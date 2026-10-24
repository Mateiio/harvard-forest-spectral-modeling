"""S1 HF365 v2 reprocessing -- command line entry point.

    python -m s1 check                environment, WP0 inputs, Earthdata auth
    python -m s1 selftest             full offline suite on a synthetic granule
    python -m s1 stage 0              CMR granule manifest (no credentials)
    python -m s1 stage grid           verify the T18TYN anchor against WP0
    python -m s1 run                  everything; stages 1+ need credentials

Stage 0 and the selftest run without credentials. Everything that touches real
pixels needs NASA Earthdata Login -- `check` says exactly what is missing.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import warnings
from pathlib import Path

from s1 import io as sio


def _mark(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _report(rows) -> int:
    fails = 0
    for label, ok, detail in rows:
        print(_mark(ok), label, (f"| {detail}" if detail else ""))
        fails += not ok
    return fails


def cmd_check(args) -> int:
    from s1 import fetch, schema
    ready, missing = sio.wp0_ready()
    print(f"wp0 inputs   : {'all present' if ready else 'MISSING ' + ', '.join(missing)}")
    print(f"tile         : {schema.TILE}  UL=({schema.TILE_ULX}, {schema.TILE_ULY})  "
          f"EPSG:{schema.EPSG}")
    st = fetch.auth_status()
    print(f"earthaccess  : {'installed' if st['earthaccess_installed'] else 'NOT INSTALLED'}")
    print(f"credentials  : netrc={st['netrc']} env={st['env_vars']}")
    print(f"online ready : {st['ready']}")
    for t in st["todo"]:
        print(f"   todo -> {t}")
    built = sorted(p.name for p in sio.OUT.glob("*")) if sio.OUT.exists() else []
    print(f"artifacts    : {len(built)}")
    for b in built:
        print(f"               {b}")
    prov = sio.load_provenance()
    print(f"stages run   : {', '.join(prov.get('stages', {})) or 'none'}")
    return 0


def cmd_selftest(args) -> int:
    import numpy as np
    from s1 import extract, fetch, grid, qa, schema, synthetic

    fails = 0
    print("--- Fmask / Table 9 ---")
    fails += _report(qa.checks())

    print("\n--- grid anchor ---")
    ok, detail = grid.anchor_ok()
    fails += _report([("T18TYN origin lies on the global 30 m grid", ok, detail)])
    fails += _report(grid.verify_against_wp0())

    print("\n--- schema typing ---")
    fails += _report([
        ("L30 B10 is brightness temperature, not reflectance",
         not schema.layer("L30", "B10").is_reflectance
         and schema.layer("L30", "B10").scale == schema.THERM_SCALE,
         f"scale {schema.layer('L30', 'B10').scale} degC"),
        ("S30 B10 is reflectance",
         schema.layer("S30", "B10").is_reflectance, "same name, different quantity"),
        ("S30 NIR is B8A, not B08",
         schema.NIR_BAND["S30"] == "B8A", schema.NIR_BAND["S30"]),
        ("L30 NIR is B05, red is B04",
         (schema.NIR_BAND["L30"], schema.RED_BAND["L30"]) == ("B05", "B04"), ""),
        ("angle fill is 40000, reflectance fill is -9999",
         schema.ANG_FILL == 40000 and schema.REF_FILL == -9999, ""),
    ])

    print("\n--- synthetic granule: decode, mask, extract ---")
    cw = extract.crosswalk()
    px = cw["hls_pixel"].drop_duplicates()
    tmp = Path(tempfile.mkdtemp(prefix="s1_selftest_"))
    a3 = {tuple(map(int, p.split("_"))) for p in cw.loc[cw["plot"] == "A3", "hls_pixel"]}
    a2 = cw[cw["plot"] == "A2"].sort_values("rank")
    hi = {tuple(map(int, a2.iloc[1]["hls_pixel"].split("_")))}
    # plant reflectance/angle fill on a non-dominant pixel of a 4-pixel plot, so
    # the -9999 and 40000 decode paths run on a pixel that is actually read
    multi = cw[cw["n_pixels_touched"] == 4].sort_values(["plot", "rank"])
    fill_plot = multi["plot"].iloc[0]
    fill_px = multi[multi["plot"] == fill_plot].iloc[-1]["hls_pixel"]
    fill = {tuple(map(int, fill_px.split("_")))}
    base = synthetic.make(tmp, px, "L30", cloud_pixels=a3,
                          high_aerosol_pixels=hi, fill_pixels=fill)
    bounds = fetch.bounds_for(px)
    layers = fetch.granule_layers(base, "L30", bounds)
    pix = extract.pixel_frame(layers, "L30")
    plots = extract.to_plots(pix, cw)
    exp = synthetic.expected()
    clear = pix[pix["usable"]]
    p = plots.set_index("plot")

    fails += _report([
        ("scale hard-coded when the COG carries no scale_factor tag",
         abs(float(clear["nir"].iloc[0]) - exp["nir"]) < 1e-9,
         f"nir {clear['nir'].iloc[0]:.4f} vs {exp['nir']}"),
        ("reflectance fill -9999 becomes NaN",
         bool(pix.set_index("hls_pixel").loc[fill_px, "nir"] != pix.set_index("hls_pixel")
              .loc[fill_px, "nir"]),
         f"{fill_px} on plot {fill_plot}"),
        ("angle fill 40000 becomes NaN, not 400 degrees",
         bool(np.isnan(pix.set_index("hls_pixel").loc[fill_px, "sza"])),
         "different fill value from reflectance"),
        ("a fill pixel is excluded from its plot's weighted mean",
         float(p.loc[fill_plot, "weight_coverage"]) < 1.0,
         f"{fill_plot} coverage {p.loc[fill_plot, 'weight_coverage']:.4f}"),
        ("NDVI matches closed form",
         abs(float(clear["ndvi"].iloc[0]) - exp["ndvi"]) < 1e-9, f"{exp['ndvi']:.6f}"),
        ("EVI2 matches closed form",
         abs(float(clear["evi2"].iloc[0]) - exp["evi2"]) < 1e-9, f"{exp['evi2']:.6f}"),
        ("NIRv matches closed form",
         abs(float(clear["nirv"].iloc[0]) - exp["nirv"]) < 1e-9, f"{exp['nirv']:.6f}"),
        ("angles decode with the 0.01 scale",
         abs(float(clear["sza"].iloc[0]) - 35.0) < 1e-9, f"{clear['sza'].iloc[0]}"),
        ("clouded plot A3 yields no value",
         (not bool(p.loc["A3", "single_usable"])) and np.isnan(p.loc["A3", "ndvi_weighted"]),
         "single unusable, weighted NaN"),
        ("high-aerosol pixel is discarded from the weighted mean",
         abs(float(p.loc["A2", "weight_coverage"]) - 0.6435) < 0.01,
         f"A2 coverage {p.loc['A2', 'weight_coverage']:.4f} = its dominant overlap"),
        ("fully-inside plot A1 gives single == weighted",
         abs(float(p.loc["A1", "ndvi_single"]) - float(p.loc["A1", "ndvi_weighted"])) < 1e-12,
         "coverage 1.0"),
    ])

    print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILURES'}")
    return 1 if fails else 0


def cmd_stage(args) -> int:
    name = str(args.name).lower()
    if name in ("0", "search"):
        from s1 import search
        man, dens = search.run()
        print(f"{len(man)} granules")
        fails = _report(search.checks(man))
        print("\nper year:")
        print(man.groupby("year").size().to_string())
        print("\nplatform mix:")
        print(man["platform"].value_counts().to_string())
        print("\nS30 L1C baseline (known issue #12):")
        print(man[man["product"] == "S30"]["l1c_baseline"].value_counts().to_string())
        return 1 if fails else 0
    if name == "grid":
        from s1 import grid
        ok, detail = grid.anchor_ok()
        fails = _report([("T18TYN origin on the 30 m grid", ok, detail)])
        fails += _report(grid.verify_against_wp0())
        return 1 if fails else 0
    print(f"unknown stage {name!r}; try 0 or grid", file=sys.stderr)
    return 2


def cmd_findings(args) -> int:
    """Recompute every finding from s1/out and rewrite FINDINGS.md."""
    from s1 import findings
    fs, _ = findings.run()
    fails = 0
    for f in fs:
        print(_mark(f.holds), f.id, f.claim)
        print("      " + f.value[:150])
        fails += not f.holds
    print("\n%d of %d findings reproduce" % (len(fs) - fails, len(fs)))
    print("written: %s" % (sio.PKG / "FINDINGS.md"))
    return 1 if fails else 0


def cmd_run(args) -> int:
    from s1 import fetch
    rc = cmd_stage(argparse.Namespace(name="0"))
    rc |= cmd_stage(argparse.Namespace(name="grid"))
    st = fetch.auth_status()
    if not st["ready"]:
        print("\n" + "=" * 62)
        print("Stages 1+ need NASA Earthdata credentials. Not run.")
        for t in st["todo"]:
            print(f"  -> {t}")
        print("Everything that does not need credentials has completed.")
        return rc
    print("\ncredentials present -- online stages not yet wired to a full run")
    return rc


def main(argv=None) -> int:
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(prog="s1", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("selftest").set_defaults(fn=cmd_selftest)
    sub.add_parser("run").set_defaults(fn=cmd_run)
    sub.add_parser("findings").set_defaults(fn=cmd_findings)
    sp = sub.add_parser("stage")
    sp.add_argument("name")
    sp.set_defaults(fn=cmd_stage)
    args = ap.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
