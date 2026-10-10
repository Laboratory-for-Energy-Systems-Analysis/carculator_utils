Carculator utils: shared vehicle modelling
==========================================

``carculator_utils`` supplies the calculation methods used by ``carculator``,
``carculator_truck``, ``carculator_bus`` and ``carculator_two_wheeler``. It handles
inputs, driving-cycle energy, fuel and electricity supply, emissions, inventories
and exports. A complete calculation uses a vehicle package's defaults and classes.

Start with :doc:`usage`, then :doc:`interpretation` for terms and units.
:doc:`validation_examples` shows what the available evidence can and cannot tell
us. The technical guides below explain individual assumptions in more detail.

Getting started
---------------

.. toctree::
   :maxdepth: 1

   installation
   usage
   interpretation
   validation_examples
   modeling
   structure
   inventory_export

Inputs and assumptions
----------------------

.. toctree::
   :maxdepth: 1

   input_validation
   input_completeness
   repeated_runs
   battery_costs
   cost_uncertainty
   base_costs
   fuel_catalogue
   biological_methane
   methane_leakage
   carbon_accounting
   electricity_lifetime
   electricity_scenarios
   electricity_coverage
   bev_target_range_issue
   combustion_controls

Evidence and recorded checks
----------------------------

.. toctree::
   :maxdepth: 1

   validity
   energy_measurements
   adac_cycle_comparison
   truck_energy_diagnostics
   petrol_car_energy_diagnostics
   temporal_energy
   energy_model_repairs
   hot_emission_audit
   lcia_metadata
   background_rebuild

Development and historical records
----------------------------------

These records explain earlier findings and completed repairs. Their dates and
software revisions matter: historical failures and test counts are not a
statement of current behaviour.

.. toctree::
   :maxdepth: 1

   approved_fixes
   energy_validation_2025
   documentation_review
   release
   api

.. toctree::
   :maxdepth: 1
   :hidden:

   references/references
