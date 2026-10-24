"""S4: separating illumination geometry from canopy change, using matched solar angles.

At 42.54 N the sun sweeps tens of degrees within a single day while leaf area,
leaf angle, chlorophyll and structure stay physically constant. Solar noon at
the solstice sits near 19 degrees; 7 AM that same day near 64; and solar noon on
1 December also near 64. A July morning and a December midday therefore sample
*identical illumination through different canopies*.

That gives two sampling routes to the same solar zenith angle, and the contrast
between them is the decomposition:

  * same day, different SZA  -> geometry alone (canopy is constant)
  * same SZA, different day  -> canopy alone (illumination is constant)

**The primary instrument is a matched-pair contrast, not a fitted model.** The
GAM in :mod:`s4.response` only smooths and pools what the pairing has already
separated. It is never asked to predict, never scored on held-out accuracy, and
never claimed to beat anything -- the baseline is Fensholt unmodified, which the
program says to characterise rather than beat.

This matters because SZA and day-of-year are strongly dependent by construction,
which is the whole phenomenon. A GAM given smoothers for both suffers concurvity:
the terms compete for the same variance and the marginal SZA curve becomes
arbitrary. The matched pairs break that confound by design.

**Target is measured transmittance**, tau = understory PAR / above-canopy PAR --
a direct ratio of two instruments. It needs none of the Lee et al. equations
that currently gate S2 and WP0's radiometry block.
"""

__version__ = "0.1.0"
