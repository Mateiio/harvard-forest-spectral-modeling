# Status — 05 LAI/FAPAR Forecasting

**Status: Both targets now implemented. FPAR needs a first real-data run.**

## Done
- [x] 8-day-ahead forecast pipeline for **both** Lai_500m and Fpar_500m, one shared notebook
- [x] Baseline models (LinearRegression, RandomForest) fit and compared, both targets
- [x] Plot-averaging diagnostic features tested for both targets
- [x] Baret & Guyot (1991) physical baseline fit per-index, per-target, with clamping
- [x] **`NaN`-leak bug (single-plot-day `NDVI_std`) fixed**
- [x] **Baret-Guyot curve-fit scaling bug found and fixed** — this was the concrete reason FPAR forecasting hadn't worked when first attempted; the same fixed-k0 approach that worked for LAI silently failed on FPAR's different scale until this fix
- [x] Feature importance computed for both targets
- [x] **Previously open gap resolved:** FPAR forecasting no longer missing

## Open / not done
- [ ] **Run against real MODIS data** to get the first authoritative FPAR forecast numbers (currently only verified on synthetic test data)
- [ ] Confirm the fixed Baret-Guyot fit produces sensible (positive, reasonable) R² for FPAR on real data, the way it already does for LAI
- [ ] Optional: extend the forecast horizon test beyond 8 days for either target

## Known issues
None remaining in the code. Both open items above are "needs a real-data run," not bugs.
