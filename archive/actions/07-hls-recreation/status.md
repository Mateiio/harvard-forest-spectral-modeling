# Status — 07 HLS Recreation

**Status: New. Code built and tested on synthetic data. Needs a real AppEEARS request to produce real results.**

## Done
- [x] Confirmed the public formulas for EVI2, NDVI, NIRv
- [x] Confirmed raw HLS Red/NIR data is accessible via AppEEARS (same tool/workflow as MODIS elsewhere in this project)
- [x] Built and tested the recreation/validation notebook end-to-end (synthetic data matching real export structure — zero errors)
- [x] Built the AppEEARS request file for the 4 control-point coordinates + original tower (self-check)

## Open / not done
- [ ] **Submit the AppEEARS request** (`hls_expansion_points.csv`, products `HLSL30.020`+`HLSS30.020`, layers `B04`/`B05` (L30) + `B04`/`B8A` (S30), plus `Fmask` and `SZA`/`SAA`/`VZA`/`VAA`) and download the results
  - Layer names corrected 2026-08-07: Landsat is `B04`/`B05`, not `B4`/`B5`. Verified against the AppEEARS product endpoints.
  - Note: for the Harvard Forest plot network itself, S1 supersedes this route — `Freedle/s1/` pulls native COGs via CMR/earthaccess, which preserves the UTM grid and enables the area-weighted assignment. This AppEEARS request remains the right tool for the four **control points**.
- [ ] **Run the notebook on your real HLS export** to get the first real recreated-vs-published comparison (validates HF365's own values)
- [ ] **Run the same notebook on the 4 control-point HLS results** once downloaded, to get a genuine HLS-vs-HLS distance-decay comparison (stronger than the current HLS-vs-MODIS comparison in `03-control-points`)

## Known issues
None in the code. All open items are "needs a real data request," not bugs.
