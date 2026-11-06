# Recreating the results

This is the build sheet for the whole program: what to download, in what order to run it,
how long each step takes, and what numbers should come out. It was followed end to end on a
clean checkout on 2026-11-06, and every figure quoted below is what that run printed.

You need a laptop, an internet connection and one free account. No cloud compute, no GPU,
no paid data. The cost is about 243 MB of downloads, under two minutes of computation, and
however long NASA's extraction service takes to fill eight orders — usually a few hours.

## 1. What comes out

| Question | Score |
|---|---|
| Leaf area index on a plot that was measured before, on a date nobody visited | R² 0.898, RMSE 0.411 LAI units |
| Leaf area index on a plot that was never measured | R² 0.863, RMSE 0.476 |
| The same, from a wall calendar alone, no satellite | R² 0.721, RMSE 0.679 |
| Measurement error of each stream, with nothing assumed to be truth | ground 0.759 PAI, satellite 0.020 EVI2, MODIS 1.143 LAI |
| Usable plot observations in the rebuilt spectral record | 14,406 on 411 of 1,075 dates, 2013-04-16 → 2026-08-04 |

Plus 56 numbered findings across five packages, each of which recomputes itself from the
data on every run and reports `Reproduces: NO` if its value has moved.

## 2. Software

```
git clone https://github.com/Mateiio/harvard-forest-spectral-modeling.git
cd harvard-forest-spectral-modeling
pip install -r requirements.txt
```

Python 3.14.4 on Windows 11 is what the verification run used. Nothing here is
platform-specific; paths come from `pathlib`. One pin matters: `pygam` holds `scipy` below
1.17, so installing it downgrades scipy. Nothing else needs 1.17.

`requirements.txt` lists `earthaccess`, which this route does not use. `python -m s1 check`
will say

```
earthaccess  : NOT INSTALLED
online ready : False
```

and that is the correct state here. `earthaccess` belongs to the alternative path that reads
native satellite images instead of the extraction service, and that path is not wired to a
command.

## 3. The one account

NASA Earthdata Login, free and self-service: <https://urs.earthdata.nasa.gov/users/new>.

It is used only to place orders in a browser at AppEEARS, NASA's point-extraction service
(<https://appeears.earthdatacloud.nasa.gov/>). The code never authenticates: the granule
search it runs is a public endpoint, and the order results are plain CSV files you download
by hand.

## 4. Data

Fifteen archive files, 211 MB, plus eight order results, 32 MB. They go in one directory
tree of your choosing; the code finds it through the environment variable `HF_DATA_ROOT`.

```
setx HF_DATA_ROOT "D:\hf-data"        # Windows, then open a new shell
export HF_DATA_ROOT=/data/hf-data     # macOS / Linux
```

Unset, every path silently resolves against a relative `data/` and every input reads as
missing. `python -m wp0 check` prints the root it resolved and counts how many of the fifteen
it can see.

The satellite order cannot be placed until the code has worked out which 95 ground cells to
ask for, so downloading and running interleave. Five phases.

### Phase 1 · Harvard Forest archive (14 files, 211 MB)

Data files follow `https://harvardforest1.fas.harvard.edu/data/pNN/hfNNN/<filename>`. Use the
`harvardforest1` host; the name without the `1` redirects. Metadata follows
`https://harvardforest1.fas.harvard.edu/data/eml/hfNNN.xml`. All of it is CC0; cite the
individual datasets, not this repository.

| Destination under `HF_DATA_ROOT` | Source path | MB |
|---|---|---|
| `HF365Dataset/hf365-01-hls-evi2.csv` | `p36/hf365/` | 0.06 |
| `HF365Dataset/hf365-02-hls-ndvi.csv` | `p36/hf365/` | 0.06 |
| `HF365Dataset/hf365-03-hls-nirv.csv` | `p36/hf365/` | 0.06 |
| `HF375/hf375-01-field-sites-points.csv` | `p37/hf375/` | 0.02 |
| `HF375/hf375-02-field-sites-plots.csv` | `p37/hf375/` | 0.04 |
| `HF069/hf069-01-lai-plot.csv` | `p06/hf069/` | 0.34 |
| `HF069/hf069-02-lai-site.csv` | `p06/hf069/` | 0.02 |
| `HF004/hf004-01-final.csv` | `p00/hf004/` | 69.03 |
| `HF206/hf206-05-EMS-understory.csv` | `p20/hf206/` | 140.20 |
| `HF_EML/hf069.xml` | `eml/` | 0.24 |
| `HF_EML/hf365.xml` | `eml/` | 0.12 |
| `HF_EML/hf375.xml` | `eml/` | 0.03 |
| `HF_EML/hf206.xml` | `eml/` | 0.33 |
| `HF_EML/hf004.xml` | `eml/` | 0.09 |

The fifteenth input is the MODIS order placed in phase 3.

The metadata XML is not decoration. Plot status, plot radius, and the fact that the ground
column named `lai` is actually plant area index all come from `hf069.xml` and contradict both
the CSV headers and the program's own planning document. Findings F01, F02, F03 and F11 are
those contradictions.

Two files carry most of the bytes and only two findings. `hf004-01-final.csv` (69 MB) is
needed for the timestamp test in stage D; `hf206-05-EMS-understory.csv` (140 MB) is needed
for finding F15 and for S4. Skip both and the core chain still runs — see §9.

### Phase 2 · Build the foundation

```
python -m wp0 run
```

22 seconds. This writes plot geometry, the plot-to-cell crosswalks, recovered reflectance, a
solar table and the cleaned ground record, and prints a pass/fail line for each of fifteen
assertions. Everything downstream reads these files.

### Phase 3 · Order the satellite data

**The 95 cell centres.** The order needs one coordinate per 30 m satellite cell that any of
the 40 ground plots touches. Phase 2 has just computed them; this reshapes them into the
format the order form wants.

```python
import pandas as pd, pathlib
cw = pd.read_csv('wp0/out/crosswalk_plot_to_hls.csv')
g = cw[cw['plot'].str.match(r'^[A-H][1-5]$')]
p = (g[['hls_pixel', 'pix_centre_lat', 'pix_centre_lon']].drop_duplicates('hls_pixel')
     .rename(columns={'hls_pixel': 'ID', 'pix_centre_lat': 'Latitude',
                      'pix_centre_lon': 'Longitude'}))
p['Category'] = 'hls_pixel'
p = (p[['ID', 'Category', 'Latitude', 'Longitude']]
     .sort_values('ID', ignore_index=True).round({'Latitude': 6, 'Longitude': 6}))
pathlib.Path('s1/out').mkdir(parents=True, exist_ok=True)
p.to_csv('s1/out/appeears_hls_pixel_centres.csv', index=False)   # 95 rows
```

This file is a dependency of `s1/appeears.py` that no committed code writes — the original
was made in a notebook. The snippet above reproduces it exactly: same 95 identifiers, zero
difference in either coordinate.

**Eight orders.** At AppEEARS choose *Extract → Point*, upload
`appeears_hls_pixel_centres.csv`, and place seven orders for satellite reflectance plus one
for MODIS. The record is split by date because one order of this length times out.

| Order name | Product | Window |
|---|---|---|
| `HF-EMS-95px-HLSL30-2013-2015` | HLSL30.020 | 2013-01-01 → 2014-12-31 |
| `HF-EMS-95px-HLSL30-2015-2020` | HLSL30.020 | 2015-01-01 → 2020-06-06 |
| `HF-EMS-95px-HLSL30-2020-2023` | HLSL30.020 | 2020-06-07 → 2023-12-15 |
| `HF-EMS-95px-HLSL30-2023-2026` | HLSL30.020 | 2023-12-16 → 2026-08-08 |
| `HF-EMS-95px-HLSS30-2015-2020` | HLSS30.020 | 2015-01-01 → 2020-10-14 |
| `HF-EMS-95px-HLSS30-2020-2023` | HLSS30.020 | 2020-10-15 → 2023-12-03 |
| `HF-EMS-95px-HLSS30-2023-2026` | HLSS30.020 | 2023-12-04 → 2026-08-08 |

Layers, per order:

- HLSL30.020 (Landsat 8/9): `B02 B03 B04 B05 B06 B07 B09 SAA SZA VAA VZA Fmask`
- HLSS30.020 (Sentinel-2): `B02 B03 B04 B8A B11 B12 B10 SAA SZA VAA VZA Fmask`

`B09` on Landsat and `B10` on Sentinel-2 are the cirrus bands. They are needed because the
quality layer in this product version cannot flag cirrus at all — the bit is reserved and
always zero, so the pipeline derives its own proxy from the band (S1-12). `Fmask` is the
quality layer; Landsat orders return it whether or not you tick it, Sentinel-2 orders need it
asked for. The two satellites also name their near-infrared band differently, `B05` against
`B8A`, which is one of the things the offline self-test checks.

The MODIS order is five points, not 95, because one MODIS cell is 500 m across and swallows
the whole plot network in five cells:

| ID | Latitude | Longitude |
|---|---|---|
| `pixel1` | 42.539583 | -72.177657 |
| `pixel2` | 42.539583 | -72.172002 |
| `pixel3` | 42.535417 | -72.178496 |
| `pixel4` | 42.535417 | -72.172841 |
| `pixel5` | 42.535417 | -72.167186 |

Product `MCD15A2H.061`, window 2014-12-27 → 2020-12-26, layers `Lai_500m LaiStdDev_500m
Fpar_500m FparStdDev_500m FparLai_QC FparExtra_QC`. Keep the IDs exactly as written: the
collocation code matches on them, and WP0 stage B asserts that each one round-trips to the
right MODIS tile row and column.

**Where the results go.** Unzip each order into its own directory:

```
HF_DATA_ROOT/
  HLSV2Landsat/HF-EMS-95px-HLSL30-2013-2015/...-results.csv
  HLSV2Landsat/HF-EMS-95px-HLSL30-2015-2020/...
  HLSV2Landsat/HF-EMS-95px-HLSL30-2020-2023/...
  HLSV2Landsat/HF-EMS-95px-HLSL30-2023-2026/...
  HLSV2Sentinel-2/HF-EMS-95px-HLSS30-2015-2020/...
  HLSV2Sentinel-2/HF-EMS-95px-HLSS30-2020-2023/...
  HLSV2Sentinel-2/HF-EMS-95px-HLSS30-2023-2026/...
  MODIS/Main5Pixels-PointSample-MCD15A2H-061-results.csv
```

The loader globs `HLSV2*/*/*-results.csv`, so the two parent directory names matter and the
order directory names do not. The MODIS filename does matter; it is read by exact path.

### Phase 4 · The three studies

```
python -m s1 selftest                                   #  3 s, offline, 34 checks
python -m s1 stage 0                                    #  7 s, public granule search
python -c "from s1 import pipeline; pipeline.run()"     # 11 s
python -c "from s1 import results; results.run()"       #  4 s
python -m s7 run                                        #  4 s
python -c "from s1 import archive_export as a; a.run()" #  2 s
python -m s8 run                                        #  7 s
```

Three of those have no command of their own, because the pipeline was driven from notebooks
and only part of it was lifted into the command line. `python -m s1 run` stops after the
granule search and the grid check and prints *"online stages not yet wired to a full run"* —
that is the whole of what the command does, not a failure.

### Phase 5 · Optional

```
python -m s4 build       # 20 s, reads both large files
python -m s4 findings
```

S4 is deliberately unfinished, and its own finding S4-07 is the reason: six point light
sensors under a closed canopy measure sunfleck statistics, not the spatial average the study
needed. The data layer and the machinery are built; no model was fitted.

## 5. Order of operations

Two dependencies cross package boundaries and neither is obvious.

**The granule search must run before WP0's findings.** Finding F05 reads the manifest that
`python -m s1 stage 0` writes. Regenerate WP0's findings before that and you get *14 of 15
findings reproduce*, with F05 reporting `manifest not built`. The finding is fine; the order
was wrong.

**Triple collocation must run before the archive export.** `s7` writes a per-observation
uncertainty column back onto `s1/out/hf365_v2_candidate.csv`. Export the deliverable files
first and that column is missing from them.

So the full regeneration, once phase 3 has landed, is:

```
python -m s1 stage 0
python -c "from s1 import pipeline; pipeline.run()"
python -c "from s1 import results; results.run()"
python -m s7 run
python -c "from s1 import archive_export as a; a.run()"
python -m s8 run
python -m wp0 findings
python -m s1 findings
python -m s7 findings
```

## 6. What you should see

Totals from the 2026-11-06 clean run:

| Command | Result |
|---|---|
| `python -m wp0 check` | `raw inputs : 15/15 present` |
| `python -m wp0 run` | every stage check PASS, 22 s |
| `python -m s1 selftest` | 34 checks, `ALL PASS`, no network |
| `python -m s1 stage 0` | 1,198 granules, 7 checks PASS |
| `s1.pipeline.run()` | 109,185 cell observations, 1,155 acquisitions, 46,200 plot rows, 14,406 usable, 411 of 1,075 dates |
| `python -m s7 run` | ground 0.75881, satellite 0.01969, MODIS 1.14346; 14,406 rows given an uncertainty |
| `python -m s8 run` | 2,894 pairs, 37 plots, 92 campaigns; R² 0.8977 / RMSE 0.4111 |
| `python -m wp0 findings` | 15 of 15 |
| `python -m s1 findings` | 15 of 15 |
| `python -m s7 findings` | 8 of 8 |
| `python -m s8 findings` | 11 of 11 |
| `python -m s4 findings` | 7 of 7 |

Intermediate values worth checking if a total comes out wrong:

- WP0 stage B: 7 of the 40 plots sit wholly inside one satellite cell; median overlap for a
  10 m plot is 0.7687.
- WP0 stage C: reflectance recovered from the published indices closes on them to 0.00059,
  against a storage-rounding floor of 0.00045.
- WP0 stage D: lowest solar zenith over 2008–2026 is 19.19°, against 19.10° predicted from
  the site latitude. The hourly tower timestamps are shown to label interval starts, by a
  vertex lag of −0.506 h.
- WP0 stage LAI: 9,922 clean rows, 46 plots, 288 campaigns, nine rejected plot labels.
- S1: 31.4 % of cell observations survive quality masking. Most of the loss is the provider's
  own discard rule for high-aerosol retrievals, which costs 55 points of coverage and is not
  optional (S1-13).
- S8 model ladder, in order: calendar 0.7211, EVI2 0.8224, all three indices 0.8452, indices
  plus calendar 0.8620, plus plot identity 0.8977.

## 7. What will not match, and why

**The granule counts.** They come from a live search service and grow. The committed findings
were frozen on 2026-08-30 at 1,161 granules (677 Landsat, 484 Sentinel-2); the same query on
2026-11-06 returned 1,198 (696 and 502). Three findings quote that service and all three move
together: S1-15's filename-timestamp mismatch 468 → 486, its zone misreports 345 → 354, and
S1-10's pre-Collection-1 share 224 of 484 → 224 of 502. The numerators are fixed, the
denominators are not. Nothing downstream depends on them; the plot-level product comes from
the orders, which are frozen files.

**The header line of `s1/FINDINGS.md`.** It reads *"6 AppEEARS point-sample bundles …
103,348 pixel-observations, 1,092 acquisitions, 13,746 usable plot-observations"*. Those are
pre-backfill numbers in a hardcoded string, and regenerating the file does not update them.
The findings in the body of that same file, and the pipeline itself, give seven orders,
109,185, 1,155 and 14,406. Trust the body.

**A fresh set of orders.** Place them today and the end date moves past 2026-08-08, so every
count shifts. To match exactly, use the windows in the table above.

Everything else reproduced to the digit, bootstrap confidence intervals included. There is no
unseeded randomness in the chain.

## 8. Shortcuts that do not work

Each of these was tried, measured and rejected. They are why the pipeline is shaped the way
it is.

- **Using the published spectral dataset instead of rebuilding it.** It stops in 2020 and
  reaches 1,364 ground-satellite pairs. The rebuild reaches 2,894; the extra five years of
  field campaigns are the whole reason the model has a usable sample (S8-03).
- **Treating the ground column named `lai` as leaf area index.** It is plant area index and
  includes wood. Its leaf-off reading averages 1.72 on a stand whose deciduous leaf area at
  that point is 0.08 (F11, S8-01).
- **Taking the plot radius from the spatial file.** It reports one area for all 46 plots,
  about 5 % low for the tower plots and 2.4× low for the nine harvest plots, which were
  expanded to 15 m radius in 2001 (F01, F02).
- **Filtering plots on the `Active` flag.** All 46 read active with no end date. Four have not
  been measured since 2001 (F03).
- **`df['D1']` on a raw spectral file.** Two column headers carry trailing spaces, so that
  raises `KeyError` (F08).
- **Grouping the ground file by plot and date without deduplicating.** 103 rows are genuine
  repeat measurements of the same plot-date and nothing in the file marks them (F10).
- **Parsing the acquisition time out of a granule filename.** For Sentinel-2 it is the orbit
  start, not the overpass, and it disagrees on 486 of 1,198 granules (S1-15).
- **Trusting the coordinate-system field in the granule metadata.** It fails to report the
  right UTM zone on 354 granules and one says the wrong one outright. Taken literally it puts
  every cell about 490 km from the forest (F05, S1-15).
- **Computing an index and then masking.** Masking runs first, deliberately. 1,605
  observations carry negative red reflectance and 98.8 % of those are flagged high-aerosol
  (S1-13).
- **Leaving the fill values alone.** The extraction service applies scale factors but does not
  convert fill: reflectance arrives as a literal −9999 on 236 observations and view angles as
  a literal 40000 on 190 (S1-14).
- **Random cross-validation folds.** Grouping folds by field campaign is what makes a random
  forest stop beating ridge regression; ungrouped folds let it memorise date-specific patterns
  (S8-06).
- **Bootstrapping rows in the triple collocation.** 1,800 rows are only 279 independent
  blocks, because every plot inside one MODIS cell shares that cell's value on a date. Row
  resampling gives intervals 2.2× too narrow (S7-06).
- **Running triple collocation on NDVI.** It saturates against leaf area, so the method's
  linearity requirement fails and it returns model error dressed as measurement error. EVI2
  passes the same test (S7-02).
- **Adding solar zenith angle as a predictor.** It is a day-of-year harmonic with 1.21° of
  residual scatter, so every route into the model is collinear with the calendar (S8-04).
- **Adding MODIS to the retrieval.** On the 1,393 pairs it reaches it moves R² by 0.0004. A
  500 m cell cannot resolve a 10 m plot (S8-05).

## 9. If you only have an afternoon

The offline subset needs no account, no orders and 1.4 MB of input: the three spectral files,
both spatial files, both ground files and the five metadata files.

```
python -m wp0 check            # reports 12/15 present; that is the expected state here
python -m wp0 stage A --check
python -m wp0 stage B --check
python -m wp0 stage C --check
python -m wp0 stage LAI
python -m s1 selftest
```

Verified on 2026-11-06: all four stages pass every assertion and the self-test reports
`ALL PASS` on 34 checks, with the two large tower files and the MODIS order absent. Stage B
does not need the MODIS file despite listing it as an input — its MODIS grid check
round-trips five hardcoded cell indices rather than reading the order.

That is 34 checks against a synthetic satellite image plus WP0's geometry, reflectance and
ground-record assertions — the parts most likely to break on a different machine. Stage D
needs the 69 MB tower file; everything past it needs the orders.

## 10. Reading the output

`python -m <package> findings` rewrites that package's `FINDINGS.md` from whatever is on disk
and marks `Reproduces: NO` on any finding whose value has moved or whose inputs are gone.
Where a module docstring and a findings file disagree, the findings file is current.

What it all means, weaknesses included, is in
[predicting-forest-leaf-area.md](predicting-forest-leaf-area.md). Per-dataset notes, including
where each file comes from and what is wrong with it, are in
[data-catalog.md](data-catalog.md).
