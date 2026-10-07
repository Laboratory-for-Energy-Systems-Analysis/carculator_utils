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

Reproducibility
---------------

The model-specific ``docs/validity.rst`` pages state what was calibrated, what
was merely compared, and which measurements are still missing. The shared
artifact index at ``docs/_static/energy_validation_2025/README.md`` distinguishes
current results from retained investigation history. Original inputs and
calibration metadata remain packaged with each vehicle model.
