"""Stage 1: windowed reads of native HLS COGs.

Windows are expressed in **map coordinates**, not row/col offsets, and resolved
with ``rasterio.windows.from_bounds``. That keeps the same code correct whether
it is pointed at a full 3660x3660 tile from LP DAAC or at the small synthetic
granule the offline tests use, and it removes any chance of an off-by-one
between the two.

Reads are windowed on purpose: the plot network needs a 26x16 block, so a range
request moves a few kilobytes instead of a 26 MB tile. That is what makes 1,098
granules x 8 layers tractable.

Everything here needs NASA Earthdata credentials. :func:`auth_status` reports
what is missing rather than failing deep inside a read.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds

from s1 import schema

GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_COOKIEFILE": str(Path.home() / ".hls_cookies"),
    "GDAL_HTTP_COOKIEJAR": str(Path.home() / ".hls_cookies"),
    "GDAL_HTTP_MAX_RETRY": "5",
    "GDAL_HTTP_RETRY_DELAY": "2",
}


def auth_status() -> dict:
    """What is present, what is missing, and what the user must do."""
    try:
        import earthaccess          # noqa: F401
        has_lib = True
    except ImportError:
        has_lib = False
    netrc = Path.home() / ".netrc"
    has_netrc = netrc.exists() and "urs.earthdata.nasa.gov" in (
        netrc.read_text(encoding="utf8", errors="replace") if netrc.exists() else "")
    has_env = bool(os.environ.get("EARTHDATA_USERNAME")
                   and os.environ.get("EARTHDATA_PASSWORD"))
    ready = has_lib and (has_netrc or has_env)
    todo = []
    if not has_lib:
        todo.append("pip install earthaccess")
    if not (has_netrc or has_env):
        todo.append("set EARTHDATA_USERNAME/EARTHDATA_PASSWORD, or run "
                    "`python -c \"import earthaccess; earthaccess.login(persist=True)\"` "
                    "to write ~/.netrc")
    return {"earthaccess_installed": has_lib, "netrc": has_netrc,
            "env_vars": has_env, "ready": ready, "todo": todo}


def login():
    import earthaccess
    return earthaccess.login(strategy="environment" if os.environ.get(
        "EARTHDATA_USERNAME") else "netrc", persist=False)


def bounds_for(pixels) -> tuple[float, float, float, float]:
    """UTM bounds covering WP0 global pixel ids like '24408_157110'."""
    import pandas as pd
    idx = pd.Series(list(pixels)).str.split("_", expand=True).astype(int)
    gcol, grow = idx[0].to_numpy(), idx[1].to_numpy()
    left = gcol.min() * schema.RES_M
    right = (gcol.max() + 1) * schema.RES_M
    bottom = grow.min() * schema.RES_M
    top = (grow.max() + 1) * schema.RES_M
    return float(left), float(bottom), float(right), float(top)


def read_window(path_or_url: str, bounds: tuple[float, float, float, float]):
    """Read one layer over ``bounds``. Returns (raw array, transform)."""
    with rasterio.Env(**GDAL_ENV):
        with rasterio.open(path_or_url) as src:
            win = from_bounds(*bounds, transform=src.transform)
            win = win.round_offsets().round_lengths()
            arr = src.read(1, window=win)
            return arr, src.window_transform(win)


def pixel_index(transform, height: int, width: int):
    """Global (col, row) grid ids for every cell of a windowed read."""
    left, top = transform.c, transform.f
    cols = np.round((left / schema.RES_M) + np.arange(width)).astype(int)
    rows = np.round((top / schema.RES_M) - 1 - np.arange(height)).astype(int)
    return cols, rows


def granule_layers(url_base: str, product: str, bounds, layers=None) -> dict:
    """Read the core layers of one granule and decode them with the hard-coded
    scales. Never reads scale/offset from the COG -- see s1.schema."""
    from s1.search import layer_url
    layers = layers or schema.CORE_LAYERS[product]
    out, tf = {}, None
    for name in layers:
        raw, tf = read_window(layer_url(url_base, name), bounds)
        out[name] = raw if name == "Fmask" else schema.decode(product, name, raw)
        out[f"_raw_{name}"] = raw
    out["_transform"] = tf
    return out
