# Status — 04 Anomaly Detection

**Status: Complete, bug fixed — recommend one confirmation re-run**

## Done
- [x] Two independent anomaly-detection methods run and cross-checked
- [x] Applied to all 3 HF365 indices and both MODIS variables
- [x] Plot H3 identified (original run) as the single most consistent cross-index anomaly
- [x] Peer correlation cross-check included
- [x] **`ValueError` (read-only array) bug found and fixed** — see report
- [x] Notebook now runs end-to-end with zero errors, streamlined from the original

## Open / not done
- [ ] Re-run against real data to confirm exact flagged-plot lists still match the original findings (expected to, given the core method is unchanged — just confirming after the fix + streamlining)
- [ ] Optional: investigate plot H3 specifically (field notes, plot photos, location)
- [x] **New:** Mahalanobis distance added alongside Euclidean for plot-to-plot and pixel-to-pixel centroid comparisons -- tested, no singular-covariance issues at current feature count

## Known issues
None remaining in the code.
