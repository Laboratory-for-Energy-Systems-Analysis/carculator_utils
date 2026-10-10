Energy-model repairs and calibration status
===========================================

The shared energy model now has analytical and full-vehicle regression checks
for the accounting defects identified in the 2025 review. Physical consistency
takes precedence over achieving an arbitrary residual target. Only the city-bus
auxiliary prior was fitted to consumption in this review; the other changes are
physics repairs, component assumptions or diagnostic experiments.

Current accounting
------------------

* Engine load uses shaft output, including combustion auxiliaries, divided by
  rated shaft power. Transmission-map dependence is solved with bounded iteration.
* Fuel/electrical input is not clipped at the mechanical rating. Requested shaft
  demand above the rating is exposed through ``power_deficit_kw``; a requested
  trace is not silently turned into a feasible trace.
* Combustion auxiliaries include engine conversion losses. Battery auxiliaries
  bypass traction-motor efficiency. Fuel-cell auxiliaries include fuel-cell
  conversion. Explicit public efficiency overrides take precedence over maps.
* Hybrid motor peak power can be specified independently of combined system
  power. Recovered electricity is converted to reusable propulsion with explicit
  storage and electric-drive losses, rather than cancelled efficiency factors.
* For positive battery-terminal demand D and recovered generator DC R, stored
  energy decreases by D / eta_discharge - R * eta_charge. Range uses this stored
  energy. Charging electricity additionally accounts for battery-charge and
  charger conversion; net terminal DC (D - R) is reported separately.
* Custom speed/gradient arrays are accepted through the public model API,
  validated and copied. Every custom-cycle sample counts as operating time.
  Supplied numeric gradients use degrees. Bundled gradients are rise/run,
  converted with ``arctan``. Source-matched VECTO speed/grade pairs and recorded
  durations cover all six bus classes and six truck sizes on three duty cycles;
  the 32 t truck trace retains its unverified legacy duration.
* CNG efficiency corrections affect fuel input before consumption is integrated.
  Availability masks apply consistently to reported energy. A masked zero is not
  a physical consumption estimate.

Adopted assumptions and calibration
-----------------------------------

The four vehicle packages include tabulated 2025 records. Battery one-way
charge/discharge efficiencies use sqrt(0.97); motor/inverter, electric
transmission and charger assumptions are 0.90, 0.97 and 0.90 in their documented
scopes. These component assumptions are not independently identified by aggregate
consumption. Generic hybrid motor/system peak ratios are likewise assumptions.

The **8.3 kW base auxiliary prior for 13 m city BEVs** transfers a conditional
Gillig fit to depot, opportunity and in-motion charging buses. OCBC and HD-UDDS
informed the fit; Manhattan was held out. Cabin HVAC was off in the documented
setup. Triangular bounds of 6.225–10.375 kW retain engineering uncertainty,
not a confidence interval estimated from multiple buses. The held-out cycle
is not an independent vehicle, and the auxiliaries-off BYD tests cannot
validate this auxiliary transfer. See :doc:`energy_measurements` for the
conditional-fit versus generic-rating distinction.

The subsequent :doc:`temporal_energy` update preserves every 2025 scalar and
uncertainty distribution, extends component definitions consistently across
years, rebases storage/charger loss trends, and carries the bus auxiliary prior
from 2020 onward with shared temporal uncertainty. Original affected records
are archived in each package's ``temporal_energy_provenance.json``. Historical
and future inputs changed deliberately; they are no longer all unchanged legacy
records.

Evidence and remaining limits
-----------------------------

The final measurement snapshot contains 40 runs and 41 paired observations;
77 observations remain excluded with documented reasons. All 40 runs reproduce
their energy and mass outputs after the temporal update. These observations
include mismatched cycles, historical vehicles and unresolved meter boundaries,
so the count must not be presented as 41 independent successful validations.

* :doc:`adac_cycle_comparison`: approximate graph reconstruction, not an official
  numerical ADAC trace or a new mini-BEV efficiency fit.
* :doc:`truck_energy_diagnostics`: source road loads improve the Smith comparison;
  historical diesel and heavy-BEV route/boundary discrepancies remain.
* :doc:`petrol_car_energy_diagnostics` and :doc:`combustion_controls`: opt-in
  conventional petrol controls conserve energy but remain engineering rules,
  not a calibrated Golf controller or a generic class-default adjustment.

Time-resolved hybrid control, vehicle-specific road loads, temperature-dependent
battery behavior outside the supported bus HVAC path, and better cycle/gradient
provenance remain limitations. The 32 t truck VECTO trace is explicitly unverified.
Passing model and LCA tests does not close these empirical evidence gaps.

Verification and investigation record
-------------------------------------

The temporal audit completes 546 annual cases across 21 configurations; the
original inconsistent inputs caused 20 sizing failures in that grid. The family
artifact run passed 436 tests with one existing expected two-wheeler failure,
plus offline wheel/source-distribution model and LCIA checks. See
:doc:`temporal_energy` for the saved verification report and exact scope.

The original investigation is retained separately so intermediate values and
pending-work statements cannot be mistaken for current defaults:

.. toctree::
   :maxdepth: 1

   energy_model_repairs_history
