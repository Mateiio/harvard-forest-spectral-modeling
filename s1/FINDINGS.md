# S1 findings · HF365 reprocessed from HLS v2.0

*Regenerated 2026-08-30 by `python -m s1 findings`. Values are read from `s1/out/` on each run.*

**15 of 15 findings reproduce.**

Source: 6 AppEEARS point-sample bundles, 95 HLS pixel centres covering the 40 grid plots, tile T18TYN, 2015-2026. 103,348 pixel-observations, 1,092 acquisitions, 13,746 usable plot-observations.

## What changed between HLS v1.4 and v2.0

### S1-01 · The v1.4 to v2.0 change is in the NIR band, not the red

**Measured:** median dNIR +0.01342 (+5.1 % relative) vs dRED +0.00038 (+1.5 %); |dNIR| is 9.4x |dRED|; NIR dominant in 3765/4096 observations

**Impact:** Any index rebuilt from v2.0 shifts because NIR shifted. NDVI, EVI2 and NIRv all take NIR in the numerator.

*Source:* s1/compare.py; 4,096 paired observations over 129 shared dates, usable pixels only · *Reproduces:* yes

### S1-02 · The change exceeds the v1.4 reconstruction noise floor

**Measured:** floor NIR 0.00037, RED 0.000078; measured change is 48x the NIR floor

**Impact:** v1.4 is unobtainable, so its bands are reconstructed from 3-decimal indices. Without this the change could be storage rounding.

*Source:* wp0/bands.py Monte Carlo floor; s1/compare.py · *Reproduces:* yes

### S1-03 · The NIR change is seasonal, not a constant offset

**Measured:** growing season dNIR +0.02897 vs off season +0.00174 (16.6x larger); 71 % of changes are positive

**Impact:** A constant bias could be corrected with an offset. This cannot -- it scales with canopy NIR, so it changes seasonal amplitude.

*Source:* s1/results.py, DOY 150-250 as growing season · *Reproduces:* yes

### S1-04 · Both satellite streams show the same shift

**Measured:** L30 dNIR +0.01621 ; S30 dNIR +0.01392

**Impact:** Rules out a sensor-specific artifact. The change is in the HLS processing chain, not in Landsat or Sentinel-2 alone.

*Source:* s1/out/result_v14_vs_v20_stratified.csv · *Reproduces:* yes

## Pixel assignment

### S1-05 · Single-pixel and area-weighted assignment are indistinguishable

**Measured:** pooled r 0.8685 (single) vs 0.8684 (weighted), margin 0.00011; largest difference at any splitting level 0.0061 (band '<50%')

**Impact:** The archive's existing single-pixel convention can be kept, on evidence rather than convenience. No reprocessing needed to change it.

*Source:* s1/validate.py against interpolated HF069 PAI, 34 active tower plots · *Reproduces:* yes

### S1-06 · Pixel choice contributes about 2 % of the seasonal signal

**Measured:** between-pixel NDVI sd within one plot footprint 0.0083 (1.14 % of value) against a seasonal amplitude of 0.4077 -> 2.0 % of signal, over 11,893 plot-acquisitions

**Impact:** Explains S1-05. The canopy is spatially homogeneous at 30 m relative to the plot-pixel offset, so the assignment rule cannot matter much.

*Source:* s1/results.py · *Reproduces:* yes

## Product characterisation

### S1-07 · The HLS angle bands agree with independent solar geometry

**Measured:** median residual vs pvlib +0.308 deg overall; L30 +0.143, S30 +0.568; 2.8 % of 1,155 acquisitions exceed 1 deg

**Impact:** S4 depends on these bands. The L30/S30 gap matches their documented provenance difference (red band vs 5 km interpolated red-edge).

*Source:* s1/validate.py vs wp0/out/solar_30min.csv · *Reproduces:* yes

### S1-08 · v2.0 retains far more dates than v1.4

**Measured:** v1.4 261 dates, v2.0 1075, shared 215; 860 v2.0-only, 46 v1.4-only

**Impact:** Date sets are not nested. Every comparison must declare a join mode; the headline uses the intersection.

*Source:* s1/out/result_date_sets.csv · *Reproduces:* yes

### S1-09 · Observation density is not stationary

**Measured:** 37 acquisitions in 2015 rising to 140 in 2025 (3.8x); Landsat 9 from 2022, Sentinel-2 systematic over this tile only from ~2018

**Impact:** Confounds any trend or gap statistic. Breaks S5's stated '~52 weekly dimensions per year' premise.

*Source:* s1/out/observation_density.csv · *Reproduces:* yes

### S1-10 · Half the Sentinel-2 record rests on superseded input data

**Measured:** 224 of 484 S30 granules built on pre-Collection-1 L1C; ESA reprocessed L1C through 2023-12-13 and HLS was never rebuilt from it

**Impact:** The v2.0 side of any comparison is itself heterogeneous. HF365's whole 2015-2020 window sits in the pre-Collection-1 era.

*Source:* CMR PROCESSING_BASELINE; HLS S30 known issues #12 · *Reproduces:* yes

## Masking and quality

### S1-11 · The Fmask decoder was validated against an independent implementation

**Measured:** 100.0000 % agreement with AppEEARS' own decoding on all 108,949 real observations, across cloud, shadow, adjacent, snow, water and aerosol bits

**Impact:** Masking provenance is the core of the v2 product. This is external confirmation that Table 9 is implemented correctly.

*Source:* s1/appeears.py:validate_qa · *Reproduces:* yes

### S1-12 · Cirrus cannot be masked from the QA layer in HLS v2.0

**Measured:** Table 9 bit 0 is 'Reserved, but not used in HLS V2.0'; confirmed set to zero on every real observation. AppEEARS names the column 'Fmask_Cirrus_/_Reserved,_but_not_used'

**Impact:** A documented hole in the masking. S1 ships a cirrus proxy from the cirrus band (L30 B09, S30 B10) labelled as S1-derived, not provider QA.

*Source:* HLS v2.0 User Guide Table 9; s1/qa.py · *Reproduces:* yes

### S1-13 · High-aerosol retrievals produce physically impossible reflectance

**Measured:** 1,605 observations carry negative red reflectance; 1,586 of them (98.8 %) are flagged high aerosol. Among cloud-free pixels only 22.4 % are high aerosol, so the flag is not merely tracking cloud

**Impact:** The provider states such data should be discarded. Applying the rule costs 55.5 points of usable data (86.9 % -> 31.4 %).

*Source:* HLS S30 known issues #1; s1/pipeline.py · *Reproduces:* yes

## Data-source defects

### S1-14 · AppEEARS applies scale factors but does not convert fill values

**Measured:** reflectance fill arrives as literal -9999 on 236 observations and angle fill as literal 40000 on 190; AppEEARS also decodes the QA fill value 255 as every flag set at once rather than as no-data

**Impact:** Unhandled, a -9999 reflectance enters an NDVI and a 40000 degree view zenith enters any angular analysis.

*Source:* s1/appeears.py · *Reproduces:* yes

### S1-15 · Two CMR metadata fields are unreliable for this tile

**Measured:** the granule-name timestamp differs from the acquisition time on 468 of 1161 granules (it is orbit start, not overpass); HORIZONTAL_CS_NAME fails to report zone 18 on 345 granules, one 2020 L30 granule reporting 'UTM ZONE 19'

**Impact:** Parsing the filename time misdates observations. Trusting the CRS field places every pixel about 490 km away.

*Source:* s1/search.py; zone 18 confirmed geometrically against CMR's own polygon · *Reproduces:* yes
