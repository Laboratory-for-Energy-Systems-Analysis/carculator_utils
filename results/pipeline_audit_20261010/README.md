# Vehicle-to-LCIA spot checks, 10 October 2026

**Status:** both findings below have been corrected. See the
[verification after the fixes](fixed/README.md). This page and its adjacent JSON
files preserve the original audit and the numerical evidence that motivated
the changes; they describe the code at the recorded pre-fix revisions.
The [integration report](integration/README.md) records the final combined
code, including the separately committed hydrogen-compression change.

This audit runs vehicles through sizing, cycle energy, fuel or electricity
consumption, inventory assembly, functional-unit conversion and LCIA. It
compares three calculations: the package's usual impact calculation, a direct
solution of its complete inventory matrix, and Brightway calculations of the
exported vehicle inventories.

The sample contains eight randomly selected cases, stratified to include one
battery-electric and one combustion vehicle from each of the four vehicle
families. The selection seed is `20261010`; the candidate pools and draws are
recorded in [model_checks.json](model_checks.json). Three deliberate checks add
a petrol plug-in hybrid, a hydrogen truck and a prospective background for the
same electric car. These are deterministic parameter runs; the seed controls
case selection, not parameter uncertainty or incidental model cost randomness.

All vehicles have manufacture year 2025. Car cycles are WLTC, trucks use Urban
delivery or Regional delivery, buses use the bundled `bus` cycle and
two-wheelers use their size-specific bundled cycle. Exact cycle names and country codes are recorded
in the JSON results. The sample does not cover every size, powertrain, year,
uncertainty mode or custom override.

## Comparability

The matching Brightway project is
`carculator-matrices-premise-2.5.4-ei312-20261009`, with premise 2.5.4 and
ecoinvent 3.12 cutoff. Static comparisons use
`carculator-ei312-premise254-static`, the source for the bundled static B
matrix. Linking directly to an unmodified ecoinvent database would introduce
a background difference into this test.

The usual calculation groups inventory contributions by source. The manual
calculation bypasses this grouping and solves

`x = solve(A, f / load); impact = B @ x`.

Here `f` demands one vehicle-kilometre, and `load` is passengers per vehicle for
passenger-kilometres, cargo tonnes for tonne-kilometres, or one for
vehicle-kilometres. B contains characterized background impacts and direct
flow factors; it is not a biosphere-exchange matrix. This solve independently
checks allocation, grouping and normalization, but shares A and B with the
package. The separate Brightway calculation tests export, supplier linking
and full background LCIA.

Brightway links suppliers by exact name, reference product, location and unit;
biosphere flows use name, categories and unit. Ambiguous or absent matches
raise an error. The audit adds separate foreground databases and 24 custom
noise flows; it does not change existing background inventories or methods.
The standard methods give these custom noise flows no characterization.
The package's separate human-noise method is checked by the matrix solve but
has no matching Brightway method in this project and is excluded from the
Brightway comparison.

The prospective case uses the same exported foreground against the 2020 and
2030 SSP2-NPi backgrounds and averages their impact scores. This reproduces
the package's linear interpolation of B for 2025. It does not change the
foreground vehicle between the two endpoint calculations.

"Static" refers to the background impact matrix. The model still constructs
its country- and lifetime-specific electricity supply. French and German
electricity projections after 2025 use the documented European Union proxy.
These comparisons therefore check the implemented assumptions, not national
forecasts or observed real-world vehicle impacts.

The numerical LCIA comparison tolerance is `rtol=1e-5, atol=1e-10` (0.001%
relative). This allows floating-point storage and arithmetic differences;
it is not a statement about scientific uncertainty.

## Findings

### Chargers are counted twice in the usual impact totals

The source-category patterns in
`carculator_utils/data/lcia/impact_source_categories.yaml` put onboard car
chargers and scooter chargers in both `powertrain` and `charger`.
`Inventory.get_split_indices()` removes duplicates within a category but not
between categories. Summing the reported impact groups consequently counts
those suppliers twice.

The extra charger contribution explains the discrepancy in all affected
categories, to the declared numerical tolerance. It raises climate impacts
by 0.69% for the sampled small electric car, 1.70% for the electric scooter,
0.47% for the plug-in hybrid and 0.61% for the prospective electric car.
The largest relative error across the sampled categories is 1.91%.

Proposed correction: assign onboard chargers to the powertrain group and
external charging infrastructure to the charger group using unambiguous
rules. Validate that each contributing exchange belongs to exactly one
group, and test grouped totals against a complete matrix solve. Existing
result categories can remain available without counting an input twice.

### Hydrogen-truck energy uses the previous sizing mass

For the 26-tonne hydrogen truck, the cycle trace corresponds to a driving
mass of 17,611.60 kg; the final reported mass is 17,691.40 kg. Independent
force calculations using the final mass consequently differ by about 0.45%
for mass-dependent terms. This exceeds the audit's 0.2% force-consistency
threshold. Truck sizing stops at a 1% change in available payload, so its
current convergence policy permits this residual.

Refreshing the energy calculation at the final state changes TtW energy
from 4,860.67 to 4,872.71 kJ/km (+0.25%). This refresh is a diagnostic, not a
new complete vehicle/inventory run. The existing LCIA uses the original
4,860.67 kJ/km value.

Proposed correction: converge driving mass and energy-storage state together
at a tighter, per-cell tolerance, then ensure the final energy trace and
consumption outputs use that same state. Recheck target range and inventories
after the final update. This is a smaller issue than the LCIA double counting.

No production model code or packaged scientific data was changed by this audit.

## Independent physical and inventory checks

For nine non-PHEV cases, rolling, aerodynamic, gradient and inertial forces
were independently calculated from speed, slope and final vehicle parameters.
Wheel energy was integrated over the one-second cycle. The audit checks each
time step, not just net cycle work, which can cancel positive and negative
kinetic work. Eight cases pass; the hydrogen truck has the mass residual above.

Cycle integration reproduces reported TtW energy for all nine cases, including
regeneration, battery discharge losses and the buses' separate HVAC terms.
This step uses the model's efficiency and auxiliary-energy traces; it does
not independently establish that the efficiency maps or HVAC assumptions
match measurements. Two-wheelers retain their current assumption of no
regenerative energy credit. The plug-in hybrid is checked separately by
retaining its electric and combustion modes and applying a 60% electric
distance fraction to fuel, electricity and TtW energy.

Additional checks cover driving mass, battery capacity and pack mass, range
where explicitly reported, charging losses, fuel-to-energy conversion,
fuel purchases, fuel mass fractions in supply datasets, fossil and biogenic
tailpipe CO2, vehicle lifetime allocation, battery replacements, and preservation
of A during export. These checks pass in the sampled cases.

For example, the lower-medium petrol car consumes 2,208.10 kJ/km. Its default
blend contains 98.8423711% petrol and 1.1576289% sugarbeet ethanol by mass.
With lower heating values of 42.6 and 26.5 MJ/kg:

`fuel = 2,208.10 / [1,000 × (0.988423711 × 42.6 + 0.011576289 × 26.5)]`

This gives about **0.052061 kg/km**. Complete oxidation with the documented
fuel factors gives **0.161579 kg fossil CO2/km** and
**0.001181 kg biogenic CO2/km**, matching the direct inventory exchanges.
These checks reproduce the model's complete-oxidation convention; they do
not independently close elemental carbon across its separately specified
CO, hydrocarbon and particulate emissions.

For this petrol car, the independent climate calculation in kg CO2-eq per
passenger-kilometre is:

| Contribution | Climate impact |
| --- | ---: |
| Vehicle production and replacements | 0.034876819 |
| Direct emissions | 0.101130042 |
| Fuel supply | 0.032868732 |
| Road, maintenance and other operation | 0.017031446 |
| **Total** | **0.185907039** |

The climate method is IPCC 2021 GWP100, total excluding biogenic CO2. Biogenic
CO2 is retained in the inventory but is not assigned a positive emission
factor by this method. Full exact method tuples are recorded in the
Brightway results, including the separate climate method with biogenic CO2.

## Results

All **242 manual/Brightway comparisons pass** (11 cases × 22 categories).
The largest relative difference is **0.00000761%**. The usual grouped
calculation passes 154 comparisons and differs in 88: the 22 matched
categories for each of the four cases affected by charger duplication.

Climate scores below are **kg CO2-eq per stated functional unit**.
Different functional units must not be compared directly. A dash indicates
a difference below 0.001%. All cases use 2025 vehicle parameters.

| Case | Vehicle | Country | Background | Unit | Usual calculation | Manual solve | Brightway | Usual vs BW |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| case-01 | Car Small, BEV | FR | static | pkm | 0.076910 | 0.076385 | 0.076385 | +0.686% |
| case-02 | Car Lower medium, ICEV-p | CH | static | pkm | 0.185907 | 0.185907 | 0.185907 | — |
| case-03 | Truck 7.5t, BEV | CH | static | tkm | 0.129976 | 0.129976 | 0.129976 | — |
| case-04 | Truck 18t, ICEV-d | CH | static | tkm | 0.462770 | 0.462770 | 0.462770 | — |
| case-05 | Bus 13m-city, BEV-depot | FR | static | pkm | 0.056729 | 0.056729 | 0.056729 | — |
| case-06 | Bus 18m, ICEV-d | CH | static | pkm | 0.098587 | 0.098587 | 0.098587 | — |
| case-07 | TwoWheeler Scooter 4-11kW, BEV | DE | static | pkm | 0.059935 | 0.058936 | 0.058936 | +1.695% |
| case-08 | TwoWheeler Scooter <4kW, ICEV-p | CH | static | pkm | 0.084862 | 0.084862 | 0.084862 | — |
| case-09 | Car Lower medium, PHEV-p | CH | static | vkm | 0.179814 | 0.178975 | 0.178975 | +0.469% |
| case-10 | Truck 26t, FCEV | DE | static | tkm | 0.115758 | 0.115758 | 0.115758 | — |
| case-11 | Car Small, BEV | FR | SSP2-NPi | pkm | 0.065655 | 0.065259 | 0.065259 | +0.607% |

The prospective Brightway climate scores are 0.074675916 for the 2020
background and 0.055841703 for 2030. Their average is 0.065258809
kg CO2-eq/pkm, matching the independently solved 2025 result.

[Download the climate comparison table](climate_comparison.csv).

Machine-readable evidence:

- [Model and complete-matrix checks](model_checks.json), including input
  coordinates, package commits, computed parameters and each numerical check.
- [Physics, fuel supply and source-group diagnostics](physics_checks.json).
- [Brightway scores and comparisons](brightway_checks.json), with database
  names, activity keys, method tuples, units and endpoint results.

## Reproduction

Use Python 3.12 with matching sibling source checkouts for the model commands.
Use the environment containing the matching project and modern Brightway
stack for the Brightway command. The executed Brightway environment used
bw2data 4.7 and bw2calc 2.5.0; its remaining versions are in the results.

```bash
python dev/audit_pipeline_spotchecks.py \
  --private-dir /tmp/carculator-pipeline-audit-new \
  --report results/pipeline_audit_new/model_checks.json

python dev/audit_pipeline_physics.py \
  --private-dir /tmp/carculator-pipeline-audit-new \
  --model-report results/pipeline_audit_new/model_checks.json \
  --report results/pipeline_audit_new/physics_checks.json

python dev/audit_pipeline_brightway.py \
  --private-dir /tmp/carculator-pipeline-audit-new \
  --model-report results/pipeline_audit_new/model_checks.json \
  --report results/pipeline_audit_new/brightway_checks.json \
  --database-prefix carculator-pipeline-audit-new
```

Choose a new private directory and database prefix for each run. The private
directory contains complete export inventories and matrix diagnostics;
these are not included in the public results and must not be redistributed
with licensed background information. Brightway imports can take several
minutes because this version compacts the whole project database after each
write. The audit databases remain in the local project for inspection.
