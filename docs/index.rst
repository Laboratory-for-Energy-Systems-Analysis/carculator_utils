Carculator utils: shared vehicle modelling
==========================================

``carculator_utils`` supplies the shared parameter handling, driving-cycle
physics, background systems, inventories and exports used by ``carculator``,
``carculator_truck``, ``carculator_bus`` and ``carculator_two_wheeler``.
It does not provide standalone vehicle defaults: use a vehicle package's input,
model and inventory classes for a complete calculation.

Start with :doc:`installation`, :doc:`usage` and :doc:`validity`.
The shared validation pages retain the measurement catalogs, cycle diagnostics,
energy-accounting repairs and inventory audits. Some older methodology pages
describe the passenger-car application; the vehicle repositories document their
own sizing, service constraints and calibration scopes.

User's Guide
------------

.. toctree::
   :maxdepth: 2

   installation
   usage
   input_validation
   battery_costs
   cost_uncertainty
   modeling
   structure
   validity
   biological_methane
   bev_target_range_issue
   hot_emission_audit
   energy_validation_2025
   energy_measurements
   energy_model_repairs
   adac_cycle_comparison
   truck_energy_diagnostics
   petrol_car_energy_diagnostics
   combustion_controls
   temporal_energy

API Reference
-------------

.. toctree::
   :maxdepth: 2

   api

Project information
-------------------

.. toctree::
   :maxdepth: 1

   release

.. toctree::
   :maxdepth: 2
   :hidden:

   references/references
