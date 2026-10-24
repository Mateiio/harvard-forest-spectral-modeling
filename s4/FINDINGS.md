# S4 findings · matched-SZA decomposition

*Regenerated 2026-08-30 by `python -m s4 findings`.*

**7 of 7 findings reproduce.**

**S4 is incomplete.** The data layer (608,415 half-hourly transmittance observations, 6 plots, 2008-2023) and the decomposition machinery are built. The study as specified cannot be completed with these instruments -- see S4-07. No model was fitted; every number below is arithmetic on matched observations.

## Gates

### S4-01 · The kill-test paper does not foreclose S4

**Measured:** Remote Sensing 12(13):2083 is a within-day upscaling method (instantaneous to daily via cos SZA at local noon). Its in-situ validation is a maize canopy, not 'seven forest sites' -- the word 'site' appears once in the paper. Section 2.5 is a 6S look-up table for retrieving diffuse ratio. 'Diurnal' appears 15 times, 'seasonal' once, inside a reference title. No matched-SZA-across-days analysis anywhere

**Impact:** S4's decomposition survives. What it cannot claim is that the diurnal fAPAR-SZA relationship is uncharacterised -- it is modelled and validated.

*Source:* full text of RS 12:2083 read 2026-08-08 · *Reproduces:* yes

### S4-02 · The two PAR files use different timestamp conventions

**Measured:** hf004 stamps mark the START of the hour (WP0: vertex lag -0.506 h, 95 % CI [-0.515, -0.490]). hf206-05 is centre-labelled, by two independent tests: parabola-vertex lag -0.082 h (95 % CI [-0.123, -0.030]) where interval-start predicts -0.25, and minimising morning/afternoon tau asymmetry at matched SZA selects centre (0.0107) over interval-start (0.0159)

**Impact:** Their effective sampling centres differ by about 0.5 h. Computing transmittance stamp-to-stamp misaligns numerator and denominator, worst where irradiance changes fastest -- the regime S4 studies.

*Source:* s4/data.py; parabola-vertex method from wp0/solar.py · *Reproduces:* yes

## Data defects

### S4-03 · hf206-05 duplicates essentially all of 2024

**Measured:** 20,350 rows share a duplicated timestamp (6.7 % of the file), of which 20,348 fall in 2024 and 2 in 2010. The 2024 rows are byte-identical duplicates; the 2010 pair carries conflicting values. One NaT datetime

**Impact:** A naive load double-counts a year. Also: the file is not sorted by time, so slicing a datetime index fails before deduplication.

*Source:* s4/findings.py, recomputed from the raw file · *Reproduces:* yes

## Measurements

### S4-04 · Measured transmittance is far less sun-angle sensitive than Beer-Lambert

**Measured:** pooled clear-sky, LAI > 3.5 (median 4.44), diffuse < 0.30: observed tau falls by a factor 0.46 from SZA 25 to 65 deg, where Beer-Lambert with a spherical leaf angle distribution predicts 0.061 -- about 8x weaker

**Impact:** The textbook extinction law does not describe these measurements.

*Source:* s4/response.py; s4/out/transmittance.csv · *Reproduces:* yes

### S4-05 · The implied extinction coefficient does not recover as diffuse light falls

**Measured:** implied G = 0.074 against 0.5 for a spherical leaf angle distribution, from 2,409 plot-days. Across diffuse-fraction bins it stays flat: (0.0, 0.15] -> 0.136, (0.15, 0.25] -> 0.072, (0.25, 0.35] -> 0.072, (0.35, 0.5] -> 0.074, (0.5, 1.0] -> 0.095

**Impact:** Rules out diffuse contamination as the explanation. The discrepancy is not a black-sky/white-sky mixing artifact.

*Source:* s4/response.py:daily_extinction, within-day fits of ln(tau) on sec(SZA) · *Reproduces:* yes

### S4-06 · The understory signal is sunfleck-dominated at every sun angle

**Measured:** mean/median ratio of tau runs 1.45 to 1.98 across all sun-angle bins (1.0 would be symmetric). Median tau under a closed canopy is 0.0130, with individual half-hours spiking above 0.05

**Impact:** The distribution is spike-driven, not a smooth transmittance curve.

*Source:* s4/out/transmittance.csv · *Reproduces:* yes

## Verdict

### S4-07 · Six point sensors cannot estimate plot-mean canopy transmittance

**Measured:** the hf206-05 sensors are single points at 1 m under a closed canopy. They sit in near-permanent deep shade punctuated by sunflecks, so they measure sunfleck statistics rather than the spatial mean transmittance that Beer-Lambert describes

**Impact:** S4 as the program specifies it -- measure the extinction coefficient's sun-angle dependence -- cannot be completed with these instruments. It is an instrument limitation, not an analysis choice. Two routes remain: characterise the shade and sunfleck regimes separately (the deciduous counterpart to the km67 Tapajos two-regime work), or run the same matched-illumination design on HLS indices, which are already a 900 m2 spatial average.

*Source:* S4-04, S4-05 and S4-06 together · *Reproduces:* yes
