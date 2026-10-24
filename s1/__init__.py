"""S1: HF365 reprocessed from HLS v2.0.

Produces ``hf365_v2_candidate`` -- a candidate successor to the archived HF365,
not an archive release. Publishing it as a new version needs the original
dataset lead's sign-off; this package builds the thing to propose.

Reads WP0's artifacts (plot registry, HLS crosswalk, recovered v1.4
reflectance, solar geometry, field LAI) and writes into WP0's provenance
contract so both halves verify together.
"""

__version__ = "0.1.0"
