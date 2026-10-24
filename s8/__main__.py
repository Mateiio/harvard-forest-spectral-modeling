"""S8 command line entry point.

    python -m s8 build       rebuild s8/out/pairs.csv from WP0 and S1
    python -m s8 fit         score the ladder, write predictions and coefficients
    python -m s8 forecast    score future-date prediction against three references
    python -m s8 findings    recompute every finding and rewrite s8/FINDINGS.md
    python -m s8 run         build, then fit, then forecast, then findings

``build`` takes ``--tol`` (matching window in days, default 3) and
``--from-1998`` to include the LAI-2000 era instead of starting at 2015.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings


def cmd_build(args) -> int:
    from s8 import data
    _, stats = data.run(tol_days=args.tol,
                        instrument_floor=None if args.from_1998
                        else data.INSTRUMENT_FLOOR)
    print(json.dumps(stats, indent=2))
    return 0


def cmd_fit(args) -> int:
    from s8 import model
    ladder, summary = model.run()
    shown = ["target", "features", "regime", "r2", "rmse", "n"]
    print(ladder[ladder["target"] == "lai"][shown].to_string(index=False))
    print("\nchosen:", summary["chosen"])
    print("known plot, new date :", summary["known_plot"])
    print("new plot             :", summary["new_plot"])
    return 0


def cmd_forecast(args) -> int:
    from s8 import forecast
    res, summary = forecast.run()
    print(res.pivot(index="horizon_days", columns="reference",
                    values="r2").to_string())
    print("\nbeats calendar   :", summary["beats_calendar"])
    print("beats persistence:", summary["beats_persistence"])
    return 0


def cmd_findings(args) -> int:
    from s8 import findings
    fs, _ = findings.run()
    fails = 0
    for f in fs:
        print("PASS" if f.holds else "FAIL", f.id, f.claim)
        print("      " + f.value[:150])
        fails += not f.holds
    print("\n%d of %d findings reproduce" % (len(fs) - fails, len(fs)))
    return 1 if fails else 0


def cmd_run(args) -> int:
    return (cmd_build(args) or cmd_fit(args) or cmd_forecast(args)
            or cmd_findings(args))


def main(argv=None) -> int:
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(prog="s8", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("build", cmd_build), ("fit", cmd_fit),
                     ("forecast", cmd_forecast), ("findings", cmd_findings),
                     ("run", cmd_run)):
        p = sub.add_parser(name)
        p.set_defaults(fn=fn)
        if name in ("build", "run"):
            p.add_argument("--tol", type=int, default=3,
                           help="matching window in days (default 3)")
            p.add_argument("--from-1998", action="store_true",
                           help="include the LAI-2000 era (crosses a calibration break)")
    args = ap.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
