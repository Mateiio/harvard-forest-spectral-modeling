# S7 findings · error variance without a truth assumption

*Regenerated 2026-08-30 by `python -m s7 findings`. Values are read from `s7/out/` on each run.*

**8 of 8 findings reproduce.**

Source: 1,800 three-way collocated observations over 33 plots, 59 ground visits and 5 MODIS cells, 2015-05-28 to 2020-12-03. Ground PAI (314 m2) / HLS EVI2 (900 m2) / MODIS LAI (~215,000 m2).

**No novelty is claimed.** See S7-01.

## Scope

### S7-01 · Both proposed novelty claims are foreclosed by existing work

**Measured:** Triple collocation is already applied to LAI and FAPAR, including a four-product study (GLASS, MCD15A2H, VNP15A2H, CLMS). Correlated Triple Collocation, Extended TC (McColl 2014) and Extended Quadruple Collocation all handle error-correlated datasets; the literature names 'two of three products share a source' as the canonical failure mode. Representativeness error is a standard additional term with published estimation methods

**Impact:** S7 ships as an applied deliverable only. The write-up must not claim TC on vegetation indices, correlated-error TC or representativeness decomposition as new. The program document's 'TC rarely used on LAI and fAPAR' is wrong.

*Source:* literature audit 2026-08-08 · *Reproduces:* yes

## Model validity

### S7-02 · NDVI violates the linearity TC requires; EVI2 does not

**Measured:** on EVI2 a quadratic term reduces residual sum of squares by 0.0005 % (p=0.927). On NDVI the same test cuts 14.1 % against ground and 22.9 % against MODIS

**Impact:** TC's model is linear. NDVI saturates against LAI, so running TC on it returns model error dressed as measurement error. The product uses EVI2.

*Source:* s7/tc.py:linearity · *Reproduces:* yes

### S7-06 · Rows are not independent; naive bootstrap intervals are too narrow

**Measured:** 1,800 rows reduce to 279 independent (date, MODIS cell) blocks -- 5 cells serve 59 ground dates. Row resampling gives intervals 2.2x too narrow

**Impact:** Every plot inside one MODIS cell shares the same MODIS value on a date.

*Source:* s7/tc.py:block_bootstrap · *Reproduces:* yes

### S7-07 · Per-season uncertainty is not estimable from this data

**Measured:** 6 of 8 strata fail validity: every within-season stratum returns a correlation with truth outside (0,1) or collapsing toward zero. The growing season retains only 18 % of the record's plant-area-index variance

**Impact:** TC needs the latent quantity to vary. Within a season it does not, and the shoulder seasons change fast enough that +-4 day matching is itself disagreement. Only strata spanning the full cycle survive.

*Source:* s7/results.py, gated on MIN_SIGNAL_VAR_FRAC = 0.5 · *Reproduces:* yes

## Results

### S7-03 · Error variance of each stream, estimated without a reference

**Measured:** ground sd 0.7588 PAI (95 % CI [0.6866, 0.8166], rho2 with truth 0.705); hls sd 0.0197 EVI2 (95 % CI [0.0062, 0.0397], rho2 with truth 0.987); modis sd 1.1435 LAI (95 % CI [0.9642, 1.2967], rho2 with truth 0.712)

**Impact:** Each in its own units. No dataset is nominated as truth.

*Source:* s7/tc.py, 1,800 triplets, ground PAI / HLS EVI2 / MODIS LAI, +-4 day matching · *Reproduces:* yes

### S7-04 · The ground measurement is not truth

**Measured:** 29 % of ground PAI variance is error (rho2 with truth 0.705), comparable to MODIS at 29 %. HLS EVI2 is 1.3 %

**Impact:** Validation that treats plot measurements as truth mis-attributes roughly a third of the disagreement to the satellite.

*Source:* s7/tc.py · *Reproduces:* yes

### S7-05 · The data bounds how correlated the two satellite errors can be

**Measured:** sweeping assumed HLS-MODIS error covariance: classical TC (0 %) flatters both satellites and penalises the ground; at 30 % the ground's correlation with truth exceeds 1, which is impossible

**Impact:** HLS and MODIS share optical physics, so their errors are correlated by construction and the independence assumption is known to fail. The true correlation lies below the bound.

*Source:* s7/tc.py:sensitivity · *Reproduces:* yes

## Deliverable

### S7-08 · The product now ships per-observation uncertainty

**Measured:** `evi2_sd_tc` on 14,406 usable observations, per product: L30 sd 0.0145 EVI2 (3.0 % of a typical value), S30 sd 0.0227 EVI2 (4.3 % of a typical value). Sentinel-2 carries 1.6x Landsat's error

**Impact:** An archived product shipping characterised uncertainty meets the CEOS LPV Stage 3 requirement. Pooling the two streams unweighted treats unequal observations as equal.

*Source:* s7/results.py -> s1/out/hf365_v2_candidate.csv · *Reproduces:* yes
