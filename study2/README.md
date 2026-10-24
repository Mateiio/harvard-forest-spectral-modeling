# Study 2 — angular

Whether solar zenith angle biases the HF365 record. The original authors invited this
investigation.

Status: ingest and QC only. `01_Ingest_QC.ipynb` loads and quality-checks the half-hourly
PAR and canopy data. No analysis is implemented. The sun-angle numbers in
[the report](../docs/predicting-forest-leaf-area.md#the-sun-angle-question) were computed
for the write-up and are not in code here.

`study2_lib.py` holds the site constants, the QC filters, solar geometry via pvlib, and the
canopy equations, transcribed from the source paper and numbered as it numbers them. Two
details to know before using it:

- Equation 8 as printed returns −0.06 at LAI 0. Both the printed and the corrected form
  are implemented (`EQ8_FORM`), and the choice is made empirically at gate G3.
- The leaf-angle parameter has no default. The paper uses `x = 3` (planophile); `x = 1` is
  the spherical case. The choice dominates the modelled SZA response.

Source paper: SSRN preprint 4237352, not redistributed here. The `docs/ssrn-4237352.pdf`
path in the module docstring refers to a local copy.
