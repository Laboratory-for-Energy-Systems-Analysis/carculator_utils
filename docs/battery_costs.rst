Battery unit-cost inputs
========================

A battery price input is a price per unit of nominal capacity, not the total
price of the installed pack. This guide explains how an explicit price interacts
with chemistry selection and subsequent cost calculations.

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

Year and sample alignment
~~~~~~~~~~~~~~~~~~~~~~~~~

Automatic cost projections align the ``year`` and ``value`` dimensions by name.
Within a run, each sampled cost factor applies to its sample across all years.
The sensitivity reference has the same prices as the static calculation for
each year, regardless of the number or order of selected years and samples.

This corrects a positional reshaping defect in the shared, car, bus and
two-wheeler cost hooks. It affected multi-year calculations with multiple samples,
including sensitivity references. For example, a three-year, two-sample BEV
calculation assigned EUR 102.57/kWh to the 2025 reference instead of EUR
134.64/kWh. The corrected default battery prices are EUR 186.49, 134.64 and
102.57/kWh in 2020, 2025 and 2030, respectively.

The correction also aligns power-battery, hydrogen-tank, fuel-cell-stack and
CNG powertrain projections where used by the vehicle subclasses. Existing price
curves, random-factor distributions, cost caps and explicit battery-price
precedence are retained. The alignment repair alone preserves static and
single-year results. The subsequent :doc:`cost_uncertainty` repair ties projected
cost draws to the input seed; regenerate stochastic results made with the old
global generator, as well as multi-year sensitivity costs made before alignment
was corrected.
Truck models use a separate sampled-cost calculation and do not call these projections.

Shared fuel-cell component costs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The shared ``VehicleModel.adjust_cost()`` assigns the hydrogen-tank and
fuel-cell-stack curves to distinct parameters: ``fuel tank cost per kg``
(EUR/kg of stored hydrogen) and ``fuel cell cost per kW`` (EUR/kW of stack power).
Previously, it wrote both curves to the tank parameter, overwriting the tank
price and leaving the stack input unadjusted. The corrected deterministic 2025
prices are EUR 625.89/kg and EUR 96.18/kW, respectively, from the existing curves.
Both curves retain the same general per-sample uncertainty factor.

This correction affects direct use of the shared method and subclasses that
inherit it. Cars and buses already assign these fields correctly in their own
cost hooks; the normal truck workflow does not call the shared projection.
The repair does not change the price assumptions. Regressions check the separate
fields across years and sample orders, plus completed static, sensitivity and
seeded FCEV car runs using the shared hook in place of the car override. These
runs reproduce the existing car costs, physical results and sampled inventory
and LCIA results.

Plug-in hybrids
~~~~~~~~~~~~~~~

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
check power batteries and PHEVs, preserve static prices,
and verify identical physical outputs, inventories and LCIA for paired BEV prices.
Cost-alignment regressions cover unequal year/sample counts, unsorted years,
labelled sample draws, all affected component curves and completed sensitivity
references compared with static runs. Paired runs with the pre-fix cost hooks
also verify that correcting multi-year costs leaves physical outputs,
inventories and LCIA unchanged.
These are software contract checks, not empirical validation of the price curve.
