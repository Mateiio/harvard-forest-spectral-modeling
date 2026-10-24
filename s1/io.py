"""S1 paths and provenance -- deliberately thin, reusing WP0's contract.

S1 writes stage entries into its own ``s1/out/provenance.json`` but with the
same shape and the same ``md5``/``hash_inputs`` helpers WP0 uses, so both halves
can be verified by one habit rather than two.

The WP0 artifacts S1 consumes are hashed on the way in. If WP0 is rebuilt with
different inputs, S1's provenance shows it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from wp0 import io as wio

PKG = Path(__file__).resolve().parent
OUT = PKG / "out"
CACHE = PKG / "cache"

# WP0 outputs S1 depends on.
WP0_INPUTS = {
    "plot_registry": wio.OUT / "plot_centroid_registry.csv",
    "crosswalk_hls": wio.OUT / "crosswalk_plot_to_hls.csv",
    "v14_reflectance": wio.OUT / "hf365_reflectance.csv",
    "solar_30min": wio.OUT / "solar_30min.csv",
    "field_lai": wio.OUT / "hf069_plot_clean.csv",
    "hf365_date_sets": wio.OUT / "hf365_date_sets.csv",
}


def wp0_ready() -> tuple[bool, list[str]]:
    missing = [k for k, p in WP0_INPUTS.items() if not p.exists()]
    return not missing, missing


def hash_wp0() -> dict[str, dict]:
    out = {}
    for k, p in WP0_INPUTS.items():
        if p.exists():
            st = p.stat()
            out[k] = {"path": str(p), "md5": wio.md5(p), "bytes": st.st_size}
        else:
            out[k] = {"path": str(p), "status": "MISSING"}
    return out


def read_wp0(key: str, **kw) -> pd.DataFrame:
    return pd.read_csv(WP0_INPUTS[key], **kw)


def _prov_path() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    return OUT / "provenance.json"


def load_provenance() -> dict:
    p = _prov_path()
    return json.loads(p.read_text(encoding="utf8")) if p.exists() else {"stages": {}}


def record(stage: str, inputs: list[str], params: dict, outputs: list[str],
           notes: str = "") -> None:
    from s1 import __version__
    prov = load_provenance()
    prov.setdefault("stages", {})[stage] = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "s1_version": __version__,
        "wp0_inputs": hash_wp0(),
        "raw_inputs": wio.hash_inputs(inputs) if inputs else {},
        "params": params,
        "outputs": outputs,
        "notes": notes,
    }
    _prov_path().write_text(json.dumps(prov, indent=2, default=str), encoding="utf8")


def write(df: pd.DataFrame, name: str, index: bool = False,
          na_rep: str = "") -> Path:
    """`na_rep="NA"` reproduces HF365's own spelling of a missing value.
    pandas writes an empty field by default, which reads as a blank cell
    rather than as 'no observation'."""
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    df.to_csv(p, index=index, na_rep=na_rep)
    return p
