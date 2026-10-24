# 07 — Recreating HF365 from Raw HLS Satellite Data

Covers: `HF365_HLS_Recreation_and_Validation.ipynb`

## Purpose
1. Recreate HF365's three indices (EVI2, NDVI, NIRv) from scratch,
   directly from raw satellite reflectance, to validate that the
   published values match what the public formulas predict.
2. Enable pulling genuinely comparable HF365-style data at **new
   locations**, for a stronger version of the control-point comparison
   in `03-control-points`.

## Correcting one assumption
The satellites themselves capture far more than 2 wavelengths of light
— Landsat 8/9 has 7 reflective bands, Sentinel-2 has 11 (including
red-edge). What's true is narrower: **the 3 specific indices HF365 uses
only need 2 of those bands — Red and Near-Infrared.**

## Confirmed public formulas
- `NDVI  = (NIR - Red) / (NIR + Red)`
- `EVI2  = 2.5 * (NIR - Red) / (NIR + 2.4*Red + 1)`
- `NIRv  = NDVI * NIR`

## Confirmed data access path
HF365 is built on **HLS** (Harmonized Landsat Sentinel-2) — the same
combined Landsat 8/9 + Sentinel-2A/B/C product already discussed
elsewhere in this project. Raw Red/NIR reflectance is available through
**AppEEARS**, the exact same tool already used for MODIS throughout
this project:

| Product | Satellite | Red band | NIR band |
|---|---|---|---|
| `HLSL30` | Landsat 8/9 | `B04` | `B05` |
| `HLSS30` | Sentinel-2 | `B04` | `B8A` |

Layer names are exactly as written, verified 2026-08-07 against the AppEEARS
product endpoints for `HLSL30.020` and `HLSS30.020`. Landsat is `B04`/`B05`,
**not** `B4`/`B5` — a request using the short forms fails. Sentinel-2 NIR must
be `B8A` (narrow, 0.85–0.88 µm, the band HLS bandpass-adjusts to Landsat
`B05`); `B08` is the broad NIR band (0.78–0.88 µm) and is the wrong one.

## What's built and tested
- A notebook that takes a raw HLS Red/NIR point-sample export, computes
  all 3 indices from the formulas above, and merges against HF365's own
  published values by date — producing a direct scatter comparison
  (recreated vs. published) with correlation and mean-difference per
  index.
- Tested end-to-end on synthetic data matching the real AppEEARS HLS
  export structure — zero errors, comparison plots render correctly.
- A ready-to-submit AppEEARS request file (`hls_expansion_points.csv`)
  covering the same 4 control-point coordinates already validated in
  `03-control-points`, plus the original Harvard Forest tower coordinate
  as a self-check.

## Why the expansion points matter
Since HLS is one continuously-operating global product (not a
region-specific one), any location gets a broadly similar revisit
cadence — HLS's own documentation states observations less than 1.4
days apart on average, globally. Requesting real HLS indices at the
same 4 control points already used for MODIS comparison would give a
genuinely apples-to-apples check: **HLS-derived indices vs.
HLS-derived indices** at increasing ecological distance, rather than
comparing HLS (HF365) against a different product (MODIS) as the
current control-point work does.

## Caveats
- **This notebook has not yet been run on real HLS data.** It's fully
  tested against synthetic data matching the real export structure, but
  the actual recreation-vs-published comparison and the expansion-point
  results both require submitting the AppEEARS requests described above
  and downloading the results.
- Exact calendar dates from new locations won't match Harvard Forest's
  HF365 dates unless the site falls in the same or an adjacent HLS
  tile — "roughly the same timing" means comparable sampling density
  and seasonal coverage, not identical dates.
