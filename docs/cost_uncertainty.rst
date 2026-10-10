Reproducible cost uncertainty
=============================

Sampling an uncertain input and repeating the same model calculation are
different operations. This page explains which cost adjustments use random draws
and how their seeds preserve the identity of each sample.

``inputs.stochastic(n, seed=42)`` now controls both input-parameter draws and
the additional projected-cost factors used by cars, buses and two-wheelers.
With the same package versions, inputs and seed, fresh models built from these
arrays reproduce their cost results without calling ``numpy.random.seed``.
Parameter draws retain their existing sequence; cost factors use separate local
random streams and neither sampling nor cost projection consumes NumPy's global
random state.

Previously, the cost hooks drew from the process-wide generator every time a
model ran. Two completed 2025 Medium BEV car runs using three samples and
``seed=42`` reproduced their physical inputs but gave first-sample purchase
costs of EUR 43,294 and EUR 41,534. The defect also affected buses and
two-wheelers. The truck model uses its sampled cost records and does not call
these projection hooks.

Distributions and sample identity
---------------------------------

The existing assumptions are retained:

* General projected costs use a triangular factor with lower bound 0.7,
  mode 1 and upper bound 1.3. A sample shares its factor across years,
  sizes and the affected component-cost curves.
* Bus hydrogen tanks and fuel-cell stacks share a separate triangular factor
  with lower bound 3, mode 5 and upper bound 6. This stream is independent of
  the general factor.
* Static and sensitivity inputs use factors 1 and 5, respectively for the two
  distributions. Removing the sensitivity reference does not introduce random
  cost variation.
* Explicit battery prices remain absolute inputs and take precedence over
  projected prices; see :doc:`battery_costs`.

The array builder stores factors as private ``value`` coordinates
``_cost_factor`` and ``_cost_factor_fcev``. Keep these coordinates when
selecting, reordering, interpolating or saving arrays. NetCDF round trips
preserve them. A sample selected on its own retains its original draw, and
repeated array construction or fresh model construction does not redraw it.
Without an explicit seed, each new ``stochastic(n)`` call draws new factors,
which are then retained in the same way.

``stochastic(1)`` now also samples these factors. Previously, a one-sample
array was treated as deterministic even when its parameters were stochastic.
Use ``static()`` for deterministic inputs and cost factors. Stochastic numerical
cost results should be regenerated after this correction; the distributions,
price curves and deterministic prices are unchanged. This is a reproducibility
repair, not an empirical calibration of ownership costs.

Older and manually constructed arrays
-------------------------------------

Arrays without cost-factor coordinates remain supported. The first cost
projection attaches local, unseeded draws to the model's private array and
reuses them on subsequent projections. Legacy single-sample and sensitivity
arrays retain deterministic factors. Such arrays cannot recover the original
input seed: rebuild inputs with the current array builder for reproducible
stochastic costs. An incomplete or invalid factor coordinate raises an error
instead of silently resampling.

Build fresh models from input arrays for independent runs. Completed family
models now retain their inputs for repeatable ``set_all()`` calls; see
:doc:`repeated_runs` for supported edits and PHEV restrictions. Record the seed,
package versions, inputs and scenario alongside results; reproducibility across
arbitrary dependency versions is not promised.

Verification
------------

Regressions check unchanged parameter draws, global RNG isolation, independent
triangular distributions, selected sample identity under array transformations
and NetCDF, and deterministic static/sensitivity factors. Completed car, bus
and two-wheeler runs cover BEV and combustion costs, fuel cells where supported,
single-sample selections and explicit per-sample battery prices. Paired physical,
inventory and impact checks distinguish this numerical change from changes to
vehicle energy or environmental performance.
