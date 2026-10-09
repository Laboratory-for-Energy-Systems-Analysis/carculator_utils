.. _usage:

Usage
=====

This package provides shared machinery, without standalone default vehicles.
Use ``CarInputParameters`` / ``CarModel`` / ``InventoryCar`` from ``carculator``,
or the corresponding truck, bus and two-wheeler classes for full calculations.
The following shared-background example requires only ``carculator_utils``.

Quick start
-----------

.. code-block:: python

   from carculator_utils.background_systems import BackgroundSystemModel

   background = BackgroundSystemModel()
   print(sorted(background.fuel_specs))


Inputs and scope
----------------

The vehicle input classes provide packaged defaults. Call ``static()`` for a
single deterministic sample, or ``stochastic(n, seed=42)`` for seeded parameter
draws. The array builder returns ``(mappings, array)`` and preserves labelled
``size``, ``powertrain``, ``parameter``, ``year`` and ``value`` dimensions.
Scope by actual labels and native input years; interpolate explicitly when a
year is not in the parameter table. The current defaults include 2025.

Change input parameters before constructing a fresh vehicle model. Constructor
overrides such as battery chemistry, capacity, fuel blends and component
efficiencies are copied, preserving the caller's data. Most vehicle overrides
use ``(powertrain, size, year)`` keys; consult the model API for exceptions.
Repeated ``set_all()`` calls on an already completed model are not the supported
way to compare independent scenarios.

Fuel blends after year selection
--------------------------------

Fuel-share and property vectors follow the input array's year order at model
construction. The model retains those source-year labels, so a completed model
can be copied and narrowed or reordered before constructing an inventory:

.. code-block:: python

   from copy import deepcopy
   from carculator import InventoryCar

   # model is a completed CarModel containing 2025 and 2030.
   selected = deepcopy(model)
   selected.array = selected.array.sel(year=[2030, 2025])
   inventory = InventoryCar(selected)
   aligned_blend = selected.get_fuel_blend()

``get_fuel_blend()`` returns an independent copy in current array-year order;
``get_fuel_blend([2025])`` requests an explicit subset. ``inventory.fuel_blend``
returns a copy aligned to the inventory's year scope. The original
``model.fuel_blend`` dictionary remains in constructor-year order: do not trim
its vectors manually when selecting the model array. Scalars still apply to
every year, and supplier identities remain unchanged. Heating values, densities,
CO2 factors and biogenic fractions follow the same labels as the fuel shares.

Selecting years does not create a new fuel scenario or rerun sizing. For new
years, interpolation or different blend assumptions, build a fresh model from
the corresponding inputs. Unknown years, malformed vectors and missing
source-year provenance raise an explicit error instead of guessing. Rebuild
fuel-using model objects saved before this correction, because they lack those
labels. See :ref:`fuel-blend-year-selection` for validation and impact examples.

Energy and results
------------------

``model["TtW energy"]`` is kJ per vehicle-kilometre. For BEVs it is net
stored-energy depletion; ``model.battery_terminal_energy`` is a separate DC
boundary, and ``model["electricity consumption"]`` is grid electricity in
kWh/km. Multiply the latter by 100 for kWh/100 km.

Construct the inventory with the completed model, not its raw parameter array.
Use ``calculate_impacts()`` and labelled selection/reduction of the returned
xarray. Functional units are ``vkm``, ``pkm`` and ``tkm``. Passenger- and
cargo-normalized results require finite positive loads for active vehicles.
Availability-masked zero consumption does not describe a zero-energy vehicle.

Default charging/fuel-preparation electricity follows each vehicle and sample's
own operating lifetime. See :doc:`electricity_scenarios` for the refreshed
Ember/GECO data, explicit electricity scenario selection and legacy reproduction.
Inspect ``inventory.electricity_mix`` for the labelled
shares; ``inventory.mix`` is only a summary. Explicit custom mixes remain
supported. See :doc:`electricity_lifetime` for annual averaging, background-year
limits and the corresponding inventory/export behavior.

Results preserve the model's ``value`` labels and their order, including a
selected Monte Carlo sample such as ``1`` or reordered sensitivity samples.
Use ``calculate_impacts(sensitivity=True)`` for ratios to the sample labelled
``reference``; that reference must be retained but need not be first.


Inventory export
----------------

Brightpath supplies the export writers; see :doc:`inventory_export` for format
details and the openLCA linking limitation.
With a vehicle package installed, after its complete model and inventory
calculation, the shared public API is:

.. code-block:: python

   paths = inventory.export_lci(
       ecoinvent_version="3.10",
       software="brightway2",
       format="file",
       directory="exports",
       filename="vehicle-comparison",
   )

``software`` accepts ``brightway2``, ``simapro`` or ``openlca``. Brightway export
supports ``file``, ``string`` and ``bw2io``; SimaPro and openLCA support ``file``
and ``string``. openLCA produces a foreground-only JSON-LD ZIP that requires
background and elementary-flow linking before calculation.
The supported ecoinvent targets are 3.9 and 3.10. Multi-year runs preserve every
year in the returned exports, and exporting does not change the original
inventory or calculated impacts. A destination Brightway/ecoinvent setup is
needed to register and link exported inventories, not for the core calculation.

Exports require exactly one retained ``value`` sample. For a sampled array,
select it before constructing a fresh model and inventory, for example::

   selected = array.isel(value=[1])  # Retain the second draw and its value label.
   model = CarModel(selected)       # Or the corresponding vehicle-model class.
   model.set_all()
   inventory = InventoryCar(model)
   importer = inventory.export_lci(format="bw2io")

The brackets retain the ``value`` dimension. Numeric labels other than zero and
named samples such as ``reference`` are supported; exchange amounts and vehicle
comments describe the same selected sample. Multiple samples raise an error;
the exporter does not average samples or generate uncertainty distributions.

SimaPro's ``Comment`` field retains the generated manufacture year and vehicle
parameters, including consumption and battery capacity where applicable.
Activity-specific comments and sources take precedence over the reference
catalog; the catalog supplies only absent fields. A missing source does not
produce a placeholder citation. Empty comments identify the inventory as
generated by carculator_utils. File and string exports use Brightpath's Latin-1
CSV encoding and quoting; embedded line breaks become SimaPro's DEL character.
Parse with a semicolon-delimited CSV reader using standard double-quote escaping,
without a backslash escape character. See :doc:`inventory_export` for naming,
encoding and noise-flow limitations.

Reproducibility and interpretation
----------------------------------

Record package versions, input overrides, driving cycle, load, geography,
fuel blend, background scenario, functional unit and energy meter boundary.
``stochastic(n, seed=42)`` also seeds projected-cost factors. Keep the array's
auxiliary coordinates and build fresh models for independent runs; see
:doc:`cost_uncertainty` for sample selection and legacy-array behavior.
See :doc:`validity` for the scope of
calibration, measurement comparisons and known limitations.
