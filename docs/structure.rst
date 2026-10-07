.. _structure:

Shared model structure
======================

``carculator_utils`` supplies common modelling machinery to the passenger-car,
bus, truck and two-wheeler packages. Vehicle-specific input records and sizing
policies remain in those packages; the shared package does not ship a generic
vehicle parameter table that can replace them.

.. list-table:: Responsibilities
   :header-rows: 1
   :widths: 35 65

   * - Module
     - Role
   * - ``vehicle_input_parameters`` and ``array``
     - Input validation, static/seeded sampling and labelled vehicle arrays.
   * - ``model`` and ``numerical``
     - Shared overrides, battery/fuel accounting and bounded sizing iteration.
   * - ``driving_cycles`` and ``energy_consumption``
     - Cycle/grade resources, road load, conversion losses and auxiliaries.
   * - ``combustion_controls``
     - Opt-in conventional petrol-car control rules and buffer accounting.
   * - ``hot_emissions``, ``particulates_emissions`` and ``noise_emissions``
     - Direct operation-related emissions.
   * - ``background_systems``
     - Fuel properties, electricity mixes and background assumptions.
   * - ``inventory`` and ``export``
     - Inventory construction, LCIA and optional external-format export.

Workflow and boundaries
-----------------------

A vehicle-specific input class loads its package data and supplies static or
sampled values. ``fill_xarray_from_input_parameters`` returns mappings and an
array with dimensions ``size``, ``powertrain``, ``parameter``, ``year`` and
``value``. The vehicle-specific model's ``set_all()`` couples mass, power,
storage and energy through bounded sizing before constructing inventory inputs.

Energy traces distinguish wheel demand, shaft load, battery-terminal energy,
stored-energy depletion and charging electricity. Their units and comparison
boundaries are described in :doc:`energy_model_repairs`. Availability masks
identify unsupported vehicle configurations; a masked zero is not a physical
prediction. Calibration evidence and reproducibility checks are described in
:doc:`validity` and :doc:`temporal_energy`.

Use the vehicle package's public model and inventory classes for a complete
calculation. See :doc:`api` for shared interfaces and :doc:`input_validation`
for array, sampling and override contracts.
