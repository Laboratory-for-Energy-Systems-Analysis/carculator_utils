FCEV buffer power and pack accounting
=====================================

14 October 2026. This isolates the FCEV accounting correction from the
preceding hybrid petrol-mapping correction. It is not the final old-versus-new
vehicle EF 3.1 comparison requested for the end of the exercise.

Correction and scope
--------------------

The source parameter defines fuel-cell share as the fraction of total vehicle
power supplied by the fuel cell. The model's stack rating includes its own
consumption. The former battery formula multiplied that gross rating by the
complementary share, applying the share twice and leaving a net-power gap.
The corrected nominal allocation is::

    gross stack kW = vehicle kW * fuel-cell share * gross/net multiplier
    buffer kW = vehicle kW * (1 - fuel-cell share)
    gross stack kW / gross/net multiplier + buffer kW = vehicle kW

For the power-sized car buffer, cell mass is buffer power divided by cell
specific power. The declared cell fraction describes cell mass divided by
complete pack mass. Pack mass is therefore cell mass divided by that fraction,
with balance-of-pack mass equal to the difference. Multiplying cell mass by
one minus its fraction previously understated the balance of pack.

The starter-battery helper no longer overwrites FCEV traction power with zero.
Combustion starter sizing retains its existing convention. The truck HEV's
separate traction buffer and starter are preserved. The shared fix also applies
to bus model calculations; the Premise bus workbook is not refreshed here.

Observed 2020 specifications
--------------------------------

.. list-table:: Medium car and 40 t Regional-delivery truck
   :header-rows: 1
   :widths: 45 25 15 15

   * - Vehicle
     - Quantity
     - Before
     - After
   * - Medium FCEV car
     - Buffer power, kW
     - 29.878
     - 34.867
   * - Medium FCEV car
     - Nominal capacity, kWh
     - 3.366
     - 3.928
   * - Medium FCEV car
     - Pack mass, kg
     - 18.232
     - 23.380
   * - Medium FCEV car
     - Curb mass, kg
     - 1736.976
     - 1743.372
   * - Medium FCEV car
     - Hydrogen energy, kJ/km
     - 1049.574
     - 1051.411
   * - 40 t FCEV truck
     - Buffer power, kW
     - 0
     - 218.016
   * - 40 t FCEV truck
     - Nominal capacity, kWh
     - 71.101
     - 71.101
   * - 40 t FCEV truck
     - Pack mass, kg
     - 423.219
     - 423.219

Across eight car sizes, capacity rises 16.57--16.70% and pack mass rises
28.10--28.24%. Coupled hydrogen demand rises only 0.088--0.182% because these
buffers are a small part of vehicle mass. All seven trucks retain their
capacity, pack mass and operating consumption. Their recorded traction power
now represents the model requirement. ``model_changes.csv`` records every
FCEV change and the audit checks that the selected physical fields of other
powertrains are unchanged.

Fresh exports preserve 162 car and 127 truck activity identities. Coefficient
changes are restricted to eight FCEV car services and eight production
datasets. Every truck coefficient is unchanged at relative tolerance 1e-12
and absolute tolerance 1e-18. Power fields, provenance and explicit limitations
are included in dataset metadata and parameter companions. Initial and
replacement battery capacity still passes through Premise's MIX kWh market.

Interpretation limits
---------------------

The truck and bus energy-sizing rule remains 20 kWh **plus** 6% of hydrogen
chemical energy. No new cell technology or buffer-sizing rule is introduced.
The truck's inherited 0.15 kW/kg input describes lead-acid starters; it is not
a validated lithium-ion traction rating and does not determine the final
energy-sized FCEV pack. Correcting the recorded power does not verify peak
cell discharge capability, independent motor/inverter peak losses, or sustained
cycle power delivery. These limitations appear in the truck dataset comments.
Default truck FCEV buffer price inputs remain zero; no unapproved price proxy
has been introduced. A regression confirms that a supplied price uses the
corrected nonzero power requirement. Costs do not enter these LCA exchanges.

Future FCEV buffers and hydrogen tanks retain the baseline design under the
existing policy. The correction introduces no additional Premise runtime
calculation. No hot-emission factors, fuel-blend assumptions, compression
pressure, PHEV packs or HEV design assumptions are changed.

Sources and reproducibility
---------------------------

The intent follows the existing ``fuel cell power share`` parameter description
and ``set_fuel_cell_power`` equation, not a new empirical calibration. Shared
code and regression commit: ``d19bf76``. Car documentation/regression:
``dc7d1ab``. Truck regression: ``c075a6f``. Bus regression: ``305f4b3``.
Premise inventory, provenance and regression update: ``caa9ff1``.

Run ``dev/regenerate_premise_cars.py`` and
``dev/regenerate_premise_trucks.py`` with matching Python 3.12 checkouts and
fresh output folders; this run did not reuse raw exports. The installation
receipt identifies workbook/companion hashes and retained backups.
``dev/audit_premise_vehicle_fcev.py`` checks native balances and bounds all
full-database coefficient changes. ``dev/audit_premise_vehicle_plausibility.py``
checks final functional units, battery purchases, scenario designs, fuel energy
and carbon against the regenerated templates. Proprietary complete inventories
remain in the private workspace.

Verification
------------

The focused model checks pass 93 tests: 72 native-family/component/hardening
checks, 15 shared buffer/base-contract checks and six adapter-provenance
checks. Small real car, truck and bus model/LCIA runs return finite nonzero
results. The focused Premise suite passes 184 tests, including the installed
FCEV power, mass, lifetime-capacity and metadata regressions. Provenance checks
were repeated successfully after retaining the earlier sidecar history.

Both full builds use encrypted REMIND SSP2-NPi, ecoinvent 3.12 cutoff and the
same Premise implementation and IAM inputs as the previous audit. Only the
identified car/truck workbooks change. The 2020 build contains 42,564 activities
and 1,358,553 exchanges; 2050 contains 42,795 activities and 1,363,087 exchanges.
Both have zero validation errors. The 401 and 468 warning identities,
respectively, are unchanged.

In each year, numerical changes are confined to 88 FCEV car activities:
10 RER activities and six services in each of 13 IAM regions. The RER total
includes eight production activities and two directly operating services;
the other six RER services become forwarders. All other exchange coefficients
are unchanged at relative tolerance 1e-12 and absolute tolerance 1e-18.
``scenario_changes.csv`` records the detailed changes.

Per year, the independent accounting audit checks 726 operating services,
415 battery allocations, 578 fuel-energy/carbon balances and 221 scenario
battery designs; 50 forwarding services are excluded from direct-use checks.
There are no fuel-energy failures. The saved Brightway databases preserve
metadata exactly for 965 activities in 2020 and 1,186 in 2050, and verify
968 operating-energy links per year. The existing BEV climate-score smoke
checks pass. This is not a new complete EF 3.1 comparison.

The private build copies leave the user's persistent Brightway project
unchanged. The 2020 build record explicitly notes that earlier provenance
history was retained in the JSON sidecars after that build started; workbook
bytes and all build inputs remained unchanged. The final installation receipt
records the final sidecar hashes.
