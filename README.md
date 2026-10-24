# harvard-forest-spectral-modeling

Retrieving ground leaf area index from satellite reflectance at the Harvard Forest EMS
tower, Petersham, Massachusetts. Ground data is HF069 plant area index. Satellite data is
HLS v2.0 (Landsat 8/9 and Sentinel-2), reprocessed here rather than taken as published.
MODIS supplies the third stream for a triple-collocation error estimate.

Ridge regression on EVI2, NDVI, NIRv, day of year and plot identity gives R² 0.898 and
RMSE 0.411 LAI units for a known plot on an unvisited date, cross-validated by field
campaign. Day of year alone gives R² 0.721.

Write-up, including the weaknesses:
[docs/predicting-forest-leaf-area.md](docs/predicting-forest-leaf-area.md).

## Packages

| | Contents | Commands |
|---|---|---|
| [`wp0/`](wp0/) | Input registry with MD5 provenance, plot centroids, HLS and MODIS crosswalks, solar table, HF069 roster cleaning, PAI→LAI variants | `check` `run` `stage` `findings` |
| [`s1/`](s1/) | HF365 rebuilt from HLS v2.0: CMR search, Fmask decoding, masking before indices, a synthetic granule for testing | `check` `selftest` `stage` `run` `findings` |
| [`s7/`](s7/) | Triple collocation: error variance for three collocated streams, blocked bootstrap, correlated-error sweep | `run` `findings` |
| [`s8/`](s8/) | Ground LAI retrieval: campaign-grouped CV, the model ladder, forecast by horizon | `build` `fit` `forecast` `findings` |
| [`s4/`](s4/) | Matched-SZA decomposition. Incomplete: the available sensors cannot answer the question, see S4-07 | `build` `findings` |
| [`study2/`](study2/) | Solar zenith angle and the HF365 record. Ingest and QC only, see [study2/README.md](study2/README.md) | |

Run as `python -m <package> <command>`.

`python -m <package> findings` regenerates that package's `FINDINGS.md` from the artifacts
on disk. A finding whose inputs are missing, or whose recomputed value no longer matches,
is marked `Reproduces: NO`. Where a module docstring and a findings file disagree, the
findings file is the current one.

Each package also keeps its notebook, with outputs saved.

## Running it

```
pip install -r requirements.txt
```

Python 3.14 on Windows. `pygam` holds `scipy` below 1.17.

The archive data is not in this repository. HF069, the AppEEARS bundles and the MODIS
extracts run to several hundred megabytes and are available from their sources. Set
`HF_DATA_ROOT` to your local copy:

```
setx HF_DATA_ROOT "<path to your data root>"
```

Outputs are written to each package's own `out/`, which is ignored here. `wp0` runs first;
the others read its artifacts.

```
python -m wp0 check     # which of the 15 raw inputs are present
python -m wp0 run       # ~15 s, writes the foundation artifacts
python -m s1 selftest   # 34 checks against a synthetic granule, offline
```

S1 stages past stage 0 need a NASA Earthdata login, read from `~/.netrc` or from
`EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD`.

## Data

HF069 from the Harvard Forest Data Archive, HLS v2.0 (`HLSL30.020` / `HLSS30.020`, tile
T18TYN) via AppEEARS, and MODIS MCD15A2H v061. Cite those for the measurements, not this
repository. The code is MIT licensed.

## archive/

[`archive/actions/`](archive/actions/) is the earlier notebook work against the published
HF365 and MODIS records, numbered in the order it was done. Superseded by the packages
above; `07-hls-recreation` is the route `s1` replaced.
