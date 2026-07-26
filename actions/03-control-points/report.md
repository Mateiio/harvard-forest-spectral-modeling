# 03 — Control Points & Pixel Geolocation

Covers: `HF365_ControlPoints_and_Geolocation.ipynb`

## Purpose
Test whether the main HF365↔MODIS correlation (see `02`) reflects a real
local relationship or a coincidence — by checking correlation at
locations of increasing distance/dissimilarity from Harvard Forest.
Also documents the real-world location of the 5 main MODIS pixels
(moved here from `01-data-understanding`, since it's spatial content).

## Bug found and fixed in this rebuild
The chart-plotting section previously crashed with
`KeyError: ('MA_Far', 'EVI2', 'Lai_500m')` and never produced a single
chart. **Root cause:** the actual `ID` values returned by AppEEARS came
back **without underscores** (`MAFar`, `JapanOppositeTZ`, ...) but the
plotting loop still referenced a separate, hardcoded list of names
**with** underscores (`MA_Far`, `Japan_Opposite_TZ`, ...) from the
original request-building step — the two lists silently drifted out of
sync.

**Fix:** the location list is now read directly from the data
(`raw[id_col].unique()`) rather than maintained as a separate hardcoded
list, so this class of bug can't recur. Verified: all 24 four-panel
charts plus the final summary chart (25 figures total) now render with
zero errors, where none did before.

## Real-world location of the 5 main MODIS pixels

| Pixel | Latitude | Longitude |
|---|---|---|
| pixel_1 | 42.539583 | -72.177657 |
| pixel_2 | 42.539583 | -72.172002 |
| pixel_3 | 42.535417 | -72.178496 |
| pixel_4 | 42.535417 | -72.172841 |
| pixel_5 | 42.535417 | -72.167186 |

## Control point correlation results (unaffected by the bug fix — these numbers were always correct; only the charts were broken)

| Control point | Description | EVI2/Lai | EVI2/Fpar | NDVI/Lai | NDVI/Fpar | NIRv/Lai | NIRv/Fpar |
|---|---|---|---|---|---|---|---|
| **MAFar** | Mount Greylock, western MA (~130km away, same state) | 0.895 | 0.889 | 0.872 | 0.901 | 0.895 | 0.883 |
| **JapanOppositeTZ** | Takayama, Japan (~13-14hr TZ offset) | 0.678 | 0.624 | 0.691 | 0.656 | 0.666 | 0.609 |
| **DifferentState** | Wind River Experimental Forest, WA (different biome) | 0.587 | 0.454 | 0.581 | 0.466 | 0.582 | 0.446 |
| **AmazonEquatorial** | Tapajós National Forest, Brazil (near-equatorial) | 0.346 | 0.317 | 0.356 | 0.322 | 0.344 | 0.314 |

## Headline finding: a clean, graded distance-decay pattern
**MAFar (~0.87-0.90) > JapanOppositeTZ (~0.61-0.69) > DifferentState (~0.45-0.59) > AmazonEquatorial (~0.31-0.36)**.
Correlation fades smoothly with ecological/climatic distance — exactly
what real shared local phenology should look like, and strong evidence
the main-site correlation (see `02`) is not a pipeline artifact.

## Caveats
None outstanding — both the numeric results and the visualizations are now confirmed working.

## Addendum: plot distance vs. correlation (within the existing 42-plot network)

`HF365_Plot_Distance_vs_Correlation.ipynb` extends the distance-decay
idea above to work *within* the existing HF365 plot network itself,
rather than only against far-away external control points: does a
plot's correlation with the site average weaken the further it sits
from the tower?

**This currently runs on placeholder/reconstructed coordinates, not
real survey data** — early attempts to get precise plot coordinates
(digitizing the HF069 site map, then a WebPlotDigitizer pass) were
never completed. The placeholder set is built only from HF069's
documented transect structure (8 directions × 100m steps to 500m), with
transect bearings assumed evenly spread across the NW-SW arc — not
verified against the real site map. **Every number this notebook
currently produces should be treated as a demonstration of the method,
not a real finding.** See `status.md` for what's needed to fix this.
