# 01 — Data Understanding

Covers: `HF365_Dataset_Facts.ipynb`, `MODIS_Dataset_Facts.ipynb`,
`HF365_MODIS_Overlap_TrueWindows.ipynb`

## Purpose
Establish the basic structural facts of both datasets — shape, missingness,
timing, and value ranges — before any correlation or modeling is attempted.

## What changed in this rebuild
- **Gap closed:** `HF365_Dataset_Facts.ipynb` now exists (previously flagged as missing) and has been tested end-to-end against the real HF365 CSVs.
- All three notebooks rebuilt for clarity/conciseness; no methodology changes to the overlap or MODIS facts logic.
- The pixel real-world-location section previously bolted onto the end of the overlap notebook has been **moved to `03-control-points`**, since it's spatial, not temporal, content.

## HF365 side — key facts (tested against real data)
- **EVI2: 261 dates, NDVI/NIRv: 262 dates** — each x 42 plots
- Union of dates across all 3 indices: **263**, range **2015-01-23 to 2020-08-10**
- Rows only exist for actual overpass dates: **13.0% of calendar days** in range have a row at all (sparse by construction, not padded)
- **37.3–38.2% of individual plot cells are blank** (per-plot cloud/snow masking); **0 rows have every plot blank**
- Median gap between dates: **6 days** (mean 7.8d); **17 gaps exceed 16 days**, max gap **57 days**
- Least complete plots: **H2 (~55%)**; most complete: **H4 (~68%)**
- **260 dates common to all 3 indices** — each index has 1-2 dates the others don't
- All values fall inside physically plausible ranges (no fill-value artifacts)

## MODIS side — key facts
- 2 layers (`Lai_500m`, `Fpar_500m`) × 5 pixels × 276 distinct composite dates = 1,380 rows per layer
- Date range: **2014-12-27 to 2020-12-26**
- **0% blank/fill values** — every retrieval is real and usable
- Gap distribution: 5-day (5), 6-day (1), **8-day (268)**, 16-day (1)
- **A methodology detail worth remembering:** MODIS's true composite calendar resets per-year — a naive uniform-8-day-from-start assumption gives a slightly wrong expected-date count. Always use the true per-year 8-day grid.
- **QC (FparLai_QC) breakdown:** Level 0/Best 62.2%, Level 1/Good 32.8%, Level 3/Poor 5.0%. **Overall goodness score: 0.880.**
- The QC byte is decoded via `(byte >> 5) & 0b111` to extract the real SCF_QC level — this exact decode function is reused (and its correct use is now enforced) in `02-correlation-analysis`, after a bug was found and fixed there (see that folder's report).

## HF365 ↔ MODIS temporal overlap — key facts
- Overall overlapping window: **2015-01-23 to 2020-08-10** (2,026 days / 5.55 years), bounded by HF365 on both ends
- **253 MODIS windows** evaluated within that overlap; window lengths: 5-day (4), 6-day (1), **8-day (247)**, 16-day (1)
- HF365 observations per MODIS window: 0→**83**, 1→104, 2→47, 3→13, 4→6
- **83 of 253 MODIS windows (32.8%) have zero HF365 observations inside them.** For those, the nearest HF365 point averages 8.3 days away (median 5, max 42 days).

## Caveats
None outstanding for this folder — the previously flagged gap (no HF365 facts notebook) is now closed.
