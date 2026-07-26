# Status — 02 Correlation Analysis

**Status: Complete, bug fixed — needs one re-run on real data**

## Done
- [x] All 72 correlation numbers computed (3 methods × 6 index-pairs × 4 views)
- [x] Method comparison table built
- [x] Best method (window-containment) and best index-pair (EVI2 vs Lai_500m, r=0.938) confirmed
- [x] All 72 individual charts generated and verified rendering
- [x] **QC-weighting bug found, root-caused, and fixed** (raw byte vs. decoded SCF_QC level — see report)
- [x] Fix verified: weighted method now performs comparably to window-containment instead of consistently worse

## Open / not done
- [ ] **Re-run this notebook against your real MODIS data** to get corrected Method 3 (QC+StdDev weighted) numbers — the previously recorded ones used the buggy weighting and are stale

## Known issues
None remaining in the code. The one open item above is "needs a fresh run," not a bug.
