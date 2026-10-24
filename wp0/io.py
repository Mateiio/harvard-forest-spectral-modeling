"""Stage 0: input registry, hashing, and the provenance contract.

Seven studies read the artifacts this package writes. The failure this guards
against is a downstream notebook silently consuming a stale registry, which the
program has already hit once (three plot-coordinate lineages in circulation).

Every stage calls :func:`record` on the way out. ``python -m wp0 verify``
re-hashes the inputs and fails loudly when any of them has moved underneath a
committed artifact.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DATA = Path(r"c:\crtusers\matei\prj\data")
PKG = Path(__file__).resolve().parent
OUT = PKG / "out"
V0 = PKG.parent / "brainstormingsessions" / "v0"

# The v0 artifacts are comparison targets only. Reading them anywhere except
# wp0.crosswalk's adjudication step reintroduces the lineage problem.
V0_READONLY = True

RAW: dict[str, Path] = {
    "hf365_evi2": DATA / "HF365Dataset" / "hf365-01-hls-evi2.csv",
    "hf365_ndvi": DATA / "HF365Dataset" / "hf365-02-hls-ndvi.csv",
    "hf365_nirv": DATA / "HF365Dataset" / "hf365-03-hls-nirv.csv",
    "hf375_points": DATA / "HF375" / "hf375-01-field-sites-points.csv",
    "hf375_plots": DATA / "HF375" / "hf375-02-field-sites-plots.csv",
    "hf069_plot": DATA / "HF069" / "hf069-01-lai-plot.csv",
    "hf069_site": DATA / "HF069" / "hf069-02-lai-site.csv",
    "hf004_final": DATA / "HF004" / "hf004-01-final.csv",
    "hf206_ems": DATA / "HF206" / "hf206-05-EMS-understory.csv",
    "modis_main": DATA / "MODIS" / "Main5Pixels-PointSample-MCD15A2H-061-results.csv",
    "eml_hf069": DATA / "HF_EML" / "hf069.xml",
    "eml_hf365": DATA / "HF_EML" / "hf365.xml",
    "eml_hf375": DATA / "HF_EML" / "hf375.xml",
    "eml_hf206": DATA / "HF_EML" / "hf206.xml",
    "eml_hf004": DATA / "HF_EML" / "hf004.xml",
}

# Site constants, each traced to a file rather than to the program document.
TOWER_LAT = 42.537764          # hf375-01 row 154, TYPE='Tower', PLOT='EMS Tower'
TOWER_LON = -72.171479
TOWER_ELEV_M = 340.0
TZ = "Etc/GMT+5"               # EST year-round; hf004 column is hour.hour.est.utc.5.
EPSG_UTM18N = 32618
DATUM = "WGS84"                # hf375.xml: "Coordinates based on WGS84 datum."
HLS_TILE = "T18TYN"            # hf365.xml fixes the tile
HLS_RES_M = 30.0
MODIS_RES_M = 463.31271652777775   # MCD15A2H sinusoidal, 500 m nominal
PLOT_RADIUS_M = 10.0           # hf069.xml: "40 circular, 10 m radius biometric plots"
PLOT_RADIUS_ALT_M = 9.7228     # implied by hf375-02 AreaGISm2 = 297

# The S6 detector was built after seeing the program document's eight findings,
# so those eight cannot score it. These modules are hashed before any WP0 code
# runs so that findings surfaced later stay a genuine held-out evaluation set.
S6_MODULES = [PKG.parent / "s6_audit", PKG.parent / "s6_search"]


def md5(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def hash_inputs(keys: list[str] | None = None) -> dict[str, dict]:
    """MD5 + size + mtime for the named raw inputs (all of them by default)."""
    out = {}
    for k in keys or RAW:
        p = RAW[k]
        if not p.exists():
            out[k] = {"path": str(p), "status": "MISSING"}
            continue
        st = p.stat()
        out[k] = {
            "path": str(p),
            "md5": md5(p),
            "bytes": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
        }
    return out


def hash_s6() -> dict[str, str]:
    """Freeze the S6 detector so later WP0 findings remain a clean eval set."""
    out = {}
    for root in S6_MODULES:
        if not root.exists():
            continue
        for p in sorted(root.glob("*.py")):
            out[f"{root.name}/{p.name}"] = md5(p)
    return out


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------

def _prov_path() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    return OUT / "provenance.json"


def load_provenance() -> dict:
    p = _prov_path()
    if not p.exists():
        return {"stages": {}, "s6_freeze": {}}
    return json.loads(p.read_text(encoding="utf8"))


def record(stage: str, inputs: list[str], params: dict, outputs: list[str],
           notes: str = "") -> None:
    """Append a stage entry. Call once per stage, after the artifacts are written."""
    from wp0 import __version__

    prov = load_provenance()
    prov.setdefault("stages", {})[stage] = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "wp0_version": __version__,
        "inputs": hash_inputs(inputs),
        "params": params,
        "outputs": outputs,
        "notes": notes,
    }
    if not prov.get("s6_freeze"):
        prov["s6_freeze"] = {
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "reason": "s6_audit saw the program doc's 8 findings; hashing it here "
                      "keeps anything WP0 finds afterwards a held-out eval set",
            "hashes": hash_s6(),
        }
    _prov_path().write_text(json.dumps(prov, indent=2), encoding="utf8")


def verify() -> tuple[bool, list[str]]:
    """Re-hash inputs against what each recorded stage consumed."""
    prov = load_provenance()
    problems: list[str] = []
    if not prov.get("stages"):
        return False, ["no stages recorded yet -- run the pipeline first"]
    live = hash_inputs()
    for stage, entry in prov["stages"].items():
        for key, was in entry["inputs"].items():
            now = live.get(key, {})
            if was.get("md5") != now.get("md5"):
                problems.append(
                    f"{stage}: input '{key}' changed since it ran "
                    f"({was.get('md5', 'MISSING')[:8]} -> {now.get('md5', 'MISSING')[:8]})")
    for name, was in prov.get("s6_freeze", {}).get("hashes", {}).items():
        src = PKG.parent / name
        if not src.exists():
            problems.append(f"s6 freeze: {name} deleted")
        elif md5(src) != was:
            problems.append(f"s6 freeze: {name} edited after freeze -- "
                            "held-out findings may be contaminated")
    return not problems, problems


# --------------------------------------------------------------------------
# loaders
# --------------------------------------------------------------------------

def read_raw(key: str, **kw) -> pd.DataFrame:
    return pd.read_csv(RAW[key], **kw)


def eml_text(key: str) -> str:
    return RAW[key].read_text(encoding="utf8", errors="replace")


def write(df: pd.DataFrame, name: str, index: bool = False) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    df.to_csv(p, index=index)
    return p
