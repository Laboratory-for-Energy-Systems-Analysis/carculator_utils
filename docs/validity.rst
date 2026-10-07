.. _validity:

Shared-model validation
=======================

``carculator_utils`` provides shared physics, parameter handling and inventory
machinery; vehicle-specific calibration belongs to the four vehicle packages.
A passing software test and agreement with a measured vehicle answer different
questions. The current evidence review separates analytical conservation tests,
numerical convergence, fitted assumptions, held-out observations and screening
comparisons with imperfectly matched cycles or meter boundaries.

Current evidence
----------------

* :doc:`hot_emission_audit` records completed family inventory runs and unresolved
  pollutant mapping, speciation, energy-boundary and deterioration defects.
* :doc:`energy_model_repairs` describes adopted accounting repairs and priors.
* :doc:`energy_measurements` records 40 model runs, 41 paired observations and
  77 exclusions. It distinguishes charging AC, battery-terminal DC and unknown
  electrical boundaries.
* :doc:`temporal_energy` preserves the 2025 anchors and checks 546 annual cases,
  including availability-masked historical cells. It is a temporal regression
  audit, not 546 independent empirical validations.
* :doc:`adac_cycle_comparison`, :doc:`truck_energy_diagnostics` and
  :doc:`petrol_car_energy_diagnostics` retain the vehicle-specific diagnostic
  evidence and limits. Two-wheelers have no new independent measured calibration
  in that catalog.

The analytical tests cover shaft/input energy, road load, regenerative recovery,
auxiliary losses, explicit overrides and battery boundaries. The family artifact
verification passed 436 tests plus one existing expected failure and offline
model/LCIA smoke checks. The saved report in :doc:`temporal_energy` identifies
its runtime and inputs. Empirical residuals remain conditional on source quality
and matched test settings; no fixed error threshold substitutes for physics.

Driving-cycle checks
--------------------

Use the shared public cycle loader rather than importing removed car modules.
For a one-second speed trace, metres/second summed over time gives metres;
divide by 1,000 to report kilometres::

   import numpy as np
   from carculator_utils.driving_cycles import get_standard_driving_cycle_and_gradient

   speed_kmh, gradient = get_standard_driving_cycle_and_gradient(
       "car", ["Medium"], "WLTC"
   )
   active = np.isfinite(speed_kmh[:, 0])
   velocity_ms = speed_kmh[active, 0] / 3.6
   distance_km = velocity_ms.sum() / 1000
   duration_seconds = len(velocity_ms)

Named cycles can contain storage padding; use their documented active-duration
contract, not the stored array length. Custom cycles include all supplied
samples, including terminal stops. Rate/grade provenance and power-feasibility
checks remain necessary for measured-route comparisons.

Fuel-blend inventory checks
----------------------------

``tests/test_fuel_blend_inventory.py`` completes parameter loading, vehicle
sizing, inventory construction and LCIA for all four vehicle families. It
uses Medium cars, 13m-city buses, 40t long-haul trucks and Motorcycle 11-35kW
two-wheelers. The 16 runs cover 22 family/powertrain combinations, three years
(2020, 2025 and 2030), and two passenger-load samples: 528 vehicle/year/sample
cases across the four blend configurations.

The configurations are country defaults, fossil/biofuel blends, selected
synthetic-fuel blends, and two blend components sharing one supplier. Explicit
blends use primary mass shares of 100%, 65% and 0% in successive years. These
are accounting stress tests, not recommendations for engine fuel compatibility.
Hydrogen from natural-gas reforming and PEM electrolysis is included for fuel
cell vehicles; BEVs provide zero-fuel and zero-tailpipe-CO2 controls. Passenger
cars also include petrol/diesel hybrids and plug-in hybrids; buses include
diesel hybrids; trucks include diesel hybrids and plug-in hybrids.

Independent expectations check:

* burned fuel mass = combustion energy / blend lower heating value;
* PHEV combustion energy = combustion-mode energy times one minus the electric
  utility factor;
* fuel-market inputs equal component mass shares, summed when suppliers coincide;
* transport fuel purchases equal burned mass, with the existing pump-to-tank
  leakage allowance added for methane;
* fossil and non-fossil tailpipe CO2 equal burned mass times the corresponding
  share-weighted fuel carbon factors; and
* other fuel inputs are zero and completed impact results are finite.

The audit exposed and repaired two shared inventory defects. A second component
pointing to the same supplier overwrote the first component's exchange. PHEV
tailpipe CO2 used weighted tank mass divided by combined range instead of the
fuel consumption used by its supplier exchange. The latter understated fossil
CO2 by up to 18.4% for the tested default petrol PHEV cars and about 0.7% for
the tested default diesel PHEV trucks. Both fossil and non-fossil CO2 now use
the fuel-consumption mass basis. These corrections affect inventory accounting,
not driving-cycle fuel consumption or the calibrated energy parameters.

This verifies propagation of the bundled fuel specifications, not independent
validation of upstream production datasets, every synthetic-fuel carbon-source
classification, or every vehicle size. In particular, the existing
``biogenic_share`` field also serves as the non-fossil accounting flag for
some synthetic fuels; passing this test does not establish that captured CO2
is physically biogenic. CO2 follows the model's complete-oxidation convention;
this is not an elemental balance including separate CO, methane and hydrocarbon
emission models. Shares are mass fractions, not petrol-station volume blends.

Run the checks with all four sibling packages installed::

   CARCULATOR_REQUIRE_FAMILY=1 python -m pytest tests/test_fuel_blend_inventory.py

Reproducibility
---------------

The model-specific ``docs/validity.rst`` pages state what was calibrated, what
was merely compared, and which measurements are still missing. The shared
artifact index at ``docs/_static/energy_validation_2025/README.md`` distinguishes
current results from retained investigation history. Original inputs and
calibration metadata remain packaged with each vehicle model.
