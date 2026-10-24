"""S7: error variance for three collocated streams, without treating any as truth.

**No novelty is claimed here, and the write-up must not imply any.** The
2026-08-08 literature audit found triple collocation already applied to LAI and
FAPAR, and both extensions the program proposed already published: Correlated
Triple Collocation and Extended Quadruple Collocation handle error-correlated
datasets, and representativeness error is a standard additional term with
existing decompositions. What survives is the *product*: a per-observation
uncertainty column on ``hf365_v2_candidate``, which is what the CEOS LPV Stage 3
requirement actually asks for.

The method is applied, cited, and not reinvented.
"""

__version__ = "0.1.0"
