Constant-range batteries with negligible runtime cost
=====================================================

The user requested a practical update without runtime vehicle simulations or
complex sizing. Premise now uses closed-form battery accounting. The new step
took 0.043--0.051 seconds across all regional car and truck services in three
full builds, below 0.06% of their 98--103 second total build times. This measures
the sizing step itself, including production cloning and provider-index updates;
it is not a claim of literally zero cost or a controlled benchmark of every
downstream effect of the additional activities.

There is no runtime carculator dependency, driving-cycle simulation, engineering
optimization or convergence loop. Native model calculations occur once during
inventory generation to save baseline specifications and wear relationships.

Accounting rule
----------------

Let ``f`` be final grid electricity per service divided by its 2020 value.
The updated nominal capacity is ``C2020 * f``. Updated pack mass is
``M2020 * f * density2020 / density(year)``. Curb and driving mass change by the
pack-mass difference. Premise supplies the approved density projection for the
original chemistry; NMC-622 is 0.24 kWh/kg cell in 2020 and 0.26 in 2050.

The IAM energy target includes the complete efficiency improvement, including
any mass benefit. No further energy saving is applied after resizing. Other
hardware, charging efficiency, depth of discharge, cell mass fraction, payload,
annual use and lifetime retain their 2020 design. PHEVs use the electricity
ratio and retain electric-mode range and electric-driving share. The same
lifetime usage at the same range retains cycle demand; existing replacement
counts therefore remain applicable. Capacity-market purchases include the
initial pack plus replacements once, with their existing end-of-life boundary.

This is a scenario-accounting approximation. It does not reconstruct the
engineering source of IAM efficiency gains or certify pack power/thermal
feasibility. It supersedes the earlier proposal to calibrate engineering
assumptions during scenario generation.

Inventory changes and boundaries
--------------------------------

Road construction follows driving mass; car maintenance and truck assembly
follow curb mass. Wear treatments follow precomputed native mass powers,
including the original cycle shares, PHEV mode weights, recuperation credit and
the existing resuspended-dust contribution. Generation checks these condensed
relationships against the native model before saving them. Runtime uses only
the saved shares and mass powers. Baseline truck gross-weight maintenance and
disposal proxies, distance-based road maintenance, HBEFA emissions, refrigerants
and non-battery component quantities retain their original drivers.

Each changed regional vehicle links to a production activity with its original
name/product and the service's IAM location. This location describes the
regional design; existing component supplier locations remain unchanged.
Original RER production templates remain available. Battery amount comments and
structured state metadata report the actual scenario capacity, mass, lifetime
capacity and electric range. Earlier model descriptions are explicitly labelled
as the 2020 baseline. Repeating the sizing operation does not compound scaling
or create duplicate production activities.

HEV and FCEV power buffers retain their separate specifications. Fuel-tank and
hydrogen-tank range accounting is outside this battery change. Unregionalized
templates retain their 2020 hardware; this includes truck PHEVs for which the
controlled REMIND mapping does not supply regional fleet technologies. They
carry the sizing contract for use when a mapped regional service exists.
Missing IAM signals remain visible in the existing efficiency-source metadata.
No Large Car/SUV fleet proxy was introduced.

Verification
-------------

The generation adapters add sizing contracts to 25 car and 14 truck services
and their corresponding production datasets (78 activity records). Comparison
of both complete workbooks proves that all pre-existing fields, identities and
exchange amounts remain identical. This is a metadata-only workbook update.

260 focused tests pass, including 37 new cases for constant range, pack mass,
PHEV electric-mode allocation, replacement demand, density interpolation,
truck payload constraints, invalid inputs, compact exchanges, regional supplier
isolation, repeated updates, importer metadata retention and the legacy truck
battery override. Existing fuel-carbon, hydrogen compression, emission scaling,
IAM compatibility and battery-capacity tests remain included.

Full encrypted REMIND SSP2-NPi / ecoinvent 3.12 cutoff builds use an isolated
Brightway project copy. They do not write a database into the user's persistent
project. Each build contains 221 checked regional services: 143 BEVs and 78
gasoline PHEVs. Independent checks use final electricity purchases to verify
range, pack/cell mass, payload, nominal capacity and lifetime battery purchases.

.. list-table:: Full-build results
   :header-rows: 1

   * - Year
     - Additional production activities
     - Sizing time
     - Validation errors
     - Validation warnings
   * - 2020
     - 0
     - 0.043 s
     - 0
     - 401
   * - 2030
     - 221
     - 0.051 s
     - 0
     - 427
   * - 2050
     - 221
     - 0.049 s
     - 0
     - 460

Complete inventory comparisons against the preceding intensity correction show
zero material exchange changes in 2020. All 1,726 changed amounts/provider links
in the 2050 comparison are explained by the documented rule, including new
production activities compared with their original RER recipes. Operating
energy and direct biosphere emissions are unchanged throughout the database.
The previously verified fuel-carbon and hydrogen-compression balances therefore
remain unchanged. Warning identities/counts in 2020 and 2050 are also unchanged.
The 2030 run checks physical/accounting identities; there is no preceding 2030
database for an inventory-difference comparison.

.. list-table:: EUR examples in 2050
   :header-rows: 1

   * - Vehicle
     - 2020 nominal capacity
     - 2050 nominal capacity
     - 2050 pack mass
     - Retained electric range
   * - Medium BEV car
     - 67.20 kWh
     - 54.54 kWh
     - 299.68 kg
     - 344.49 km
   * - Medium gasoline PHEV car
     - 30.58 kWh
     - 24.46 kWh
     - 134.40 kg
     - 155.23 km
   * - 40 t Regional-delivery BEV truck
     - 550.86 kWh
     - 440.69 kWh
     - 2,421.38 kg
     - 400.00 km

The PHEV range is the inherited electric-mode design, not total hybrid range
or a new market-representativeness claim.

Reproduction and commits
-------------------------

Premise commits are ``5dde5ee`` (metadata-only workbooks) and ``50a1052``
(closed-form transformation, documentation and regressions). The two generation
adapters call ``dev/premise_vehicle_battery_metadata.py``. Installation refuses
any change to a pre-existing workbook field or exchange.

``dev/build_premise_vehicle_battery.py`` captures complete source/workbook hashes
and times the new step. ``dev/audit_premise_vehicle_battery.py`` independently
checks final databases and explains their differences. ``verification_sources.json``
records all scripts and the 260-test JUnit result. The final runtime source
hashes match all three builds. Source generation logs, complete inventories,
validation dumps and original workbook backups remain private/untracked under
``/private/tmp/premise-vehicle-battery-simple-20261013`` and the local result
directory. Committed report artifacts contain specifications, hashes and
aggregate diagnostics rather than complete background inventories.
