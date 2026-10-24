# Data catalog

Companion to `00-research-program.md`. Every dataset the program uses, what it measures, how, and where to get it.

**Link conventions.** Harvard Forest landing pages: `https://harvardforest.fas.harvard.edu/exist/apps/datasets/showData.html?id=hfNNN`. Direct files: `https://harvardforest.fas.harvard.edu/data/pNN/hfNNN/`. Verified package prefixes: **p06** = HF069, **p20** = HF206, **p36** = HF365. Data-quality preview plots carrying row counts, ranges and per-column NA counts live at `https://harvardforest1.fas.harvard.edu/data/plots/hfNNN-NN.pdf` and are the fastest way to audit a file without downloading it. All Harvard Forest data is mirrored at EDI under scope `knb-lter-hfr` and is CC0.

---

## 1. Ground and tower data

### HF365 · Spectral Vegetation Indices from HLS, 2015-2020
Three CSVs of dimensionless indices, one per index, with a `date` column and 42 plot columns: A1 to H5 plus `HARV_049` and `HARV_050`. 261 records (EVI2) and 262 (NDVI), so **one row per usable HLS acquisition date, not a daily series.** NA marks cloud, snow and similar. Computed from HLS v1.4 surface reflectance at the 30 m pixel covering each plot, MGRS tile T18TYN. Definitions: `EVI2 = 2.5(NIR−RED)/(NIR+2.4·RED+1)`, `NDVI = (NIR−RED)/(NIR+RED)`, `NIRv = NDVI × NIR`. Values stored to 0.001.
**Type:** satellite, plot-registered · **Files:** `.../p36/hf365/hf365-01-hls-evi2.csv`, `-02-hls-ndvi.csv`, `-03-hls-nirv.csv` · **EDI:** `knb-lter-hfr.365.3`
**Note:** the daily penalised-spline interpolation described in the paper is an analysis step, not part of this archive.

### HF069 · Biomass Inventories at EMS Tower since 1993 (v.43)
40 circular plots of 10 m radius. LAI measured with LI-COR LAI-2000, later LAI-2200: five readings per plot (centre plus four points 2 m out in cardinal directions), taken near sunrise or sunset for diffuse light, outer ring masked. Bi-weekly in spring and fall, monthly mid-summer; 1998, 1999, and every year since 2005. Measures **plant** area index, so the woody-fraction correction is yours to apply. `hf069-02` publishes PAI explicitly uncorrected for woody material.
**Type:** ground · **Path:** `.../p06/hf069/`

| File | Contents |
|---|---|
| `hf069-01-lai-plot.csv` | date, year, doy, plot, lai, se — **the core ground truth** |
| `hf069-02-lai-site.csv` | Site aggregates, PAI uncorrected for woody material |
| `hf069-03-litter-chem.csv` | Litter chemistry |
| `hf069-04-canopy-chem.csv` | Canopy chemistry, N and C |
| `hf069-05-litter.csv` | **Litterfall sorted by species, per plot, annually since 1998** |
| `hf069-07-soil-moist.csv`, `-18`, `-19` | Soil moisture and water content |
| `hf069-09-ems-trees.csv` | Tree-level DBH and species per plot |
| `hf069-11-understory-trees.csv`, `-15` | Understory stems |
| `hf069-12-biomass-basal.csv` | Biomass and basal area |
| `hf069-20-plot-map.jpg`, `-21-compass-dist.bmp` | Plot maps (coordinates are in HF375, not here) |
| `hf069-22-allometries.txt` | Allometric equations |

**Plot status:** 34 active tower plots. G3, H3, H4 dropped in 2001 to beaver-pond inundation; A4, A5, B5 moved to the harvest group. Harvest plots are X1 to X6.

### HF375 · Long-Term Field Research Sites since 1937
**The source of all plot coordinates.** Filter `hf375-02` on `NAME` matching `^EMS [A-HX]\d$` for 46 rows: 40 grid plots plus 6 harvest plots, each with `Latitude`, `Longitude`, `ArchiveNum = HF069`, `AreaGISm2 = 297`, `CATEGORY = tower biometery`. `hf375-01` gives `EMS Tower` at **42.537764, -72.171479**. `hf375-03` and `-04` are point and polygon shapefiles.
**Type:** ground, spatial · **Page:** `showData.html?id=hf375`

### HF206 · Microclimate at HEM, LPH and EMS Towers since 2005
**Type:** ground, tower and understory · **Path:** `.../p20/hf206/`

`hf206-05-EMS-understory.csv` is the critical file: **302,777 rows, 83 columns, 30-minute resolution, 2008-01-01 to 2025-01-09**, essentially gap-free at the row level. MD5 `94d70d32eaaee53996b25fd5dafe6715`. Understory PAR from LI-190 SA quantum sensors at 1 m, in six named biometry plots.

| Column | Plot | Logger | Missing |
|---|---|---|---|
| `par_c2_ave` | C2 | EMS1 | 1.4 % |
| `par_e3_ave` | E3 | EMS2 | 1.4 % |
| `par_b2_ave` | B2 | EMS1 | 1.6 % |
| `par_f3_ave` | F3 | EMS2 | 7.6 % |
| `par_f2_ave` | F2 | EMS2 | 11.0 % |
| `par_c3_ave` | C3 | EMS1 | 12.1 % |

Each PAR column has `_ave`, `_max` and `_min` per 30-minute interval, giving within-interval variability, which is a direct sunfleck measure. **This file contains no above-canopy PAR.** The landing page says the dataset starts 2005; the EMS file starts 2008.

`hf206-02-HK-micro-2014-present.csv` carries the richest radiation suite in the archive: PAR at 30, 20 and 10 m, plus `albedo`, `rs_down`, `rs_up`, `rl_down`, `rl_up` from an NR01 four-component net radiometer. Hemlock tower, not EMS, but the best candidate for deriving diffuse fraction.

**Known data quality issues:** unconverted ±7999 datalogger sentinels in `par_f2_max` and `swc3_max`; large negative PAR minima (`par_c3_min` = −1648); impossible temperatures (`tsoil2_e` max 101.8 °C, `tair_us_e_20cm` max 88.5 °C); `swc4_max` = 1.578 above the physical maximum of 1; `par_*_max` labelled dimensionless in the EML; `_ave` column descriptions assign all six PAR sensors to EMS1 while the methods text and `_max` descriptions assign E3, F3, F2 to EMS2 (trust the methods).

### HF282 · Microclimate at HDW Tower since 2014
`parac_up` and `parac_down`: above-canopy PAR at 28 m, up- and down-facing, on the hardwood walk-up tower about 400 m southwest of EMS. **Needed as the fAPAR denominator. Continuity across 2015-2020 not yet verified.**
**Type:** ground, tower · **Page:** `showData.html?id=hf282`

### HF004 · Canopy-Atmosphere Exchange at EMS Tower since 1991
NEE, CO2, H2O and energy fluxes; incident and reflected PAR above canopy. Eddy covariance plus tower radiometers. Reflected PAR archived hourly. **Also needed as the fAPAR denominator; continuity not yet verified.**
**Type:** ground, tower · **Page:** `showData.html?id=hf004`

### HF102 · Radiation Measurements at EMS Tower 1991-2007
Hourly radiation and soil heat flux from the SUNYA boom at 27 m. Out of range for 2015-2020 but the source of the precise tower coordinate, +42.537755, -72.171478, 340 m.
**Type:** ground, tower · **Page:** `showData.html?id=hf102`

### HF183 · Canopy Phenology, Remote Sensing and Microclimate 2006-2011
Top-of-canopy and below-canopy PAR at three below-canopy positions, plus spectral and phenology measurements. Out of range for the main window but useful training data for the understory study.
**Type:** ground · **Page:** `showData.html?id=hf183`

### HF249 · Barn Tower radiometric and meteorological data since 2011
Broadband and spectral radiation. **Check here first for a direct diffuse radiation measurement**, which would remove the need to derive diffuse fraction from a clearness index.
**Type:** ground · **Page:** `showData.html?id=hf249`

### HF300 · Harvard Forest Climate Data since 1964
Air temperature, precipitation, humidity, wind, radiation from the Fisher Meteorological Station. The long-term climate context.
**Type:** ground · **Page:** `showData.html?id=hf300`

### HF407 · Tree Ring Data from EMS Tower 1896-2014
Two 20 m radius plots within the EMS footprint; ring-width to biomass back to 1896.
**Type:** ground · **Page:** `showData.html?id=hf407`

### Unverified IDs
Two datasets are relevant but their archive IDs could not be confirmed, because the archive listing is ambiguous about whether the ID precedes or follows the title. Search the archive by title:
- **PhenoCam Images and Canopy Phenology at the Harvard Forest EMS Tower since 2008** — canopy RGB and green chromatic coordinate, including a below-canopy camera. Also at `phenocam.nau.edu` under site `harvard`.
- **Leaf Area Index at Harvard Forest HEM and LPH Towers since 1998** — additional LAI at the hemlock and upper-slope towers, giving evergreen contrast.

---

## 2. Satellite and airborne data

### HLSL30 / HLSS30 v2.0 · Harmonized Landsat Sentinel-2
30 m NBAR surface reflectance on the MGRS grid, tile T18TYN. 11 bands (L30) or 13 (S30), **four angle bands**, and an Fmask QA layer packing cloud, adjacent-cloud, cloud-shadow, snow, water and aerosol-quality bits. Landsat 8/9 OLI and Sentinel-2 MSI, harmonised through atmospheric correction, cloud and shadow masking, co-registration to a common 30 m grid, nadir BRDF adjustment and spectral bandpass adjustment. 2013-04-11 onward, 2 to 3 day nominal revisit, roughly half of growing-season observations lost to cloud.

**Critical:** the BRDF adjustment normalises **view** angle to nadir. It does **not** normalise solar zenith angle, which is why the seasonal illumination signal survives into the data at all.

**Band naming trap:** Landsat NIR is `B05`; Sentinel-2's 30 m narrow NIR is `B8A`, not `B08`. Using `B08` injects a bandpass difference between sensors that mimics real signal.

**Type:** satellite, 30 m (900 m²) · **Get it from:** AppEEARS · `lpdaac.usgs.gov/products/hlsl30v002/` and `.../hlss30v002/` · AWS Open Data as COG · GEE `NASA/HLS/HLSL30/v002`
**v1.4, used by HF365, is retired.**

### MCD15A2H v061 · MODIS LAI and FPAR, 8-day
LAI, FPAR, plus QC, extra QC and standard deviation layers. Best pixel selected from all Terra and Aqua acquisitions in each 8-day window, via a radiative-transfer retrieval.
**Type:** satellite, 500 m sinusoidal (250,000 m²; one cell holds 238 HLS pixels) · **Get it from:** AppEEARS · `lpdaac.usgs.gov/products/mcd15a2hv061/` · GEE `MODIS/061/MCD15A2H`
**Caution:** this product already models illumination geometry, so it cannot be used to test an illumination hypothesis. Use reflectance products for that.

### MCD43A1 v061 · MODIS BRDF and Albedo Model Parameters, daily
Three BRDF kernel weights per band from a 16-day retrieval window, which permit **re-simulating reflectance at any chosen solar zenith angle.** The closest available approximation to an experimental intervention on illumination.
**Type:** satellite, 500 m · **Get it from:** AppEEARS · `lpdaac.usgs.gov/products/mcd43a1v061/`

### MCD43A4 v061 · MODIS NBAR, daily
Reflectance normalised to nadir view at local solar noon, so it retains seasonal SZA variation. An intermediate case between raw reflectance and fixed-SZA re-simulation.
**Type:** satellite, 500 m · **Get it from:** AppEEARS · `lpdaac.usgs.gov/products/mcd43a4v061/`

### MOD09A1 v061 · MODIS Surface Reflectance, 8-day
Bands 1 to 7 plus solar zenith, view zenith and relative azimuth, so observation geometry can be conditioned on directly.
**Type:** satellite, 500 m · **Get it from:** AppEEARS · `lpdaac.usgs.gov/products/mod09a1v061/`

### MSLSP30NA v011 · Multisource Land Surface Phenology
Phenophase transition dates, EVI2 amplitude and maximum, percent greenness, QA, up to two cycles per year. Derived from HLS by penalised spline fitting. Useful for partitioning early, mid and late season consistently with the published work.
**Type:** satellite, 30 m NetCDF per tile per year · **Get it from:** `lpdaac.usgs.gov/products/mslsp30nav011/`

### NEON DP1.00024.001 · Photosynthetically Active Radiation
Above and below canopy PAR at the HARV tower, about 240 m northeast of the HDW tower. 1-minute and 30-minute. A third independent PAR source.
**Type:** ground, tower · **Get it from:** `data.neonscience.org/data-products/DP1.00024.001`

### NEON DP3.30024.001 · Elevation, LiDAR
1 m digital surface model in metres above sea level, capturing canopy height and 3-D structure including underlying topography. Discrete-return airborne lidar from the NEON Airborne Observation Platform, roughly annual campaigns.
**Type:** airborne, 1 m raster · **Get it from:** `data.neonscience.org/data-products/DP3.30024.001` · GEE `projects/neon-prod-earthengine/assets/DEM/001`

### NEON DP3.30015.001 · Ecosystem Structure (canopy height model)
Canopy height at 1 m, lidar surface minus terrain. Needed for structure covariates and for computing the effective optical footprint of the LAI meter, which scales with canopy height and may approach or exceed 30 m.
**Type:** airborne, 1 m · **Get it from:** `data.neonscience.org/data-products/DP3.30015.001`

### NEON DP1.10017.001 · Digital Hemispheric Photos for LAI
Hemispherical canopy imagery at NEON distributed plots. **The reference for the HARV_049 and HARV_050 coordinates**, which are the two NEON columns in HF365 and are not available from Harvard Forest.
**Type:** ground · **Get it from:** `data.neonscience.org/data-products/DP1.10017.001`

### NEON DP3.30006.001 · Spectrometer Surface Directional Reflectance
Hyperspectral mosaic, roughly 426 bands at 1 m. Higher spectral resolution for species discrimination and canopy optical properties.
**Type:** airborne, 1 m · **Get it from:** `data.neonscience.org/data-products/DP3.30006.001`

### AmeriFlux US-Ha1 · Harvard Forest EMS Tower (HFR1)
NEE, GPP, RECO and meteorology including PAR. BASE and FLUXNET-1F products, both spanning 1991-2025. Eddy covariance, with ONEFlux processing for the FLUXNET version. The GPP validation target.
**Type:** ground, tower · **Get it from:** `ameriflux.lbl.gov/sites/siteinfo/US-Ha1` · doi:10.17190/AMF/1246059

### Prithvi-EO-2.0 · NASA and IBM geospatial foundation model
600M parameters, pre-trained on 4.2M global HLS time-series samples at 30 m using masked autoencoder self-supervision, with 3-D spatiotemporal embeddings. Not data; a pre-trained encoder for exactly the imagery this program uses.
**Get it from:** `github.com/NASA-IMPACT/Prithvi-EO-2.0` · Hugging Face · fine-tuning via TerraTorch

---

## 3. Generated files

| File | Contents |
|---|---|
| `ems_plot_registry.csv` | 40 plots: status, coordinates, UTM 18N, bearing and distance from tower, dominant HLS pixel, whether wholly inside, pixels touched, MODIS cell |
| `crosswalk_plot_to_hls_pixels.csv` | **plot → pixels.** 101 rows with `rank`, `overlap_m2`, `overlap_frac`, `is_dominant`, pixel centre lat/lon |
| `crosswalk_hls_pixel_to_plots.csv` | **pixels → plots.** 93 rows with `n_plots`, `n_active`, `plots`, `plots_dominant`, `total_overlap_m2` |
| `crosswalk_plot_to_modis_pixel.csv` | plot → MODIS cell with centre coordinates |
| `modis_pixels_to_request.csv` | 20-cell block, exact centres, which are already held |
| `aoi_S1_plots_only.geojson` | Plot pixels + 2-pixel buffer: 629 × 881 m, ~615 HLS pixels |
| `aoi_S2_five_modis_cells.geojson` | Union of the five MODIS cells: 2181 × 928 m, ~2249 HLS pixels |
| `aoi_S3_block_5x4_buffered.geojson` | Full 20-cell block: 3899 × 1855 m, ~8038 HLS pixels |

`overlap_frac` is the column that matters. It is the weight for area-weighted aggregation and the diagnostic for how far any plot-pixel comparison should be trusted.

**HLS pixel ID convention:** `floor(E/30)_floor(N/30)` in EPSG:32618. Sentinel-2 tile origins are multiples of 30 m, so these group pixels exactly as the HLS grid does, differing from tile-relative row and column by a constant integer offset. To convert, read `ULX` and `ULY` from any T18TYN granule and apply `col = (E − ULX)/30`, `row = (ULY − N)/30`. Every crosswalk row also carries an unambiguous pixel centre in lat/lon.

**MODIS grid:** sinusoidal, sphere radius 6371007.181 m, cell 463.31271653 m, origin (−20015109.354, 10007554.677). Reprojecting the five held pixel centres through this grid and back reproduces them to 0.04 m.

---

## 4. Retrieving HLS

### Scope

| Scope | Bounding box (W, S, E, N) | Extent | Pixels | Use |
|---|---|---|---|---|
| S1 | −72.178340, 42.533303, −72.170677, 42.541218 | 629 × 881 m | ~615 | Studies 2, 3; HF365 v2 reproduction |
| S2 | −72.188548, 42.533333, −72.161952, 42.541667 | 2181 × 928 m | ~2249 | Study 1, which needs *every* HLS pixel inside each MODIS cell |
| **S3** | −72.199022, 42.529167, −72.151484, 42.545833 | 3899 × 1855 m | ~8038 | Everything, plus transfer to ungrounded cells |

Pull **S3** once. Eight thousand pixels over a decade is small and it supersets the others.

### Route 1 · AppEEARS

1. `https://appeears.earthdatacloud.nasa.gov/`, Earthdata Login, **Extract → Area**
2. Upload `aoi_S3_block_5x4_buffered.geojson`
3. Dates 2015-01-01 to present
4. Products `HLSL30.020` and `HLSS30.020`; add `MCD15A2H.061`, `MCD43A1.061`, `MCD43A4.061` in the same request for co-registration
5. Layers: HLSL30 `B04`, `B05`, `Fmask`, `SZA`, `SAA`, `VZA`, `VAA`; HLSS30 `B04`, `B8A` and the same QA and angle layers. **Take the angle bands** — HF365 has none and every study needs per-observation geometry
6. Output GeoTIFF, native projection. CSV output flattens the grid and destroys pixel identity

### Route 2 · earthaccess, for a reproducible pipeline

```bash
pip install earthaccess rioxarray rasterio geopandas
```

```python
import earthaccess, rioxarray as rxr, geopandas as gpd

earthaccess.login()                               # ~/.netrc or interactive
aoi = gpd.read_file("aoi_S3_block_5x4_buffered.geojson")
w, s, e, n = aoi.total_bounds

granules = earthaccess.search_data(
    short_name   = ["HLSL30", "HLSS30"],
    version      = "2.0",
    bounding_box = (w, s, e, n),
    temporal     = ("2015-01-01", "2026-08-01"),
)

BANDS = {"HLSL30": {"red": "B04", "nir": "B05"},
         "HLSS30": {"red": "B04", "nir": "B8A"}}

def read_window(granule, band, aoi_utm):
    url = [u for u in granule.data_links() if u.endswith(f".{band}.tif")][0]
    return rxr.open_rasterio(url, masked=True, chunks=True).rio.clip_box(*aoi_utm.total_bounds)
```

Streams COGs from the cloud; no bulk download. Read `Fmask` alongside, decode the bits explicitly, and **record which bits you masked on**, because HF365 does not document its own masking and that undocumented choice is one of the reproducibility gaps being closed.

### Route 3 · Google Earth Engine

Correct only for extending training beyond Harvard Forest, where downloading regional HLS is impractical.

```javascript
var aoi = ee.Geometry.Rectangle([-72.199022, 42.529167, -72.151484, 42.545833]);
var l30 = ee.ImageCollection('NASA/HLS/HLSL30/v002').filterBounds(aoi);
```

The GEE collection may lag LP DAAC and its band naming differs. Do not mix GEE and LP DAAC values in one analysis without checking they agree.

### Extracting to plots

Do not sample at plot centroids. Use the overlap weights, and compute **both** conventions:

```python
cw  = pd.read_csv("crosswalk_plot_to_hls_pixels.csv")
dom = cw[cw.is_dominant]                                  # HF365's convention

wtd = (cw.assign(v=cw.hls_pixel.map(pixel_values))
         .groupby("plot")
         .apply(lambda d: (d.v * d.overlap_frac).sum() / d.overlap_frac.sum()))
```
