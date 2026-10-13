Large Car efficiency fallback
=============================

The approved REMIND/REMIND-EU fallback now uses the same powertrain's
``Large Car and SUV`` relative energy-intensity trend when a region has neither
a usable native Large Car intensity nor a usable native energy/service pair.
Native Large Car signals take priority. The 2020 vehicle inventories, fleet
volumes, technology allocation and all existing supplier mappings are retained.
Fuel-tank resizing was separately skipped at the user's request.

Implementation and scope
------------------------

Five passenger-car entries declare ``energy_intensity_fallback_aliases`` for
REMIND and REMIND-EU: BEV, FCEV, compressed gas, gasoline PHEV and gasoline.
The same-region proxy must have MJ/vehicle-km units and a finite positive 2020
value. Its efficiency index is intensity(2020) / intensity(year). Missing
years use the existing within-series filling policy. Premise's no-deterioration
policy and default maximum index of 1.25 remain unchanged. Missing/invalid
proxy references remain explicitly unavailable; no regional curve is borrowed.

The ratio scales each original Large car's energy consumption. It does not
replace its absolute consumption, mass or other baseline specifications with
SUV values. The existing future battery accounting then responds to the
corrected energy trend, retaining that car's own electric range. Fleet-volume
aliases and exchanges are unchanged, so the donor fleet is not counted twice.

Array attributes, structured vehicle logs and dataset comments distinguish
``proxy intensity`` from ``direct intensity`` and record the actual variable,
region, 2020 reference and reason. A native signal replaces the proxy whenever
available. Repeated source recording does not duplicate the comment.

Each of the four restored REMIND cases has 40 proxy region/technology pairs:
five powertrains in CHA, EUR, IND, JPN, MEA, NEU, REF and SSA. The 25 native
Large Car pairs in CAZ, LAM, OAS, USA and World retain their original trends.
The REMIND-EU case has 100 proxy pairs and 25 native Large Car pairs. These
are conditional mappings, not a hard-coded list of regions.

Controlled results
------------------

Full builds use encrypted REMIND SSP2-NPi and ecoinvent 3.12 cutoff, compared
with the preceding BEV-truck payload correction. No workbook or encrypted
scenario file changed. No persistent user Brightway database was written.

.. list-table:: Whole-inventory verification
   :header-rows: 1

   * - Check
     - 2020
     - 2050
   * - Proxy car services
     - 40
     - 40
   * - Changed exchange coefficients
     - 0
     - 216
   * - Activities with changed coefficients
     - 0
     - 56
   * - Final fuel/CO2 checks
     - 495 passed
     - 495 passed
   * - Hydrogen/compression checks
     - 147 passed
     - 147 passed
   * - Validation errors
     - 0
     - 0
   * - Validation warnings
     - 401, unchanged
     - 468, previously 460

All exchange differences are independently explained. The 2050 changes concern
40 Large car services and their 16 BEV/PHEV production suppliers. They follow
operating energy, fuel-derived emissions, hydrogen compression, battery capacity
and the established mass-dependent maintenance/road/wear relationships.
Fleet-market coefficients, all truck inventories and unrelated exchanges stay
unchanged. Vehicle manufacture per kilometre is not scaled by fuel efficiency.

For EUR, the effective 2050 energy multiplier is now 0.8 instead of 1 for all
five affected mappings. The Large BEV battery becomes 77.952 kWh rather than
97.440 kWh while retaining its 466.17 km electric range. Its pack mass is
428.31 kg at the approved future cell density. The gasoline PHEV becomes
33.869 kWh while retaining its 194.19 km electric-only range. These are
accounting projections using the existing baseline designs, not independent
engineering forecasts or identical Large-car/SUV hardware assumptions.

The eight additional warnings are CO hot-reference screens for the gasoline
Large car in the eight proxy regions. The CO inventory is unchanged. Reduced
fuel use lowers the diagnostic's energy-based hot-reference denominator.
For EUR the inventory remains 0.000890741 kg/km; the new reference is
0.000395371 kg/km, moving the ratio from about 1.80 to 2.25. This crosses the
existing heuristic factor-of-two screen; it is not an increase in emissions
or evidence of a EURO-limit violation. ``warning_changes.json`` records each
diagnostic and explanation. No emission factor was clipped to suppress it.

Tests and reproducibility
-------------------------

291 focused tests pass. New regressions cover native direct and energy/service
priority, same-region isolation, 2020 normalization, invalid/missing proxy data,
units, gap filling, monotonicity, unchanged fleet aliases, powertrain matching
and truthful source metadata. Ten real-file model/family checks preserve
existing IMAGE, TIAM-UCL, MESSAGE, GCAM and WITCH calculations; this does not
resolve their previously recorded source-data gaps.

The four REMIND cases and one REMIND-EU case verify 4,160 proxy year cells
against independent NumPy calculations. All other 3,590 region/technology
curves retain their prior values. ``proxy_factors.csv`` contains the 260 proxy
pairs and normalized 2030/2050 factors. ``iam_verification.json`` records the
coverage, input hashes and cross-model results. The two ``build_*.json`` files
record source, mapping, workbook and encrypted-scenario hashes. The full-build
audit checks those hashes, every exchange, range and final fuel balances.

Reproduction uses Python 3.12 in the existing Premise environment:

.. code-block:: bash

   /private/tmp/premise-metals-venv/bin/python dev/audit_premise_large_car_proxy.py
   /private/tmp/premise-metals-venv/bin/python dev/build_premise_vehicle_battery.py \
     --year 2050 --workspace /private/tmp/premise-large-car-proxy-20261013 \
     --output results/premise_large_car_proxy_20261013
   /private/tmp/premise-metals-venv/bin/python dev/audit_premise_large_car_builds.py

Repeat the build command for 2020. The isolated workspace must contain the
existing private Brightway source copy and the earlier comparison inventories.
Full validation dumps and inventories remain private; aggregate checks,
differences and provenance are retained here.
