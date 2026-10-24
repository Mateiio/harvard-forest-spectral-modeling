# WP0 findings

*Regenerated 2026-08-30 by `python -m wp0 findings`. Every number below is recomputed from the raw archive files on each run; nothing is transcribed.*

**15 of 15 findings reproduce.**

Reproduce any single one in isolation:

```
python -c "from wp0 import findings; print(findings.f07_hf365_dates())"
```

## Plot geometry and status

### F01 · Three of the 40 grid plots are 15 m radius, not 10 m

**Measured:** ['A4', 'A5', 'B5'] -- area 707 m2 vs 314 m2, a factor of 2.25

**Why it matters:** A4, A5 and B5 are live HF365 columns. A flat 10 m radius understates their footprint by more than half and mis-weights their pixel overlap.

*Source:* hf069.xml abstract; wp0/registry.py · *Reproduce:* `wp0.findings.f01_plot_radii()` · *Reproduces:* yes

### F02 · hf375-02 gives one plot area for all 46 EMS plots; hf069.xml gives a radius that disagrees

**Measured:** AreaGISm2 = [np.int64(297)] for all 46 rows -> r = 9.723 m; hf069.xml says 10 m (314.16 m2), and 15 m (706.86 m2) for the harvest group

**Why it matters:** The field is wrong twice over: ~5 % low for tower plots, and 2.4x low for the nine harvest plots.

*Source:* hf375-02-field-sites-plots.csv vs hf069.xml · *Reproduce:* `wp0.findings.f02_area_conflict()` · *Reproduces:* yes

### F03 · hf375-02 reports all 46 EMS plots as active with no end date

**Measured:** Active='yes' for all: True; EndDate empty for all: True. G3/H3/H4 were removed in 2001 (beaver pond) and X4 ceased in 2001. Simes plots also carry StartDate [np.float64(1993.0)] though hf069.xml says 1999

**Why it matters:** Anyone filtering on Active gets 46 plots and silently includes four that have not been measured since 2001.

*Source:* hf375-02 Active/EndDate/StartDate vs hf069.xml abstract · *Reproduce:* `wp0.findings.f03_plot_status()` · *Reproduces:* yes

### F04 · The 30 m grid anchored on the UTM 18N origin is the real HLS grid for T18TYN

**Measured:** CMR reports ULX=699960.0, ULY=4800000.0 for every T18TYN granule; 699960 = 30x23332 and 4800000 = 30x160000, so floor(E/30) is the true pixel column

**Why it matters:** Every overlap fraction in the crosswalk depends on this. A 10 m anchor error would change all of them.

*Source:* CMR granule metadata; s1/grid.py · *Reproduce:* `wp0.findings.f04_grid_anchor()` · *Reproduces:* yes

### F05 · CMR's HORIZONTAL_CS_NAME does not reliably report the tile's UTM zone

**Measured:** 345 of 1161 granules do not report zone 18; one 2020 L30 granule reports 'UTM ZONE 19'. Zone 18 confirmed geometrically instead: read as EPSG:32618 the tile SE corner lands on CMR's own polygon exactly

**Why it matters:** Trusting that field would place every pixel about 490 km away.

*Source:* CMR AdditionalAttributes; s1/schema.py · *Reproduce:* `wp0.findings.f05_crs_metadata()` · *Reproduces:* yes

## HF365 spectral indices

### F06 · HF365's three index files are mutually consistent to the limit of their stored precision

**Measured:** recomputed EVI2 vs archived: residual sd 0.00059, against a rounding-only Monte Carlo floor of 0.00045

**Why it matters:** The audit finds nothing, which is the point: it licenses using the recovered bands as a product. RED comes back to 0.33 % relative (7.2e-05 absolute) in the growing season.

*Source:* wp0/bands.py -- EVI2 held out of the inversion · *Reproduce:* `wp0.findings.f06_band_closure()` · *Reproduces:* yes

### F07 · The three HF365 files have different, non-nested date sets

**Measured:** EVI2 261, NDVI 262, NIRv 262 dates; 260 in all three, 263 in the union. NDVI has 2019-07-12 and 2019-09-10 that EVI2 lacks; EVI2 has 2020-07-21 that NDVI lacks

**Why it matters:** Described in the program document as '261 versus 262', which implies one extra row. Any join assuming nesting drops or misaligns dates.

*Source:* wp0/bands.py:date_sets · *Reproduce:* `wp0.findings.f07_hf365_dates()` · *Reproduces:* yes

### F08 · HF365 column headers contain trailing whitespace

**Measured:** {'hf365_evi2': ['D1 ', 'F1 '], 'hf365_ndvi': ['D1 ', 'F1 '], 'hf365_nirv': ['D1 ', 'F1 ']}

**Why it matters:** df['D1'] raises KeyError on the raw file. Silent if the code happens to filter columns by pattern instead.

*Source:* hf365-01/02/03 headers · *Reproduce:* `wp0.findings.f08_hf365_whitespace()` · *Reproduces:* yes

## HF069 ground measurements

### F09 · hf069-01's plot column carries labels that are not EMS plots

**Measured:** 9 bad labels over 122 rows: ['1', 'A1CAM', 'BOG', 'PAR', 'RO', 'RO TOWE', 'TS1', 'TS2', 'VAN']

**Why it matters:** 'PAR' alone is 108 rows. A groupby on plot silently creates these as extra plots.

*Source:* hf069-01 plot column vs the hf375-02 roster; wp0/lai.py · *Reproduce:* `wp0.findings.f09_roster()` · *Reproduces:* yes

### F10 · hf069-01 contains duplicate (date, plot) rows

**Measured:** 103 duplicate rows -- genuine repeat measurements, but nothing in the file marks them as such

**Why it matters:** A naive load double-counts those plot-dates, inflating n and distorting any within-plot variance.

*Source:* hf069-01-lai-plot.csv · *Reproduce:* `wp0.findings.f10_duplicates()` · *Reproduces:* yes

### F11 · hf069-01's 'lai' column is plant area index, not leaf area index

**Measured:** EML says: "plant area index (PAI), and has not been corrected for woody material...."

**Why it matters:** PAI includes woody area. Using it as LAI overstates leaf area, most at leaf-off when the canopy is entirely woody.

*Source:* hf069.xml attributeDefinition vs the CSV header · *Reproduce:* `wp0.findings.f11_pai_not_lai()` · *Reproduces:* yes

### F12 · The LAI-2000 to LAI-2200 change in 2015 produces no detectable step

**Measured:** mean step +0.0190 PAI over 33 plots (paired t p=0.751, Wilcoxon p=0.659); between-plot sd is 0.340

**Why it matters:** hf069.xml claims 'consistent agreement' without numbers. This supplies them, so a record spanning 2015 can be used without a correction.

*Source:* wp0/lai.py, peak-season means blocked by plot · *Reproduce:* `wp0.findings.f12_instrument_step()` · *Reproduces:* yes

## HF206 understory microclimate

### F15 · hf206-05 contains duplicated timestamps, almost all of them a repeat of 2024

**Measured:** 20,350 rows share a duplicated timestamp (6.7 % of the file): 20,348 in 2024 and 2 in 2010. The 2024 rows are byte-identical; the 2010 pair carries conflicting values. Also 1 unparseable datetime

**Why it matters:** A naive load double-counts a year of understory PAR. The file is also not sorted by time, so slicing a datetime index fails before deduplication.

*Source:* hf206-05-EMS-understory.csv · *Reproduce:* `wp0.findings.f15_hf206_duplicates()` · *Reproduces:* yes

## Radiometry and solar geometry

### F13 · hf004-01 timestamps label the START of each hourly interval

**Measured:** parabola-vertex lag -0.5060 h, 95% CI [-0.5151, -0.4937], n=362 clear days -- excludes centre-labelling and end-labelling

**Why it matters:** fAPAR is a ratio of two PAR streams from different loggers; a stamp mismatch biases every value, worst where irradiance changes fastest. The intensity-weighted centroid gives -0.35 h and is wrong -- it is biased by afternoon cloud.

*Source:* wp0/solar.py:interval_labelling_test · *Reproduce:* `wp0.findings.f13_timestamp()` · *Reproduces:* yes

### F14 · Solstice-noon solar zenith at the tower matches the site latitude

**Measured:** minimum SZA over 2008-2026 is 19.19 deg; theory for 42.54 N is 42.54 - 23.44 = 19.10 deg

**Why it matters:** An independent check that the location, timezone and solar model are all wired up correctly.

*Source:* wp0/solar.py (pvlib NREL SPA) · *Reproduce:* `wp0.findings.f14_solar_geometry()` · *Reproduces:* yes

---

Archive defects formatted for the Harvard Forest information manager are in `wp0/out/archive_corrections.md`. Findings tagged for S6 evaluation, with contamination provenance, are in `wp0/out/answer_key.jsonl`.
