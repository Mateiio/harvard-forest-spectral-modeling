# Study 2 — angular

Whether solar zenith angle biases the HF365 record, which the original authors
explicitly invited someone to investigate.

**Status: notebook one of several.** `01_Ingest_QC.ipynb` loads and quality-checks the
half-hourly PAR and canopy data; no analysis is implemented yet. The sun-angle numbers
quoted in [the report](../docs/predicting-forest-leaf-area.md#the-sun-angle-question)
were computed for the write-up and do not live in code here.

`study2_lib.py` is the shared layer: site constants, the QC filters, solar geometry via
pvlib, and the canopy equations transcribed from the source paper and numbered as it
numbers them. Two things in it are deliberate and load-bearing:

- **Equation 8 prints wrong.** As published it returns −0.06 at LAI 0. Both the printed
  and the corrected form are implemented (`EQ8_FORM`) and the choice is made
  empirically, not silently.
- **The leaf-angle parameter is never defaulted.** The paper uses `x = 3` (planophile);
  `x = 1` is spherical. This choice dominates the modelled SZA response, so analysis
  code has to name it.

The source paper is SSRN preprint 4237352. It is not redistributed here, so the
`docs/ssrn-4237352.pdf` path in the module docstring refers to a local copy you supply.
