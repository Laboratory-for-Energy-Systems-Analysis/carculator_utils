# Integration verification, 10 October 2026

This repeats the eleven [original cases](../README.md) with both audit fixes
and the separately committed hydrogen-compression change (`654a844`). The
[isolated fix verification](../fixed/README.md) remains available to distinguish
the effects of charger grouping and truck sizing from hydrogen supply changes.
The input choices, cycles, backgrounds, functional units and tolerances are
unchanged. Source fingerprints are recorded in [verification.json](verification.json).

All 331 model/matrix checks, 54 physical checks, 3 PHEV weighting checks and
40 inventory/contribution checks pass. All 242 grouped/Brightway and
manual/Brightway comparisons pass. The largest relative difference between
the grouped calculation and Brightway is 0.00000761%.
The 46 focused regression tests and the shared documentation build with
warnings treated as errors also pass. Full installed-package verification
of the isolated fix snapshot is recorded in [the earlier report](../fixed/verification.json).

Climate scores are kg CO2-eq per stated functional unit. All vehicles are 2025.
Backgrounds and countries are as recorded in the original audit; case-11 uses
the SSP2-NPi 2020/2030 interpolation and the other cases use the static bundle.

| Case | Vehicle | Unit | Grouped total | Manual solve | Brightway |
| --- | --- | --- | ---: | ---: | ---: |
| case-01 | Car Small BEV | pkm | 0.076385443 | 0.076385443 | 0.076385444 |
| case-02 | Car Lower medium ICEV-p | pkm | 0.185907039 | 0.185907039 | 0.185907037 |
| case-03 | Truck 7.5t BEV | tkm | 0.130013260 | 0.130013260 | 0.130013258 |
| case-04 | Truck 18t ICEV-d | tkm | 0.463309053 | 0.463309061 | 0.463309053 |
| case-05 | Bus 13m-city BEV-depot | pkm | 0.056729495 | 0.056729495 | 0.056729497 |
| case-06 | Bus 18m ICEV-d | pkm | 0.098587012 | 0.098587012 | 0.098587011 |
| case-07 | TwoWheeler Scooter 4-11kW BEV | pkm | 0.058935972 | 0.058935972 | 0.058935971 |
| case-08 | TwoWheeler Scooter <4kW ICEV-p | pkm | 0.084862000 | 0.084862000 | 0.084862001 |
| case-09 | Car Lower medium PHEV-p | vkm | 0.178974922 | 0.178974922 | 0.178974923 |
| case-10 | Truck 26t FCEV | tkm | 0.120855545 | 0.120855549 | 0.120855547 |
| case-11 | Car Small BEV | pkm | 0.065258809 | 0.065258809 | 0.065258809 |

Hydrogen compression changes only the hydrogen truck's climate result among
these eleven cases: 0.115960354 to 0.120855545 kg CO2-eq/tkm. The change is
upstream electricity in hydrogen supply; final vehicle mass, onboard fuel
consumption and range retain the corrected sizing state. It is separate from
the two defects identified by the original audit.

The audit's fuel-mass balance now sums only kilogram-denominated supplier
inputs. Its earlier sum included every fuel-supply input and therefore added
compression electricity (kWh) to fuel mass (kg). The corrected check retains
all 40 passing inventory checks for the isolated snapshot and passes on the
combined code. Non-mass inputs are recorded separately in the physics report.

Evidence: [model and matrix checks](model_checks.json),
[physical and inventory checks](physics_checks.json),
[Brightway comparisons](brightway_checks.json), and
[climate CSV](climate_comparison.csv).

Run the three audit commands in the original report with new output paths and
a new database prefix to reproduce these checks. This run used local databases
beginning with `carculator-pipeline-integration-20261010`. Complete exports and
licensed matrix diagnostics remain private. These comparisons test numerical
and accounting consistency, not empirical validity of every model assumption.
