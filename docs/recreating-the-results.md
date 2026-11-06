# Recreating the results

Fifteen steps, from a bare laptop to the numbers in the README. Each one is a command or a
download. Done end to end on a clean checkout on 2026-11-06; every number below is what that
run printed.

You need a laptop, an internet connection and one free account. About 243 MB of downloads,
under two minutes of computation, and a wait of a few hours while NASA fills eight data
orders.

## What comes out

| Question | Score |
|---|---|
| Leaf area index on a plot measured before, on a date nobody visited | R² 0.898, RMSE 0.411 LAI units |
| Leaf area index on a plot that was never measured | R² 0.863, RMSE 0.476 |
| The same, from a wall calendar alone, no satellite | R² 0.721, RMSE 0.679 |
| Measurement error of each stream, nothing assumed to be truth | ground 0.759 PAI, satellite 0.020 EVI2, MODIS 1.143 LAI |
| Usable plot observations in the rebuilt spectral record | 14,406 on 411 of 1,075 dates, 2013-04-16 to 2026-08-04 |

Plus 56 numbered findings across five packages. Each one recomputes itself from the data on
every run and reports `Reproduces: NO` if its value has moved.

## Step 1. Install the code

```
git clone https://github.com/Mateiio/harvard-forest-spectral-modeling.git
cd harvard-forest-spectral-modeling
pip install -r requirements.txt
```

Python 3.14.4 on Windows 11 is what the verification run used. Nothing is platform-specific.

`pygam` holds `scipy` below 1.17, so installing it downgrades scipy. Nothing else needs 1.17.

`requirements.txt` also lists `earthaccess`. You do not need it. It belongs to a different way
of getting the satellite data that is not wired to a command, so `python -m s1 check` will
report `earthaccess: NOT INSTALLED` and `online ready: False`. That is correct here.

## Step 2. Get a NASA Earthdata login

Free and self-service: <https://urs.earthdata.nasa.gov/users/new>.

You use it only to place orders in a browser at AppEEARS, NASA's point-extraction service
(<https://appeears.earthdatacloud.nasa.gov/>). The code never logs in to anything. The
satellite search it runs is a public endpoint, and the orders come back as plain CSV files you
download by hand.

## Step 3. Make a data folder and tell the code where it is

The archive files do not live in the repository. Pick any folder and set one environment
variable.

```
setx HF_DATA_ROOT "D:\hf-data"        # Windows, then open a new shell
export HF_DATA_ROOT=/data/hf-data     # macOS / Linux
```

If you skip this, every path resolves against a relative `data/` and every input reads as
missing, with no error.

## Step 4. Download 14 files from Harvard Forest

Data files are at `https://harvardforest1.fas.harvard.edu/data/pNN/hfNNN/<filename>`. Metadata
is at `https://harvardforest1.fas.harvard.edu/data/eml/hfNNN.xml`. Use the `harvardforest1`
host; the name without the `1` redirects.

| Save as, under `HF_DATA_ROOT` | From | MB |
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

All of it is CC0. Cite the individual datasets, not this repository.

Do not skip the five XML files. Plot status, plot radius, and the fact that the ground column
named `lai` is actually plant area index all come from `hf069.xml`, and all three contradict
the CSV headers. Findings F01, F02, F03 and F11 are those contradictions.

Two files are most of the bytes and only two findings. `hf004-01-final.csv` is needed for the
timestamp test in stage D. `hf206-05-EMS-understory.csv` is needed for finding F15 and for S4.
Leave both out and the main chain still runs; see "A shorter version" below.

## Step 5. Check that the code can see the files

```
python -m wp0 check
```

It prints the folder it resolved and counts the inputs. You should see `raw inputs : 14/15
present`. The fifteenth is the MODIS order, which you place in step 8.

## Step 6. Build the foundation

```
python -m wp0 run
```

22 seconds. Writes plot geometry, the plot-to-cell crosswalks, recovered reflectance, a solar
table and the cleaned ground record, and prints a pass or fail line for each of fifteen
assertions. Everything later reads these files.

## Step 7. Make the list of 95 coordinates

The satellite order needs one coordinate per 30 m cell that any of the 40 ground plots
touches. Step 6 has just worked them out. This reshapes them into the format the order form
wants.

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

This step exists because of a gap in the repository. `s1/appeears.py` reads that file, and no
committed code writes it; the original was made in a notebook. The snippet reproduces it
exactly: same 95 identifiers, zero difference in either coordinate.

## Step 8. Place eight orders at AppEEARS

Choose **Extract → Point** and upload `appeears_hls_pixel_centres.csv` from step 7.

Place seven orders for satellite reflectance. The record is split by date because one order
covering all of it times out.

| Order name | Product | Window |
|---|---|---|
| `HF-EMS-95px-HLSL30-2013-2015` | HLSL30.020 | 2013-01-01 to 2014-12-31 |
| `HF-EMS-95px-HLSL30-2015-2020` | HLSL30.020 | 2015-01-01 to 2020-06-06 |
| `HF-EMS-95px-HLSL30-2020-2023` | HLSL30.020 | 2020-06-07 to 2023-12-15 |
| `HF-EMS-95px-HLSL30-2023-2026` | HLSL30.020 | 2023-12-16 to 2026-08-08 |
| `HF-EMS-95px-HLSS30-2015-2020` | HLSS30.020 | 2015-01-01 to 2020-10-14 |
| `HF-EMS-95px-HLSS30-2020-2023` | HLSS30.020 | 2020-10-15 to 2023-12-03 |
| `HF-EMS-95px-HLSS30-2023-2026` | HLSS30.020 | 2023-12-04 to 2026-08-08 |

Layers to tick, the same for every order of that product:

- HLSL30.020, Landsat 8 and 9: `B02 B03 B04 B05 B06 B07 B09 SAA SZA VAA VZA Fmask`
- HLSS30.020, Sentinel-2: `B02 B03 B04 B8A B11 B12 B10 SAA SZA VAA VZA Fmask`

`B09` on Landsat and `B10` on Sentinel-2 are the cirrus bands. You need them because the
quality layer in this product version cannot flag cirrus at all: the bit is reserved and
always zero, so the code derives its own proxy from the band (S1-12). `Fmask` is the quality
layer. Landsat orders return it whether or not you tick it; Sentinel-2 orders do not.

Then place one order for MODIS, five points rather than 95, because one MODIS cell is 500 m
across and swallows the whole plot network in five cells.

| ID | Latitude | Longitude |
|---|---|---|
| `pixel1` | 42.539583 | -72.177657 |
| `pixel2` | 42.539583 | -72.172002 |
| `pixel3` | 42.535417 | -72.178496 |
| `pixel4` | 42.535417 | -72.172841 |
| `pixel5` | 42.535417 | -72.167186 |

Product `MCD15A2H.061`, window 2014-12-27 to 2020-12-26, layers `Lai_500m LaiStdDev_500m
Fpar_500m FparStdDev_500m FparLai_QC FparExtra_QC`. Type those five IDs exactly as written.
The collocation code matches on them, and step 6 asserts that each one lands on the right
MODIS tile row and column.

Orders usually fill within a few hours.

## Step 9. Unzip the orders where the code looks

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

The loader globs `HLSV2*/*/*-results.csv`, so the two parent folder names matter and the order
folder names do not. Rename the MODIS file to match exactly; it is read by its full path.
`python -m wp0 check` should now say `15/15 present`.

## Step 10. Test the satellite code offline

```
python -m s1 selftest
```

3 seconds, no network. 34 checks against a synthetic satellite image: band naming, scale
factors, fill values, quality-bit decoding, index arithmetic and plot aggregation. Expect
`ALL PASS`.

## Step 11. Search for the satellite images

```
python -m s1 stage 0
```

7 seconds. Queries NASA's public granule catalogue and writes the manifest that later steps
read. Needs no login.

## Step 12. Rebuild the spectral record

```
python -c "from s1 import pipeline; pipeline.run()"     # 11 s
python -c "from s1 import results; results.run()"       #  4 s
```

The first masks every cell observation before computing any index, then aggregates to plots.
The second writes the comparison tables against the published version.

Neither has a command of its own, because the pipeline was driven from notebooks and only part
of it was lifted into the command line. `python -m s1 run` stops after step 11 and prints
`online stages not yet wired to a full run`. That is the whole of what it does, not a failure.

## Step 13. Estimate each stream's error

```
python -m s7 run
```

4 seconds. Estimates the measurement error of the ground, satellite and MODIS streams without
treating any of them as truth, then writes a per-observation uncertainty column back onto the
rebuilt record.

Run this before the next command. It edits `s1/out/hf365_v2_candidate.csv`, and the export
below copies that file into the deliverable tables.

```
python -c "from s1 import archive_export as a; a.run()"   # 2 s
```

## Step 14. Fit the model

```
python -m s8 run
```

7 seconds. Builds the ground-to-satellite pairs, scores eight models, scores forecasting at
four horizons, then recomputes its own findings. This is where R² 0.898 comes from.

## Step 15. Regenerate every findings file

```
python -m wp0 findings
python -m s1 findings
python -m s7 findings
```

Run these after step 11, not before. Finding F05 reads the manifest that step 11 writes, and
without it `wp0 findings` reports `14 of 15` with F05 saying `manifest not built`. The finding
is fine; the order was wrong.

## Optional: the unfinished study

```
python -m s4 build       # 20 s, reads both large files
python -m s4 findings
```

S4 is deliberately incomplete, and its own finding S4-07 says why: six point light sensors
under a closed canopy measure sunfleck statistics, not the spatial average the study needed.
The data layer and the machinery are built. No model was fitted.

## Check your numbers against mine

From the 2026-11-06 clean run:

| Command | Result |
|---|---|
| `python -m wp0 check` | `raw inputs : 15/15 present` |
| `python -m wp0 run` | every stage check PASS, 22 s |
| `python -m s1 selftest` | 34 checks, `ALL PASS` |
| `python -m s1 stage 0` | 1,198 granules, 7 checks PASS |
| `s1.pipeline.run()` | 109,185 cell observations, 1,155 acquisitions, 46,200 plot rows, 14,406 usable, 411 of 1,075 dates |
| `python -m s7 run` | ground 0.75881, satellite 0.01969, MODIS 1.14346; 14,406 rows given an uncertainty |
| `python -m s8 run` | 2,894 pairs, 37 plots, 92 campaigns; R² 0.8977, RMSE 0.4111 |
| `python -m wp0 findings` | 15 of 15 |
| `python -m s1 findings` | 15 of 15 |
| `python -m s7 findings` | 8 of 8 |
| `python -m s8 findings` | 11 of 11 |
| `python -m s4 findings` | 7 of 7 |

If a total is off, these intermediate values narrow it down:

- Step 6, stage B: 7 of the 40 plots sit wholly inside one satellite cell; median overlap for
  a 10 m plot is 0.7687.
- Step 6, stage C: reflectance recovered from the published indices closes on them to 0.00059,
  against a storage-rounding floor of 0.00045.
- Step 6, stage D: lowest solar zenith over 2008 to 2026 is 19.19°, against 19.10° predicted
  from the site latitude. The hourly tower timestamps come out as interval starts, by a vertex
  lag of -0.506 h.
- Step 6, stage LAI: 9,922 clean rows, 46 plots, 288 campaigns, nine rejected plot labels.
- Step 12: 31.4 % of cell observations survive quality masking. Most of the loss is the
  provider's own discard rule for high-aerosol retrievals, which costs 55 points of coverage
  and is not optional (S1-13).
- Step 14, model ladder in order: calendar 0.7211, EVI2 0.8224, all three indices 0.8452,
  indices plus calendar 0.8620, plus plot identity 0.8977.

## What will not match, and why

**The granule counts.** They come from a live catalogue and grow. The committed findings were
frozen on 2026-08-30 at 1,161 granules, 677 Landsat and 484 Sentinel-2. The same query on
2026-11-06 returned 1,198, being 696 and 502. Three findings quote the catalogue and all three
move together: S1-15's filename-timestamp mismatch 468 to 486, its zone misreports 345 to 354,
and S1-10's pre-Collection-1 share 224 of 484 to 224 of 502. The numerators are fixed, the
denominators are not. Nothing downstream depends on them; the plot-level product comes from
the orders, which are frozen files.

**The header line of `s1/FINDINGS.md`.** It reads `6 AppEEARS point-sample bundles … 103,348
pixel-observations, 1,092 acquisitions, 13,746 usable plot-observations`. Those are
pre-backfill numbers in a hardcoded string, and regenerating the file does not update them.
The findings in the body of that same file, and the pipeline itself, give seven orders,
109,185, 1,155 and 14,406. Trust the body.

**A fresh set of orders.** Place them today and the end date moves past 2026-08-08, so every
count shifts. To match exactly, use the windows in step 8.

Everything else reproduced to the digit, bootstrap confidence intervals included. There is no
unseeded randomness in the chain.

## Shortcuts that do not work

Each was tried, measured and rejected. They are why the steps are shaped the way they are.

- **Using the published spectral dataset instead of rebuilding it.** It stops in 2020 and
  reaches 1,364 ground-satellite pairs. The rebuild reaches 2,894. The extra five years of
  field campaigns are the whole reason the model has a usable sample (S8-03).
- **Treating the ground column named `lai` as leaf area index.** It is plant area index and
  includes wood. Its leaf-off reading averages 1.72 on a stand whose deciduous leaf area at
  that point is 0.08 (F11, S8-01).
- **Taking the plot radius from the spatial file.** It reports one area for all 46 plots, about
  5 % low for the tower plots and 2.4 times low for the nine harvest plots, which were widened
  to 15 m radius in 2001 (F01, F02).
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
- **Leaving the fill values alone.** AppEEARS applies scale factors but does not convert fill:
  reflectance arrives as a literal -9999 on 236 observations and view angles as a literal
  40000 on 190 (S1-14).
- **Random cross-validation folds.** Grouping folds by field campaign is what makes a random
  forest stop beating ridge regression. Ungrouped folds let it memorise date-specific patterns
  (S8-06).
- **Bootstrapping rows in the error estimate.** 1,800 rows are only 279 independent blocks,
  because every plot inside one MODIS cell shares that cell's value on a date. Row resampling
  gives intervals 2.2 times too narrow (S7-06).
- **Running the error estimate on NDVI.** It saturates against leaf area, so the method's
  linearity requirement fails and it returns model error dressed as measurement error. EVI2
  passes the same test (S7-02).
- **Adding solar zenith angle as a predictor.** It is a day-of-year harmonic with 1.21° of
  residual scatter, so every route into the model is collinear with the calendar (S8-04).
- **Adding MODIS to the retrieval.** On the 1,393 pairs it reaches it moves R² by 0.0004. A
  500 m cell cannot resolve a 10 m plot (S8-05).

## A shorter version

No account, no orders, 1.4 MB of input: the three spectral files, both spatial files, both
ground files and the five XML files from step 4.

```
python -m wp0 check            # says 12/15 present; expected here
python -m wp0 stage A --check
python -m wp0 stage B --check
python -m wp0 stage C --check
python -m wp0 stage LAI
python -m s1 selftest
```

Verified on 2026-11-06: all four stages pass every assertion and the self-test reports
`ALL PASS` on 34 checks, with the two large tower files and the MODIS order absent. Stage B
does not need the MODIS file despite recording it as an input; its MODIS grid check lands five
hardcoded cell indices rather than reading the order.

That covers the geometry, the reflectance recovery, the ground-record cleaning and the
synthetic-image tests, which are the parts most likely to break on a different machine. Stage
D needs the 69 MB tower file. Everything past it needs the orders.

## Reading the output

`python -m <package> findings` rewrites that package's `FINDINGS.md` from whatever is on disk
and marks `Reproduces: NO` on any finding whose value has moved or whose inputs are gone.
Where a module docstring and a findings file disagree, the findings file is current.

What it all means, weaknesses included, is in
[predicting-forest-leaf-area.md](predicting-forest-leaf-area.md). Per-dataset notes, including
where each file comes from and what is wrong with it, are in
[data-catalog.md](data-catalog.md).
