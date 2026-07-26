# Status — 01 Data Understanding

**Status: Complete**

## Done
- [x] HF365 structural facts — tested against real data (263 union dates, 37-38% blank, median 6-day gap)
- [x] MODIS structural facts — shape, missingness, timing, value ranges, QC breakdown (goodness score 0.880)
- [x] MODIS composite-calendar detail documented (true per-year 8-day grid, not a naive fixed interval)
- [x] HF365 ↔ MODIS temporal overlap facts (83/253 windows, 32.8%, have zero HF365 coverage)
- [x] **Previously open item resolved:** `HF365_Dataset_Facts.ipynb` now exists and is tested
- [x] Pixel real-world-location content relocated to `03-control-points` (not a gap — intentional move)

## Open / not done
None.

## Known issues
None. All three notebooks in this folder run cleanly end-to-end.
