# Status — 03 Control Points

**Status: Core work complete. One new analysis added, blocked on real coordinates.**

## Done
- [x] 5 main pixels' real-world coordinates confirmed and documented
- [x] 4 control points' correlation numbers computed (24/24 combinations)
- [x] Clean distance-decay pattern confirmed: MAFar > JapanOppositeTZ > DifferentState > AmazonEquatorial
- [x] `KeyError` naming-mismatch bug found, root-caused, and fixed — all 25 charts render
- [x] **New:** `HF365_Plot_Distance_vs_Correlation.ipynb` built and tested — the code/method for testing distance-decay *within* the existing 42-plot network (not just against external control points)

## Open / not done — TODO
- [ ] **Get real, precise plot coordinates.** `HF365_Plot_Distance_vs_Correlation.ipynb` currently runs on a placeholder reconstruction (HF069's documented transect structure, with bearings assumed evenly spread — not the real site survey). Two known paths to finish this, both discussed earlier in this project but never completed:
  - Digitize `hf069-20-plot-map.jpg` precisely with WebPlotDigitizer (calibrated on its scale bar)
  - Or georeference the same map in QGIS against real ground-control points (Pierce Road, Locust Opening Road, the beaver pond)
- [ ] **Once real coordinates exist:** re-run `HF365_Plot_Distance_vs_Correlation.ipynb` (just point `PLOT_COORDS_CSV` at the real file) — no other code changes needed
- [ ] **Extending further outward:** the current 42-plot network only spans ~500m from the tower (HF069's own transect design limit). Meaningfully extending the distance-decay curve further out would need new plots beyond that radius — this means either new field data collection or accepting the current network's 500m ceiling as the analysis limit

## Known issues
None in the code. The placeholder-coordinate limitation above is a data gap, not a bug.
