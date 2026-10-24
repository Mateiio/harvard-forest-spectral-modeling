"""S7 command line entry point.

    python -m s7 findings     recompute every finding and rewrite s7/FINDINGS.md
    python -m s7 run          rebuild the triplet, TC results and uncertainty column
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings


def cmd_findings(args) -> int:
    from s7 import findings
    fs, _ = findings.run()
    fails = 0
    for f in fs:
        print("PASS" if f.holds else "FAIL", f.id, f.claim)
        print("      " + f.value[:150])
        fails += not f.holds
    print("\n%d of %d findings reproduce" % (len(fs) - fails, len(fs)))
    return 1 if fails else 0


def cmd_run(args) -> int:
    from s7 import results
    print(json.dumps(results.run("evi2"), indent=2, default=str))
    return 0


def main(argv=None) -> int:
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser(prog="s7", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("findings").set_defaults(fn=cmd_findings)
    sub.add_parser("run").set_defaults(fn=cmd_run)
    args = ap.parse_args(argv)
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
