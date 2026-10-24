# harvard-forest-spectral-modeling

Can a satellite's view of color be turned into the number a ground crew measures with an
instrument under the canopy? This repository is the attempt, at Harvard Forest's EMS tower
site in Petersham, Massachusetts — ground plant-area measurements from the HF069 archive
against Landsat and Sentinel-2 surface reflectance, with MODIS as an independent third
opinion.

**Start here: [Predicting Forest Leaf Area from Satellites](docs/predicting-forest-leaf-area.md).**
It is the end-to-end account, written for a non-specialist, and it includes a section
stating plainly what is weak.

The short version: a ridge regression on three spectral indices plus day-of-year plus plot
identity reaches **R² 0.898** for a known plot on a date nobody visited. A wall calendar
with no satellite at all reaches 0.721, which is the number any claim about satellite skill
has to beat.

## The map

| | Question it answers | Run it with |
|---|---|---|
| [`wp0/`](wp0/) | What are the inputs, exactly, and have they changed? Plot geometry, pixel crosswalks, solar table, HF069 cleaning, the PAI→LAI variants | `python -m wp0 check \| run \| findings` |
| [`s1/`](s1/) | What does the satellite record look like rebuilt from HLS v2.0 rather than taken as published? | `python -m s1 check \| selftest \| run \| findings` |
| [`s7/`](s7/) | How wrong is each measurement, without assuming any of them is right? | `python -m s7 run \| findings` |
| [`s8/`](s8/) | How well can ground leaf area be retrieved, and forecast, from that record? | `python -m s8 build \| fit \| forecast \| findings` |
| [`s4/`](s4/) | Can illumination geometry be separated from canopy change? **Blocked** — the instruments cannot answer it, and the findings say so | `python -m s4 build \| findings` |
| [`study2/`](study2/) | Does sun angle bias the record? **Notebook one of several** | see [study2/README.md](study2/README.md) |

Each package carries a `FINDINGS.md` that `python -m <package> findings` **rewrites from
the artifacts on every run**. Numbers that stop being true stop appearing, and a finding
that fails to reproduce is marked FAIL rather than quietly dropped. When a module docstring
and a findings file disagree, the findings file is the one that was regenerated.

Each also has its narrative notebook beside its code, with outputs kept so it reads here
without running anything.

## Running it

```
pip install -r requirements.txt
```

Pinned against Python 3.14 on Windows. Note that `pygam` holds `scipy` below 1.17.

**The data is not in this repository**, and should not be: HF069, the AppEEARS bundles and
the MODIS extracts are third-party archive products, several hundred megabytes, and freely
available from their sources. Point the code at your local copy with one environment
variable:

```
setx HF_DATA_ROOT "<path to your data root>"
```

Every package reads its inputs from there and writes its own outputs into its own `out/`
directory, which is ignored here. They run in order, `wp0` first, because the others read
its artifacts:

```
python -m wp0 check     # reports which of the 15 raw inputs it can find
python -m wp0 run       # about 15 seconds; writes the foundation the rest depend on
python -m s1 selftest   # 34 checks against a synthetic granule: no credentials, no network
```

Because each `FINDINGS.md` is regenerated from whatever artifacts are on disk, running
`python -m <package> findings` on a tree where the upstream stages have not run marks the
affected findings `Reproduces: NO` rather than failing or inventing a number. That is the
intended behaviour. The committed files came from a complete run, and regenerate
byte-identically from it apart from their date line.

S1 stages past stage 0 need a NASA Earthdata login, read from `~/.netrc` or from
`EARTHDATA_USERNAME` / `EARTHDATA_PASSWORD`. No credential is stored in this repository.

## Data and attribution

Ground measurements come from **Harvard Forest Data Archive HF069**, satellite reflectance
from **NASA HLS v2.0** (`HLSL30.020` / `HLSS30.020`, tile T18TYN) via AppEEARS, and the
third collocated stream from **MODIS MCD15A2H v061**. Cite those sources, not this
repository, for the underlying measurements. Code here is MIT licensed; the data is not
ours to license.

## archive/

[`archive/actions/`](archive/actions/) holds the first generation of this work: exploratory
notebooks against the published HF365 and MODIS records, numbered in the order they were
done. They are kept because they record how the questions were arrived at, and superseded
by the packages above — `07-hls-recreation` in particular is the route that `s1` replaced.
