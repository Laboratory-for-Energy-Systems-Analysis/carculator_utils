# Verification after correcting grouping and truck sizing

This repeats the [original audit](../README.md) with the same eleven cases,
input choices, cycles, backgrounds, functional units and comparison tolerances.
The original results remain unchanged for comparison.

This snapshot isolates these two corrections. A separate hydrogen-compression
change was committed while the checks were running; the
[integration verification](../integration/README.md) repeats the complete
comparison with that change included and records the latest combined results.

## Corrections

Onboard chargers now belong only to `powertrain`. External chargers and
charging infrastructure belong only to `charger`. The generic activity named
`charger` uses an exact-name rule. All groups must be disjoint, and a vehicle
or transport input with no source group raises an error rather than being
omitted from the impact total.

Truck sizing now converges driving mass, available payload, energy-battery
mass, fuel mass and TtW energy together, per active cell, with relative
tolerance `1e-6`. Cargo limits participate in the iteration. The energy
calculation is refreshed at the final mass before consumption, costs and
emissions are calculated. The existing maximum-iteration bound is retained.

For the 26t hydrogen truck, final driving mass is now **17,696.34 kg** and
TtW energy is **4,873.207 kJ/km**. Repeating the energy calculation at that mass
leaves TtW energy unchanged. The complete correction changes the mass as well
as energy, so it is slightly larger than the original one-step diagnostic
(4,872.71 kJ/km at the old final mass). The target range remains 400 km within
the convergence tolerance. The independent force check now passes.

## End-to-end results

All **331 model and complete-matrix checks**, **54 cycle/physics checks**,
**3 PHEV weighting checks**, and **40 inventory/contribution checks** pass.
The same thresholds that exposed the defects are used after the corrections.

All **242 comparisons pass** for both the usual grouped calculation and the
independent matrix solve against Brightway. The largest grouped/Brightway
relative difference is **0.00000761%**.

Climate scores are kg CO2-eq per stated functional unit. All vehicles are 2025.

| Case | Vehicle | Country | Background | Unit | Grouped total | Manual solve | Brightway |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| case-01 | Car Small BEV | FR | static | pkm | 0.076385443 | 0.076385443 | 0.076385444 |
| case-02 | Car Lower medium ICEV-p | CH | static | pkm | 0.185907039 | 0.185907039 | 0.185907037 |
| case-03 | Truck 7.5t BEV | CH | static | tkm | 0.130013260 | 0.130013260 | 0.130013258 |
| case-04 | Truck 18t ICEV-d | CH | static | tkm | 0.463309053 | 0.463309061 | 0.463309053 |
| case-05 | Bus 13m-city BEV-depot | FR | static | pkm | 0.056729495 | 0.056729495 | 0.056729497 |
| case-06 | Bus 18m ICEV-d | CH | static | pkm | 0.098587012 | 0.098587012 | 0.098587011 |
| case-07 | TwoWheeler Scooter 4-11kW BEV | DE | static | pkm | 0.058935972 | 0.058935972 | 0.058935971 |
| case-08 | TwoWheeler Scooter <4kW ICEV-p | CH | static | pkm | 0.084862000 | 0.084862000 | 0.084862001 |
| case-09 | Car Lower medium PHEV-p | CH | static | vkm | 0.178974922 | 0.178974922 | 0.178974923 |
| case-10 | Truck 26t FCEV | DE | static | tkm | 0.115960354 | 0.115960357 | 0.115960356 |
| case-11 | Car Small BEV | FR | SSP2-NPi | pkm | 0.065258809 | 0.065258809 | 0.065258809 |

Evidence:

- [Model parameters and matrix comparisons](model_checks.json).
- [Physics, fuel fractions, replacements and additive contributions](physics_checks.json).
- [Brightway endpoint scores and comparisons](brightway_checks.json).
- [Climate comparison CSV](climate_comparison.csv).
- [Verification and source fingerprints](verification.json).

The three `dev/audit_pipeline_*.py` commands in the original report reproduce
these checks with a fresh output directory and database prefix. The fixed
audit used separate local Brightway databases beginning with
`carculator-pipeline-fixed-final-20261010`; the original audit databases and
all background databases/methods were retained. Complete export inventories
and matrix diagnostics remain private and are not distributed here.

## Regression coverage

All **1,637 installed tests** passed across the five packages: 1,278 shared,
77 car, 139 truck, 43 bus and 100 two-wheeler tests, with no skipped tests.
Wheel and source-distribution resource checks, fresh core-only offline
model/LCIA runs, and the shared/truck documentation builds also passed.
These full suites used the isolated candidate artifacts recorded in
`verification.json`; the integration report records the subsequent focused
checks against the combined source.

`carculator_utils/tests/test_impact_source_groups.py` checks exact ownership
of onboard and external chargers, rejects ambiguous or unassigned inputs,
and compares summed groups with a full matrix solve across all four vehicle
families, a PHEV, two years and all bundled recipe-midpoint categories.

`carculator_truck/tests/test_sizing_consistency.py` checks final-mass road
loads, range/energy consistency, inventory purchases and complete LCIA runs.
It also covers a fixed curb mass, a payload limited by gross mass, labelled
samples, multiple years, unavailable historical vehicles and bounded failure.
Existing repeat-run tests verify that selecting a sample/year or running it
alone retains consistent results.

These are numerical and accounting checks. They do not supply new empirical
calibration or eliminate uncertainty in vehicle and background assumptions.
