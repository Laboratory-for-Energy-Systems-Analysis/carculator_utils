Battery unit-cost inputs
========================

Cars, buses and two-wheelers project default battery unit costs by model year.
Previously, this projection silently replaced user prices, including prices for
the selected chemistry. Explicit prices now survive both chemistry selection and
cost adjustment and feed purchase, replacement and annualized ownership costs.
Untouched defaults retain the existing trajectory. This correction does not
recalibrate battery prices or change vehicle physics or environmental inventories.

Explicit prices
---------------

Use the model constructor to unambiguously specify a price, including zero or a
value equal to a packaged input. For example, with a passenger-car array that
contains a Medium BEV in 2025:

.. code-block:: python

   model = CarModel(
       array,
       battery_costs={
           "energy battery cost per kWh": {("BEV", "Medium", 2025): 100},
       },
   )
   model.set_all()

Keys identify a parameter, then ``(powertrain, size, year)``. Each amount is a
finite, nonnegative scalar or a sequence with one amount per ``value`` sample,
in the array's current sample order. Prices use EUR/kWh for nominal stored energy
or EUR/kW for ``power battery cost per kW``, before the existing vehicle markup.
They are absolute inputs: the model does not additionally apply its random price
factor to an explicit amount. Other stochastic costs keep their existing behavior.

The same constructor argument is inherited by the vehicle models. Truck models
already use input battery prices without the automatic year projection applied by
the other three families; their default pricing is unchanged.

Editing parameter arrays and records
------------------------------------

Ordinary edits made before constructing the model are also retained:

.. code-block:: python

   array.loc[dict(
       parameter="energy battery cost per kWh",
       powertrain="BEV", size="Medium", year=2025,
   )] = 100
   model = CarModel(array)
   model.set_all()

Changed battery-cost records supplied through input dictionaries or JSON files
are treated as explicit definitions, including their sampled values. Changes to
``inputs.values`` after ``static()`` or ``stochastic()`` are retained too.

For energy batteries, precedence is:

1. An explicit generic ``energy battery cost per kWh``.
2. An explicit ``energy battery cost per kWh, <chemistry>`` for the selected
   chemistry, if that parameter is present.
3. The existing default price behavior.

An explicit generic price therefore intentionally overrides an explicit chemistry
price for the same vehicle/sample. Unselected chemistries do not affect its price.
Choosing a chemistry alone does not imply a newly calibrated chemistry price.

The array builder attaches private auxiliary coordinates with reference costs and
custom-definition flags. These follow xarray selection, interpolation, transposing,
sample reordering and NetCDF serialization. Keep them when editing arrays. An
assignment that leaves a default value unchanged cannot signal intent; use
``battery_costs`` in that case. Use it also for older or hand-built arrays without
these coordinates. Build fresh models from input arrays for independent runs.

Sensitivity and plug-in hybrids
-------------------------------

For generated sensitivity samples, the battery-cost perturbation is 10% of the
effective projected default. Custom definitions instead retain their own perturbed
prices. A constructor override is an absolute amount and takes precedence over
these generated perturbations.

Combined ``PHEV-p`` and ``PHEV-d`` results are built from their electric and
combustion components after costs are calculated. Set prices on ``PHEV-e`` and
``PHEV-c-p`` or ``PHEV-c-d``. Leave the combined input unchanged, or explicitly
give it the same price as both components. An explicit combined-only price raises
an error instead of being silently discarded. The shared ``PHEV-e`` component
also means separately scoped runs are needed for different electric-component
prices in petrol and diesel PHEVs.

Verification
------------

The focused shared tests cover labelled selections, interpolated years, custom
files, per-sample prices, invalid values, zero, chemistry precedence, sensitivity
and serialization. Completed family tests compare explicit prices with purchase
and replacement-cost differences calculated from capacity and markup. They also
check power batteries and PHEVs, preserve static and stochastic default results,
and verify identical physical outputs, inventories and LCIA for paired BEV prices.
These are software contract checks, not empirical validation of the price curve.
