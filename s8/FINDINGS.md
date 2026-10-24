# S8 findings · ground leaf area index from the reprocessed archive

*Regenerated 2026-09-26 by `python -m s8 findings`. Values are recomputed from `s8/out/` and the raw archives on each run.*

**11 of 11 findings reproduce.**

Source: 2894 ground-satellite pairs over 37 plots and 92 field campaigns, 2015-07-13 to 2025-11-20. Target is lai (= pai - min pai per plot, WP0 lai_subtractive_fx). Chosen model: spectral + calendar + plot id, ridge alpha 1.0.

**Headline:** R2 0.898 / RMSE 0.411 for a known plot on a new date; R2 0.863 / RMSE 0.476 for a plot never measured; against a calendar-only baseline of R2 0.721.

## What is being predicted

### S8-01 · The target is derived, not observed

**Measured:** HF069 reports plant area index: its leaf-off reading averages 1.72 at plot level, and the archive's own site file puts leaf-off PAI at 1.72 against a deciduous LAI of 0.08. S8's target is pai - min(pai) per plot

**Impact:** About 1.7 of this stand's plant area is wood. Calling the raw column LAI overstates leaf area by that much in every season, and by everything in winter.

*Source:* hf069.xml; hf069-02-lai-site.csv; wp0/lai.py · *Reproduces:* yes

### S8-09 · Converting PAI to LAI does not change what the model learns

**Measured:** with plot dummies in, RMSE is 0.4111 on LAI and 0.4114 on PAI -- the same fit. R2 differs (0.898 vs 0.906) only because the targets have different variance

**Impact:** LAI = PAI minus a per-plot constant, which is exactly what a plot dummy absorbs. Convert because the write-up and FT04 need leaf area, not because the model gains anything.

*Source:* s8/model.py:run_ladder · *Reproduces:* yes

## What the satellite is worth

### S8-02 · Day-of-year alone explains most of the target

**Measured:** a calendar with no satellite input scores R2 0.721 (RMSE 0.679); the chosen model scores 0.898 (RMSE 0.411), a gain of +0.177

**Impact:** HF069 samples March to December, so most of the variance is the seasonal cycle. Any headline R2 must be reported against this baseline or it reads as skill the satellite did not supply.

*Source:* s8/model.py:run_ladder · *Reproduces:* yes

### S8-03 · S1's reprocessing is what makes the sample usable

**Measured:** 2894 pairs over 92 campaigns against 1364 within the published HF365 window 2015-01-23..2020-08-10 -- 2.12x

**Impact:** The published archive stops in 2020. S1's v2 runs to 2026, which is the only reason five more years of HF069 campaigns are reachable.

*Source:* s1/out/hf365_v2_candidate.csv; s8/data.py · *Reproduces:* yes

## Rejected inputs

### S8-04 · Solar zenith angle is day-of-year wearing a hat

**Measured:** SZA on a day-of-year harmonic returns R2 0.9927, residual sd 1.21 deg, over 22.6-67.0 deg at a maximum view zenith of 8.1 deg. Three tests: as a main effect R2 0.8977 -> 0.8971; as an index interaction -> 0.8960; and the retrieval's residuals carry no SZA structure at all (r = +0.0154)

**Impact:** Illumination geometry earns its keep where it varies within a day at a fixed canopy, which is S4's design. Here every route is collinear with the calendar, and the residuals confirm nothing is left unexplained. SZA is excluded on evidence, not on preference.

*Source:* s8/model.py:sza_is_the_calendar; s8/findings.py:f04_sza_is_the_calendar · *Reproduces:* yes

### S8-05 · MODIS adds nothing to the retrieval

**Measured:** on the 1393 pairs MODIS reaches, adding Lai_500m and Fpar_500m moves R2 from 0.9347 to 0.9351. Its cells differ by only 0.152 LAI on a typical date and 35 % of its good-quality retrievals are flagged saturated

**Impact:** A 500 m product cannot resolve 10 m plots, and its record ends 2020-12-26. Predicting one optical retrieval from another was the design of the earlier forecasting notebook; S8 does not repeat it.

*Source:* MCD15A2H.061 point sample; s8/findings.py:f05_modis_adds_nothing · *Reproduces:* yes

## Model choice

### S8-06 · Ridge beats a random forest once folds respect campaigns

**Measured:** ridge R2 0.8977 against random forest 0.8662 on the same design and the same 92 campaign groups

**Impact:** The earlier MODIS-target notebook found the forest ahead. That ordering came from splits that let it memorise date-specific patterns; grouped folds remove the advantage.

*Source:* s8/findings.py:f06_ridge_beats_the_forest · *Reproduces:* yes

## How well it works

### S8-07 · The honest score depends on which question is asked

**Measured:** known plot on a new date R2 0.8977 (RMSE 0.411, 92 campaign folds); a plot never measured R2 0.8629 (RMSE 0.476, 37 plot folds). A static per-plot offset holds 5.6 % of the target's variance

**Impact:** Quoting the higher number for the new-plot use case overstates the model. Both are written on every run so the write-up has to pick one.

*Source:* s8/model.py:run_ladder, variance_budget · *Reproduces:* yes

### S8-08 · Peak season is where the retrieval is weakest

**Measured:** at peak (DOY 160-250, n=786) the spectral model scores R2 0.257 against 0.533 with plot identity, while green-up reaches 0.879

**Impact:** The indices saturate once the canopy closes, and the ground barely varies there. What skill remains at peak is mostly the plot offset, not the spectra -- so a claim about peak leaf area rests on almost nothing.

*Source:* s8/out/season_skill.csv · *Reproduces:* yes

## Forecasting a future date

### S8-10 · The satellite's forecast value decays within about a month

**Measured:** gain over a calendar-only forecast: 8 d +0.049, 16 d +0.014, 32 d +0.010, 64 d +0.001. The calendar itself is flat across horizons (0.771-0.778) while carrying the last retrieval forward decays from 0.785 to 0.727

**Impact:** Spectral memory fades but seasonal climatology does not, so beyond roughly a month a wall calendar forecasts leaf area as well as the satellite does. Reaching further needs a climate-driven phenology model, not more spectral features.

*Source:* s8/out/forecast_results.csv · *Reproduces:* yes

## Open

### S8-11 · Ground leaf area is falling and the indices do not see it

**Measured:** over 11 peak seasons on the 28 plots measured every year, ground LAI falls -0.0564 per year (p=0.015, -0.62 across the record) while EVI2 shows -0.0030 (p=0.373) and NDVI -0.0012 (p=0.131)

**Impact:** The decade-scale change on the ground exceeds the model's RMSE, and the predictors do not carry it -- so the retrieval's residuals drift with year. This is S8-08 at decadal scale: at peak season NDVI sits near 0.89 and is saturated, so a real decline in leaf area is invisible to it. Cause is not established here; instrument drift, crew change and real canopy decline are all open.

*Source:* s8/findings.py:f11_ground_and_satellite_diverge · *Reproduces:* yes
