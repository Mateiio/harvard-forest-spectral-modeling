# 04 — Anomaly Detection

Covers: `HF365_MODIS_Anomaly_Detection.ipynb`

## Purpose
Identify which of the 42 HF365 plots and 5 MODIS pixels behave
structurally differently from their peers, using two independent
methods cross-checked against each other.

## Bug found and fixed in this rebuild
The peer-correlation cross-check (Section 7) crashed with
`ValueError: underlying array is read-only` on `np.fill_diagonal(corr.values, ...)`
— a `pandas.DataFrame.corr()` result's underlying array isn't always
writable in-place. **Fixed** by switching to a non-mutating
`.mask(eye)` approach instead of `fill_diagonal`. Verified: the
notebook now runs end-to-end with zero errors.

## Method (streamlined from the original — same core logic, less redundant code)
- **Method A — raw time-series centroid distance:** each plot/pixel's full time series compared directly to the group centroid
- **Method B — behavioral-summary centroid distance:** each plot/pixel reduced to summary features (mean, spread, seasonal amplitude) first, then compared to the centroid in that feature space
- A plot/pixel is only reported as a confirmed outlier if **both methods agree**
- Section 7 (peer correlation) is a third, independent cross-check

## Key result from the original real run: Plot H3 is the standout anomaly
**H3 was flagged by both methods across all three HF365 indices**
(EVI2, NDVI, and NIRv) — the only plot with this level of consistency.
Other plots flagged (both methods agreeing), by index:
- **EVI2:** F1, G1, H3
- **NDVI:** E5, G2, H2, H3
- **NIRv:** F1, G1, G3, H3

(Note: "F1" and "D1" appear in the raw HF365 CSV with a trailing space
in their column names — a pre-existing data quirk, stripped during
loading in this rebuild.)

## Limitation from the original run, now improved (but re-verify on real data)
Previously, the percentile-based threshold flagged **all 5 MODIS
pixels** as outliers for both Lai_500m and Fpar_500m — not a meaningful
result at n=5. In this rebuild's testing (on synthetic data with one
pixel deliberately made structurally different), the same threshold
approach correctly flagged **only that one pixel**, not all 5 — a
promising sign this may already be resolved, though this should be
confirmed against your real MODIS data rather than assumed, since the
underlying cause (small-sample percentile behavior) can be sensitive to
the actual value distribution.

## Caveats
- Since the code was both fixed and streamlined, re-run against real data to confirm the exact flagged-plot lists still match the original run — the core pattern (H3 as the standout) is expected to hold, but exact top-5 boundary cases could shift slightly.

## Addendum: Mahalanobis vs. Euclidean distance-to-centroid

A new Section 8 adds **Mahalanobis distance** alongside the existing
Euclidean-based behavioral distance (Section 3), for both plot-to-plot
and pixel-to-pixel centroid comparisons. Mahalanobis accounts for how
the behavioral features (mean, spread, seasonal amplitude) actually
covary with each other — Euclidean distance implicitly assumes they're
independent, which double-counts shared signal when they're not.

**Verified on test data:** both measures compute without error (even at
MODIS's small n=5), and the two measures show meaningful but imperfect
agreement (Euclidean-Mahalanobis correlation ranged ~0.37-0.82 across
the 5 datasets in testing) — confirming the two lenses genuinely add
different information rather than being redundant. Where they disagree
most (off-diagonal points in the new scatter plots) is flagged as
specifically worth a closer look.

**Known limitation, same as before:** Mahalanobis distance can become
mathematically undefined (singular covariance) when the number of
observations is close to the number of features — a real risk at
MODIS's n=5. Verified this doesn't occur with the current 5-feature
setup, but worth checking again if more behavioral features are added
later.
