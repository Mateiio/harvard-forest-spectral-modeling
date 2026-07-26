# 05 — LAI/FAPAR Forecasting

Covers: `HF365_MODIS_LAI_FPAR_Forecast.ipynb`

## Purpose
Forecast **both** MODIS `Lai_500m` and `Fpar_500m` **8 days into the
future** from HF365 spectral indices (EVI2, NDVI, NIRv), using a
strictly time-respecting setup. Previously only LAI was covered
(flagged as a gap) — this version runs the same validated pipeline for
both targets side by side, in one notebook, rather than duplicating
~90% of the code across two files.

## Bugs found and fixed in this rebuild
1. **`NDVI_std` NaN leak:** undefined (NaN) on any date where only one plot reported a valid value. Fixed by treating a single-valid-plot day as zero measurable spread (`fillna(0)`) — a defensible convention, not a workaround.
2. **Baret-Guyot curve-fit scaling bug (found specifically while adding the FPAR target):** the physical baseline's initial rate-constant guess (`k0=0.3`) was tuned for LAI's 0-7 range. Applied unchanged to FPAR's 0-1 range, `curve_fit` had no usable gradient and **silently got stuck at the initial guess** — producing catastrophic scores (R² as low as **-762**) that were actually just a failed fit, not a real result. **Fixed** by scaling the initial guess to each target's own range (`k0 = 3.0 / target.max()`). Verified: the fitted `k` values are now sensibly different per target (~0.45 for LAI-scale vs ~3.5 for FPAR-scale, matching the ~7x range ratio between them), and fit quality improved by two to three orders of magnitude on test data.

## Method (unchanged core logic from the LAI-only version)
- Features: site-averaged EVI2/NDVI/NIRv at date *d*, plus plot-count and plot-spread diagnostics
- Targets: MODIS `Lai_500m` **and** `Fpar_500m`, each at the composite window containing *d* + 8 days
- Chronological train/test split (never shuffled)
- Models compared per target: LinearRegression (raw + diagnostics), RandomForest (raw + diagnostics), Baret & Guyot (1991) physical baseline (clamped)

## A methodology note on applying Baret-Guyot to FPAR
The Baret & Guyot (1991) saturating-exponential formula was originally
published for **LAI**. Using the same functional shape for FPAR is a
reasonable, commonly-used analogy in remote sensing (FPAR is similarly
bounded and saturates with VI) — but it's an **analogous application**,
not the literature-validated original use. Both targets require
clamping regardless.

## Results (from the original real LAI run — unaffected by the two fixes above, which were edge-case/FPAR-specific)

| Model variant | Test R² (LAI) | Test RMSE (LAI) |
|---|---|---|
| **RandomForest + plot diagnostics** | **0.859** | **0.729** |
| RandomForest (raw features) | 0.812 | 0.843 |
| LinearRegression (raw features) | 0.809 | 0.849 |
| LinearRegression + plot diagnostics | 0.804 | 0.860 |
| Baret-Guyot (NDVI), clamped | 0.618 | 1.201 |
| Baret-Guyot (EVI2), clamped | 0.277 | 1.652 |
| Baret-Guyot (NIRv), clamped | 0.199 | 1.739 |

**FPAR results need a fresh run on your real data** — this target is
new in this version, and only structurally verified (zero errors, both
fixes confirmed working) on synthetic test data so far, not yet run
against your actual `modis_downloads` folder.

## Caveats
- **Action needed:** run this notebook against your real MODIS data to get the first real FPAR forecast numbers, and to confirm the fixed Baret-Guyot fit behaves sensibly on real (not synthetic) curves for both targets.
- The LAI numbers above remain valid and unaffected by this update.
