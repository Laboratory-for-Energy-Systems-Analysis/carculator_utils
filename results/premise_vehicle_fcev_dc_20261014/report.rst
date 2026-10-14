FCEV electrical sizing correction
=================================

14 October 2026. The user approved preserving the fuel-cell/battery split on
the electrical side after the
`power audit <../premise_vehicle_fcev_power_20261014/report.html>`_. This report
compares the correction with the preceding verified PHEV-calibrated database,
not with the original legacy vehicle inventories.

Shared implementation
----------------------

``carculator_utils.model.VehicleModel`` now uses::

    DC requirement = motor shaft kW / motor-inverter efficiency + auxiliary kW
    net fuel-cell kW = DC requirement * original fuel-cell share
    buffer kW = DC requirement * (1 - original fuel-cell share)
    gross stack kW = net fuel-cell kW * original gross/net multiplier

The existing motor/inverter conversion input is used once. Explicit efficiency
overrides have priority, including per-sample values; legacy arrays without a
fixed input use the existing efficiency map at rated shaft load. Transmission
losses do not enter this conversion of shaft rating to electrical supply.
Stack own consumption is included once in its gross rating.

The car loop already computes auxiliaries before these shared methods. Trucks
now do so too. The bus hook adds the same climate-dependent HVAC and battery
conditioning as its energy calculation. Tests cover Swiss climate and ambient
overrides of -10 and 35 degrees Celsius. These are the existing model
assumptions, not a newly established extreme-weather envelope.

Native bounded sizing loops propagate component mass changes through the
vehicle, motor rating, energy and inventories. No Premise runtime calculation
is added. Cars retain power-sized buffers; trucks/buses retain the original
energy rule, 20 kWh plus 6% of stored hydrogen chemical energy. No new chemistry,
battery lifetime, cell-power rating or cost proxy is adopted.

Observed 2020 changes
---------------------

.. list-table:: Before to corrected, including mass feedback
   :header-rows: 1

   * - Quantity
     - Medium car
     - 40 t Regional-delivery truck
   * - Gross fuel-cell rating, kW
     - 119.951 → 136.286
     - 83.573 → 94.679
   * - Buffer requirement, kW
     - 34.867 → 39.615
     - 218.016 → 246.988
   * - Nominal capacity, kWh
     - 3.928 → 4.463
     - 71.101 → 71.144
   * - Complete pack mass, kg
     - 23.380 → 26.564
     - 423.219 → 423.475
   * - Curb mass, kg
     - 1743.372 → 1778.372
     - 14534.390 → 14571.782
   * - Hydrogen energy, kJ/km
     - 1051.411 → 1061.467
     - 7665.117 → 7671.576

Medium-car hydrogen demand rises 0.956%; the 40 t truck rises 0.0843%. The car
buffer increases 13.62% after mass feedback, while truck capacity increases
only 0.0606%. The inherited truck lead-acid starter power density is not used
to validate the final lithium-ion pack. ``model_changes.csv`` covers every
changed recorded parameter. ``power/power_screen.csv`` checks all eight car
and seven truck templates; supply balances close within 2.6e-5 kW, consistent
with float32 storage.

Premise propagation
--------------------

Fresh exports retain all 162 car and 127 truck activity identities. Changed
coefficients are confined to eight car services/eight production datasets and
seven truck services/seven production datasets. All other vehicle coefficients
are unchanged at relative tolerance 1e-12 and absolute tolerance 1e-18.
Parameter companions now include motor efficiency and auxiliary demand in
watts. Comments distinguish shaft output, net electrical allocation and gross
stack rating. Publications, original model names, source hashes and provenance
history are retained. Traction batteries still use Premise's MIX capacity market
with the existing replacement counts.

Full builds use encrypted REMIND SSP2-NPi and ecoinvent 3.12 cutoff, with the
same Premise implementation, IAM data, transport mappings and fuel properties.
Only the two vehicle workbooks change. Both builds have zero validation errors
and unchanged warning identities: 401 in 2020 and 468 in 2050. Numerical
changes are confined to 162 FCEV activities per year: 19 RER activities and
11 activities in each of 13 IAM regions. All other exchange coefficients are
unchanged at the tolerances above.

Per year, independent accounting passes for 726 operating services, 415
battery allocations, 578 fuel-energy/carbon balances and 221 BEV/PHEV battery
designs. There are no fuel-energy failures. Saved Brightway readback preserves
metadata exactly for 965 activities in 2020 and 1,186 in 2050, and verifies
968 operating-energy links per year. The existing BEV LCIA smoke cases pass.
Complete inventories and database writes stay in the private workspace; the
persistent user project is unchanged.

The 102 focused shared/native-model/adapter tests pass. They cover labelled
samples, efficiency overrides, legacy map fallback, DC demand independently
recovered from cycle energy, pack accounting and bus HVAC. The focused Premise
suite passes 119 tests with one existing skip. Small real car, truck and bus
model/LCIA cases are finite and nonzero for 2020 and native 2050. Those native
2050 cases differ from Premise's future policy: Premise retains corrected
2020 FCEV hardware while applying IAM efficiency and energy-supply changes.

Incremental EF 3.1 results
--------------------------

The controlled 2020 comparison covers all 15 RER FCEV services and their
11 EUR regionalized counterparts, with 16 headline EF 3.1 indicators:
416 paired scores. Cars use one vehicle-kilometre; trucks use one tonne-kilometre.
All changes are positive. Car climate scores rise 1.41--2.39%; truck climate
scores rise 0.244--0.378%. Across all indicators, car changes range from
1.08--8.45% and truck changes from 0.164--2.81%. The largest is acidification
for the Large car, +8.45%; the largest truck change is also acidification,
for 26 t, +2.81%.

The contribution check attributes 94.44% of the Large car's acidification
increase and 97.28% of the 26 t truck's increase to fuel-cell stack and balance-
of-plant manufacture. The increases therefore follow the larger required
fuel-cell ratings, rather than an unexplained change in hydrogen supply.

``incremental_ef31.csv`` contains all paired scores. The contribution audit
independently solves the transposed technosphere system, checks agreement
with vehicle scores, and decomposes direct inputs and vehicle manufacture.
Manufacturing rows are a separate decomposition of the production input and
must not be added to the top-level contributions. This is not the final
legacy-versus-new vehicle comparison requested for the end of the exercise.

Remaining boundaries
---------------------

This correction establishes consistent electrical requirements. It does not
certify pulse/continuous cell power, charging limits, usable SOC or fuel-cell
response. The small trucks still briefly exceed their motor ratings by about
2.75 kW for 3.5 t and 13.21 kW for 7.5 t on Regional delivery. Those ratings
and the joint buffer mass/energy/power calibration remain separate follow-ups.
The PHEV cycling review remains skipped. Bus models inherit and test the
correction; the legacy Premise bus workbook is not regenerated in this step.

Reproducibility and commits
----------------------------

Shared implementation/adapters/regressions: ``0160a64``. Car regression:
``c6e0010``. Truck ordering/regression: ``3624270``. Bus HVAC/regressions:
``9d175a0``. Premise workbooks/installed-template regression: ``8fc0975``.

Use matching Python 3.12 sources with ``dev/regenerate_premise_cars.py`` and
``dev/regenerate_premise_trucks.py``, then
``dev/install_premise_vehicle_fcev_dc.py``. The installation receipt records
hashes and backups. Build, scope-audit, accounting, saved-database and LCIA
scripts record their checks here. Private workspace:
``/private/tmp/premise-vehicle-fcev-dc-20261014``.
