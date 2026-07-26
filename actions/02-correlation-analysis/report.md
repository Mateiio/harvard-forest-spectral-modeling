# 02 — Correlation Analysis

Covers: `HF365_MODIS_Full_Correlation_Analysis.ipynb`

## Purpose
Correlate HF365 plot-level indices (EVI2, NDVI, NIRv) against MODIS pixel
variables (Lai_500m, Fpar_500m), comparing three different alignment
methods and four "views" for each — 72 correlation numbers total.

## Bug found and fixed in this rebuild
The previous version's QC-weighted method (Method 3) applied its weight
map **directly to the raw packed `FparLai_QC` byte**. That byte packs
five unrelated sub-fields into one number (MODLAND flag, sensor,
dead-detector flag, cloud state, and the actual SCF_QC quality level) —
so a weight map like `{0: 1.0, 2: 0.75}` was accidentally keying off
*combinations of unrelated bits*, not real quality. This silently
mis-weighted roughly a third of the data (all "Good, with saturation"
observations landed in the near-zero default-weight bucket purely
because of which sensor/cloud bits they happened to have) — which is
exactly why Method 3 previously scored *worse* than plain
window-containment in every single index-pair.

**Fix:** decode the real SCF_QC level first via `(byte >> 5) & 0b111`
(bits 5-7), *then* map that decoded level to a weight
(`{0:1.0, 1:0.85, 2:0.50, 3:0.20, 4:0.05}`). Verified on test data: the
weighted method now performs **on par with** window-containment
(differences of ~±0.01) instead of being consistently, substantially
worse — confirming the fix behaves as a correctly-weighted method
should.

**Action needed:** re-run this notebook against your real MODIS data —
the previously-recorded Method 3 numbers (e.g. NDVI vs Lai_500m: 0.824)
were computed with the buggy weighting and should be considered stale.
Methods 1 and 2's numbers are unaffected by this fix and remain valid.

## Results that remain valid (Methods 1 & 2, unaffected by the fix)

| Index-pair | Nearest (incl. zero) | Window (excl. zero) |
|---|---|---|
| EVI2 vs Lai_500m | 0.912 | **0.938** |
| EVI2 vs Fpar_500m | 0.869 | **0.904** |
| NDVI vs Lai_500m | 0.892 | **0.927** |
| NDVI vs Fpar_500m | 0.881 | **0.926** |
| NIRv vs Lai_500m | 0.905 | **0.934** |
| NIRv vs Fpar_500m | 0.856 | **0.896** |

**Window-containment matching remains the best method, consistently,
across every index-pair.** Best single result: EVI2 vs Lai_500m under
window-containment, r = 0.938.

## Caveats
- Method 3's numbers need a fresh real-data run with the fixed code before being reported anywhere as final.
- All numbers here use the 5 real MODIS pixels only — see `03-control-points` for validation against locations further away.
