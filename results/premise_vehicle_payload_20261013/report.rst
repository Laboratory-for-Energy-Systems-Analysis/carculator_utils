BEV truck payload at fixed capacity utilization
===============================================

The lighter future battery now increases carried cargo at unchanged 2020 payload
utilization. This implements the user's requested weight-capacity policy for BEV
trucks. Gross mass, driver mass, non-battery hardware and lifetime kilometres
retain their reference values. Cars and PHEV trucks retain their actual loads.

Available payload equals gross mass minus curb mass minus driver mass. The
baseline cargo / available-payload ratio is applied to the new available
payload. Every non-production exchange in the transport service is multiplied
by baseline cargo / new cargo. Truck manufacture per tkm therefore remains
1 / (lifetime vehicle-km times cargo tonnes). The service output is unchanged;
manufacturing one truck is not itself divided by cargo.

Electricity per tonne-kilometre
-------------------------------

Electricity per tkm equals electricity per vehicle-km divided by cargo tonnes.
The IAM-derived electricity per vehicle-km is retained; carrying more cargo
divides this same energy by more tonne-kilometres. Battery capacity, chemistry,
physical pack mass and replacement count are unchanged from the preceding
constant-range implementation. No additional load-dependent driving-energy
calculation is introduced. In particular, the lower per-tkm electricity is
not fed back into battery sizing on a repeated transformation.

This is a transparent accounting approximation: the IAM trend is interpreted
at the original load, with this explicit fixed-utilization benefit added.
It does not establish that every IAM independently projects that payload gain,
nor simulate cargo-volume constraints or new power/thermal requirements.
Road construction and wear do use the new loaded driving mass, including the
extra cargo, before their per-tkm normalization. The dataset comment and
``premise vehicle battery sizing`` fields record the new cargo and utilization.

2050 EUR examples
-----------------

REMIND SSP2-NPi, ecoinvent 3.12 cutoff, 400 km design range:

.. list-table:: Cargo and additional normalization relative to the previous fixed-load design
   :header-rows: 1

   * - Gross mass
     - 2020 cargo (t)
     - 2050 cargo (t)
     - Utilization
     - Truck input / tkm change
   * - 3.5 t
     - 0.750
     - 0.912
     - 77.7%
     - -17.74%
   * - 7.5 t
     - 1.750
     - 1.951
     - 63.6%
     - -10.31%
   * - 18 t
     - 3.200
     - 3.416
     - 41.6%
     - -6.32%
   * - 26 t
     - 6.300
     - 6.628
     - 52.0%
     - -4.96%
   * - 40 t
     - 10.300
     - 10.688
     - 45.2%
     - -3.63%

For the 40 t truck the battery is 857.57 kg lighter than in 2020. At 45.2%
utilization, actual cargo increases by 387.68 kg. Loaded driving mass is
27,046.03 kg, versus 27,515.92 kg in 2020. The 440.692 kWh nominal battery and
400 km range are unchanged from the preceding future design. The table's
reductions apply to truck units and other distance-based burdens; mass-dependent
road and wear exchanges also reflect the corrected loaded mass.

Verification
------------

276 focused tests pass, including 53 battery-sizing tests. New cases cover
partial/full utilization, smaller/larger packs, gross-mass feasibility,
per-tkm purchases, uncertainty scaling, compact exchanges, non-unit service
output, loaded wear, range conservation, exact repeatability and unchanged 2020.

Complete encrypted-IAM builds cover 2020, 2030 and 2050. Each checks all 65
regional BEV truck services. Independent checks reconstruct payload, mass,
per-vehicle-km electricity, range and lifetime truck purchases. Comparing every
inventory exchange against the preceding constant-load builds explains all
differences: zero changes in 2020 and 585 changes in each future build. All
per-vehicle manufacturing inventories and other vehicle service inventories
retain their preceding exchange quantities. There are zero validation errors;
warning identities/counts are unchanged (401, 427 and 460 respectively).

The complete car/truck battery and payload step takes 0.042, 0.054 and 0.053
seconds in the three builds. Total builds take approximately 100--105 seconds.
No carculator runtime, driving-cycle simulation or iterative solver is added.

Reproducibility
---------------

``build_2020.json``, ``build_2030.json`` and ``build_2050.json`` record the
unchanged workbook/encrypted-IAM hashes, current source hashes, private inventory
hashes and timings. ``verification_summary.json`` records the checks and test
counts. ``verification_sources.json`` identifies the audit/test sources.
``vehicle_designs.csv`` contains all 195 year/region/design rows and
``inventory_changes.csv`` all 1,170 changed coefficients. Full inventories and
validation reports stay local; no persistent user Brightway database was written.

Build command, repeated for each year:

.. code-block:: bash

   /private/tmp/premise-metals-venv/bin/python dev/build_premise_vehicle_battery.py \
     --year 2050 --workspace /private/tmp/premise-vehicle-payload-20261013 \
     --output results/premise_vehicle_payload_20261013
   /private/tmp/premise-metals-venv/bin/python dev/audit_premise_vehicle_payload.py

The preceding comparison is ``../premise_vehicle_battery_simple_20261013``;
the build script also retains the earlier IAM-restoration provenance checks.
The existing baseline workbooks needed no changes for this payload policy.
