"""S8: retrieving ground leaf area index from the reprocessed HF365 archive.

The target is HF069's plot measurement, not a satellite product. Every earlier
forecasting attempt in this project predicted MODIS ``Lai_500m`` from HF365
indices, which is one optical retrieval predicting another; S8 predicts the
thing on the ground.

**Three findings shape the design, and each was measured before any model was
fitted.**

*Day-of-year is most of the answer.* HF069 samples March to December, so 78 % of
plant-area-index variance is seasonal. A calendar with no satellite input at all
scores R2 0.649. That is the baseline every configuration is reported against,
because a model that does not beat it has learned nothing about vegetation.

*Plot identity is worth as much as the spectra.* A static per-plot offset holds
14.0 % of the variance, and the satellite cannot see it -- S1-06 measured
between-pixel spread inside a plot footprint at 2.1 % of the seasonal signal.
Plot dummies alone beat all three indices. They are therefore a declared part of
the model, not a nuisance term, and they split the study into two questions with
two different honest scores:

  * **known plot, new date** -- dummies in, folds grouped by campaign
  * **new plot** -- dummies out, folds grouped by plot

*Zenith angle belongs to S4, not here.* SZA regressed on a day-of-year harmonic
returns R2 0.9878 with a residual sd of 1.49 degrees, so at this latitude and
near nadir it is the calendar wearing a hat. It is carried in the pair table for
inspection and is deliberately not a model feature. Illumination geometry earns
its keep where it varies within a day at a fixed canopy, which is S4's design.

**MODIS is excluded, by measurement.** Adding ``Lai_500m`` and ``Fpar_500m``
moved R2 from 0.789 to 0.783. Its five cells differ by 0.134 LAI on a typical
date, so it cannot resolve plots; 35 % of its good-quality retrievals are flagged
saturated; 69 used the backup empirical algorithm, which is itself an NDVI
regression and circular against HLS predictors; and it ends 2020-12-26, costing
half the pairs.

**The target is derived, not observed.** HF069 measures plant area index -- the
instrument cannot tell a leaf from a branch. S8's LAI is ``PAI - min(PAI)`` per
plot, WP0's ``lai_subtractive_fx``. Both series are fitted and reported, because
with plot dummies in the model they differ only by a constant the dummies
already absorb, and saying so is cheaper than letting a reader assume otherwise.
"""

__version__ = "0.1.0"
