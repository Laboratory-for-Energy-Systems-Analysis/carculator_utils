PHEV installed battery capacity correction
==========================================

13 October 2026. Remediation-plan step 5; replacement-count accounting is next.

Outcome
-------

The shared PHEV aggregation now retains the full electric-mode nominal battery
capacity and cell mass share along with the already retained pack, cell and
balance-of-pack masses. Electric driving share still weights operation. Electric
range now uses nominal capacity times depth of discharge rather than nominal
capacity alone. No emission factors, driving shares, physical masses, fuel
consumption, electricity consumption or battery replacement counts were changed.

All 16 PHEV car production templates now purchase their full nominal capacity.
Purchases increase 19.0--36.1% relative to the previously understated quantity
(the previous deficit was 16.0--26.5% of the physical pack). For the Medium car,
127.4 kg of cells at 0.24 kWh/kg gives **30.576 kWh**, replacing 23.894781 kWh.
Both gasoline and diesel variants use this same capacity. No hard-coded capacity
was substituted: the model retains its sized electric-mode hardware.

The truck adapter previously recovered capacity from full pack mass. It now
uses the corrected model field, with independent mass/density checks, as the car
adapter does. Truck purchases are numerically unchanged within float32 rounding.
For the 40 t PHEV, the model now reports **77.323265 kWh** rather than its
usage-weighted 11.598490 kWh. The existing 0.323333 replacement count still yields
102.324451 lifetime kWh purchased; its scientific interpretation remains step 6.
The two mode ranges remain 60 km electric and 400 km combustion; their combined
full-charge/full-tank range is now 460 km, rather than 411.25 km.

The 162 car and 127 truck dataset identities, including names, products, units
and geographies, are preserved. Capacity markets include manufacture and end of
life, so the adapters continue to remove both mass-based pack purchases and
separate pack disposal. Noise stays in the companion files.

Cost consistency
----------------

An existing battery-price regression failed after the initial capacity fix:
purchase costs still priced the smaller, usage-weighted pack. Cars and trucks
now price the full electric-mode nominal capacity in both intermediate cost
calculations. The existing subclass formulas then propagate that purchase cost
through financing and, for trucks, insurance and residual credit. Operating
energy and charging costs retain their usage weighting. Mode-specific unit
prices, markup and explicit cost overrides keep their existing conventions.

This change does not respecify other PHEV components or reconcile all differences
between mode-specific vehicle masses. Coherent future resizing remains step 8.

Verification
------------

Six new shared-model regression cases exercise car and truck PHEVs at electric
shares 0, 0.5 and 1, with reordered years and two labelled samples. They verify
physical capacity, cell/pack mass balance, usable range, battery price and
unchanged usage weighting of operation. All six failed before the correction.
Four new Premise checks inspect every installed PHEV template and its physical
capacity, lifetime purchase and absence of duplicate disposal.

The final focused test commands passed:

* Shared capacity, battery costs, charging costs, repeated runs and cost-label
  alignment: 102 tests.
* Car inputs/components: 13 tests; car battery costs: 3 tests.
* Truck inputs/components/charger inventory/depot throughput: 54 tests;
  cost defaults, infrastructure finance and AdBlue: 43 tests.
* Premise battery-capacity, hydrogen, fuel-carbon and car integration: 49 tests.

These six runs total 264 passing tests. Premise reported two existing dependency
warnings. Earlier shared inventory/export/LCIA and base-contract checks also
passed; their run exposed the cost regression described above, subsequently
fixed and rerun. Real inventory checks covered the bus and two-wheeler siblings,
whose models do not call the PHEV aggregation method.

Fresh car/truck exports from the final cost-corrected models exactly reproduce
the physical parameters, noise, comments and inventory coefficients installed
before the cost correction. The reproduction record captures final source hashes.
Exact ecoinvent 3.12 supplier checks find no missing links in either catalogue.

Full builds use REMIND SSP2-NPi and ecoinvent 3.12 cutoff, in isolated temporary
Brightway storage. The persistent user databases were not written.

.. list-table:: Completed scenario checks
   :header-rows: 1

   * - Year
     - Activities
     - Validation errors
     - Existing warnings
     - Fuel/CO2 checks
     - H2 checks
   * - 2020
     - 42,564
     - 0
     - 401
     - 495
     - 147
   * - 2050
     - 42,574
     - 0
     - 398
     - 495
     - 147

Warning identities are unchanged from the hydrogen-correction builds. In both
years, all material numerical differences are the 16 corrected car production
battery purchases, which match the independently checked workbook quantities.
Smaller floating-point differences are counted and bounded in the verification
summary (comparison tolerance 1e-6 relative, 1e-12 absolute). All operating fuel,
electricity and emissions remain numerically equivalent within that tolerance.

Reproduction and records
------------------------

``dev/regenerate_premise_cars.py`` and ``dev/regenerate_premise_trucks.py`` were
run without ``--reuse-raw`` under Python 3.12.13 / NumPy 1.26.4 with matching
sibling source checkouts. Both reject an inconsistent PHEV physical pack.
The guarded installer saves private rollback copies and verifies both families
before replacing either workbook. The build and audit scripts are
``dev/build_premise_vehicle_phev.py`` and ``dev/audit_premise_vehicle_phev.py``.

Companion records:

* ``workbook_installation.json``: input/output hashes and private rollback paths.
* ``car_battery_capacity_changes.csv`` and
  ``scenario_battery_capacity_changes.csv``: all changed capacity purchases.
* ``build_2020.json`` and ``build_2050.json``: build settings, source/IAM hashes,
  installed workbook hashes, validation counts and private inventory locations.
* ``verification_summary.json``: scenario audit counts and numerical bounds.
* ``final_model_reproduction.json``: fresh final-model replay and source hashes.

Raw exports and full background inventories remain private temporary artifacts.
The complete old/new EF 3.1 comparison remains planned after the remaining
replacement, hybrid-storage and future-sizing corrections; this report does
not claim that those open issues are resolved.
