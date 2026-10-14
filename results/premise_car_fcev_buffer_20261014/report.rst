FCEV passenger-car battery correction
========================================

The approved power-scaled Mirai pack proxy is implemented in carculator and
all eight FCEV car inventories have been regenerated and installed in Premise.
No new runtime calculation is added to Premise. This report isolates this
correction against the immediately preceding verified vehicle inventories.
The final original-legacy-versus-refreshed comparison remains separate.

Physical calibration
--------------------

`Toyota's manufacturer announcement of 30 November 2020
<https://newsroom.toyota.eu/introducing-the-all-new-toyota-mirai/>`_ specifies
310.8 V and 4 Ah (1.2432 kWh), a complete pack mass of 44.6 kg, and 31.5 kW
discharge for ten seconds. The model scales nominal capacity and mass together
with required buffer power inside its existing vehicle mass/power iteration.
This retains the electrical allocation between the fuel cell and battery,
including motor losses and auxiliaries. Explicit capacity overrides retain
their capacity and must supply the required ten-second buffer power.

.. list-table::
   :header-rows: 1

   * - Car
     - Before kWh
     - After kWh
     - Before kg
     - After kg
     - Hydrogen use
   * - Mini
     - 1.84
     - 0.66
     - 11.0
     - 23.5
     - +0.52%
   * - Small
     - 2.62
     - 0.93
     - 15.6
     - 33.5
     - +0.71%
   * - Lower medium
     - 3.30
     - 1.18
     - 19.7
     - 42.3
     - +0.80%
   * - Medium
     - 4.46
     - 1.60
     - 26.6
     - 57.3
     - +1.05%
   * - Large
     - 5.11
     - 1.83
     - 30.4
     - 65.6
     - +1.09%
   * - Medium SUV
     - 3.77
     - 1.35
     - 22.5
     - 48.4
     - +0.79%
   * - Large SUV
     - 5.63
     - 2.01
     - 33.5
     - 72.2
     - +0.99%
   * - Van
     - 3.72
     - 1.32
     - 22.1
     - 47.5
     - +0.57%

Values use the 2020 defaults, WLTC and Swiss climate. Medium hydrogen use rises
from 0.88456 to 0.89386 kg/100 km, about 1.05%. No battery-specific charging
limit has been inferred from the discharge rating. Native future model years
retain the reference ratios; pre-2020 model inputs are unchanged.

Premise representation
----------------------

All 162 workbook identities are preserved. Substantive coefficient changes
affect eight services and eight manufacturing datasets. In each full scenario,
88 activities change: eight RER manufacturing datasets, two unmatched RER
services and six operating services in each of thirteen IAM regions. The
remaining RER services are unchanged forwarders.

The full-grid float32 calculation takes ten sizing iterations instead of nine.
It also shifts 185 non-FCEV workbook exchanges by at most 0.00002322%; these
last-place numerical changes are recorded in ``non_fcev_roundoff.csv``. An
independent rerun using the preceding pack hook reproduces this effect. No
model convergence tolerance was relaxed. There are 700/705 such exchanges in
the full 2020/2050 scenarios; no other non-FCEV coefficient changes were found.

All packs retain the MIX capacity market per nominal kWh, including replacements.
The physical pack is 35.88 kg/kWh. No mass-equivalence correction is applied to
the ordinary capacity market, as explicitly requested. The lower kWh purchase
therefore does not establish lower manufacturing burdens for a real high-power
pack. Comments and structured provenance disclose this mismatch, the Toyota
source, power duration, original model/publication and the retained cell-mass,
chemistry and cost proxies. Noise remains in the companion audit file.

All eight FCEV production recipes retain their corrected 2020 battery, motor,
inverter and fuel-cell quantities in 2050. Scenario efficiency changes operating
fuel demand. Hydrogen and 30-to-700-bar compression electricity remain correctly
linked to regional supplies and scale together. Fuel-energy/carbon and capacity
allocation checks pass across cars and trucks in both full scenarios.

Incremental EF 3.1 comparison
--------------------------------

Both private databases use 2020 REMIND SSP2-NPi and ecoinvent 3.12 cutoff. The
functional unit is one vehicle-kilometre. All eight RER FCEV services and six EUR
services are compared across sixteen EF 3.1 headline indicators, giving
224 paired scores. The table selects EUR where matched and RER otherwise.

.. list-table::
   :header-rows: 1

   * - Car
     - Location
     - Climate change
     - Largest absolute change
     - Change
   * - Mini
     - EUR
     - +0.00%
     - human toxicity: carcinogenic
     - -1.98%
   * - Small
     - EUR
     - +0.03%
     - human toxicity: carcinogenic
     - -2.12%
   * - Lower medium
     - RER
     - +0.06%
     - human toxicity: carcinogenic
     - -2.28%
   * - Medium
     - EUR
     - +0.15%
     - human toxicity: carcinogenic
     - -2.51%
   * - Large
     - EUR
     - +0.15%
     - human toxicity: carcinogenic
     - -2.55%
   * - Medium SUV
     - EUR
     - +0.09%
     - human toxicity: carcinogenic
     - -2.37%
   * - Large SUV
     - RER
     - +0.10%
     - human toxicity: carcinogenic
     - -2.49%
   * - Van
     - EUR
     - +0.02%
     - human toxicity: carcinogenic
     - -2.17%

Across all pairs, changes span -2.55% to +1.22%. Detailed scores
are in ``incremental_ef31.csv``. The largest indicator change and climate change
for each class are independently reconciled through an adjoint matrix solve
and exchange contributions in ``incremental_ef31_contributions.csv``. Nested
manufacturing contributions must not be added to vehicle production twice.

The contribution analysis also checks the largest increase. It identifies:

* Large EUR carcinogenic toxicity falls 2.55%. The lower MIX battery-capacity
  purchase accounts for 131% of the net reduction, partly offset by larger
  fuel-cell/motor components and operating burdens. This is fully explained by
  the retained capacity-market proxy, but it is **not an independently justified
  manufacturing improvement** for the physically heavier pack.
* Large EUR land use rises 1.22%. The model's mass-dependent road input accounts
  for 118% of the increase, partly offset by lower battery-capacity burdens.
* Medium EUR climate impact rises from 0.232464 to 0.232814 kg CO2-eq/km
  (+0.150%). Battery manufacture falls by 1.876 g CO2-eq/km in the capacity proxy,
  offsetting additional hydrogen, compression, roads and component manufacture.
  The small net climate change therefore conceals larger opposing contributions.

No unexplained numerical residual was found. The battery-manufacturing
decreases remain a disclosed modelling limitation under the approved MIX
market treatment; this calibration does not validate the underlying supply
chain or its impact factors.

Verification
------------

* 57 car model/input/component/inventory/export checks pass, including the new
  paired-pack, explicit-capacity, custom-profile, historical/future, labelled-
  sample and repeat-run regressions. The earlier power-allocation test remains.
* 13 adapter/provenance checks pass, including stale generic-pack rejection.
* 91 Premise tests pass; one existing fixture-specific test is skipped.
* Wheel/sdist resource checks and offline core-only smoke checks pass for
  carculator and utils. A separate FCEV native EF case gives identical pack,
  fuel use and finite results from wheel and sdist installations. Full installed
  test suites were not rerun.
* Eight native car cases reproduce the installed packs and independently balance
  mass, generator/auxiliary/storage energy, fuel energy and electrical power.
* Full 2020/2050 builds contain 42,564/42,795 activities and have zero errors.
  Existing 401/468 warning identities are unchanged.
* In each year, 726 operating services, 415 battery allocations, 578 fuel-energy/
  carbon balances and 221 resized batteries pass the generic accounting audit.
* Saved metadata matches for 965/1,186 activities; 968 operating-energy links
  pass in each database. Existing user Brightway projects were not modified.

Limits and reproducibility
--------------------------

This is an approved class proxy, not validation of a complete FCEV design.
Ten-second discharge does not establish continuous discharge, charging, SOC,
temperature or ageing limits. Charging remains unconstrained and the cycle
calculation assumes instantaneous fuel-cell response. No new charging envelope,
fuel-cell ramp controller or replacement-life assumption is introduced.

Source/model commit: carculator ``ead57b3``. Adapter/provenance commit: utils
``201fbf7``. Installed inventories and tests: Premise ``93925f9``. Generation
metadata records source file hashes, including then-uncommitted changes that
are present in these commits. The shared runtime and truck model are unchanged.

The private workspace is ``/private/tmp/premise-car-fcev-buffer-20261014``.
Scripts in ``dev/`` are ``regenerate_premise_cars.py``,
``install_premise_car_fcev_buffer.py``, ``build_premise_car_fcev_buffer.py``,
``audit_premise_car_fcev_buffer.py``, ``verify_car_fcev_buffer_model.py``,
``verify_car_fcev_buffer_hardware.py``, ``save_premise_car_fcev_buffer.py``,
``compare_premise_car_fcev_buffer.py`` and ``explain_premise_car_fcev_buffer.py``.
The generic plausibility audit writes ``accounting/``. Build records pin IAM,
workbook and Premise code hashes. The skipped PHEV cycling review remains skipped.
