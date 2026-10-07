Hot-pollutant inventory audit
=============================

The 2026-10-07 audit of shared runtime commit ``161d4c2`` **does not confirm
correct propagation of all hot pollutants into inventories**. All four vehicle
families completed sizing, inventory construction and LCIA, but the labelled
pollutant and mass-conservation checks exposed the defects below. This audit
does not change production code or emission factors.

Scope and result
----------------

The runs cover Medium cars, 13m-city buses, 40t long-haul trucks and
Motorcycle 11-35kW two-wheelers: 22 family/powertrain combinations, years 2020,
2025 and 2030, and two lifetime/annual-mileage samples (132 completed vehicle
cases). Conventional combustion, hybrids, plug-in hybrids, gas, fuel-cell and
battery-electric vehicles are included where supported by these scopes.

The reference calculation reads the coefficient CSVs independently, evaluates
g/MJ times kJ/1000, adds the existing cold-start and evaporation terms, and
divides by distance and 1000 g/kg. It checks each speed-defined air compartment.
It then follows each pollutant by name into the completed model and inventory.
Aggregate PHEVs are checked after construction from their combustion/electric
mode outputs using the electric utility factor.

.. list-table:: Scalar audit checks
   :header-rows: 1
   :widths: 65 15 20

   * - Check
     - Checked
     - Failed
   * - Coefficients to six principal pollutant outputs, including additions
     - 2,592
     - 0
   * - Documented passenger-car lifetime-average NOx deterioration
     - 12
     - 12
   * - Emission energy versus completed combustion fuel energy
     - 90
     - 74
   * - Labelled hot-model output to vehicle parameters
     - 16,236
     - 408
   * - NMHC mass before and after speciation
     - 144
     - 90
   * - Vehicle parameters to inventory, retaining all mapping entries
     - 15,444
     - 84

These are accounting checks, not independent empirical observations. The six
principal pollutants are CO, NOx, PM2.5, NH3, N2O and methane. Their unit checks
retain the current deterioration tables and manual NH3/N2O multipliers; a pass
does not validate those assumptions against the licensed HBEFA source data.

Confirmed defects
-----------------

1. **Chromium species are interchanged.** ``set_hot_emissions()`` assigns a
   positional array to separately sorted parameter names. Appending
   ``direct emissions`` changes the relative ordering of ``Chromium`` and
   ``Chromium VI``. Consequently, chromium VI is approximately 500 times its
   intended amount in the affected tested combustion vehicles, while chromium
   III receives the much smaller chromium VI quantity. This affects all four
   families and can strongly distort toxicity results.

2. **NMHC speciation does not conserve mass.** Named species receive their
   mass fractions, but the remaining generic NMHC is multiplied by the sum
   of those fractions rather than its complement. Retained totals are 98.4%
   for petrol cars/two-wheelers, 90% for diesel cars and 37.4% for diesel
   buses/trucks. The latter lose 62.6% before inventory construction.

3. **Hybrids and gas vehicles lose their NMHC.** The speciation lookup checks
   the original powertrain label before applying its combustion-powertrain
   mapping. Hybrid labels consequently select the zero BEV profile. Gas
   vehicles also select that profile because the tables have no gas profile.
   Both named species and the generic remainder become zero. Missing speciation
   should preserve the parent NMHC rather than erase it; choosing a gas species
   profile requires evidence.

4. **Ethane disappears from the inventory.** The flow map sends both Ethane
   and Ethene to the same Ethane biosphere row. Building a dictionary keyed by
   that row discards the Ethane parameter and retains only Ethene. The audit
   checks aggregation under the existing mapping to expose that loss; it does
   not endorse Ethane as a chemical proxy for Ethene. The bundled matrix index
   has no separate Ethene row, so a correct new mapping requires aligned matrix
   and characterization data, not an arbitrary row rename.

5. **Emission energy differs from fuel energy.** The hot-emission caller sums
   motive, auxiliary and recuperated energy directly. The fuel model now
   converts regenerative electricity into avoided fuel input through motor,
   transmission and engine efficiencies. These boundaries differ, including
   for later-year conventional labels with electric assistance. In the tested
   hybrids the hot-emission energy basis exceeds the completed fuel-energy
   basis by approximately 7--12%. Other differences occur for conventional
   buses. This must be reconciled before interpreting energy-scaled pollutants
   as consistent with the calibrated fuel consumption.

6. **Mileage deterioration is constant.** The interpolation routine duplicates
   the same correction at zero and reference mileage, then evaluates it at
   the maximum lifetime of the whole array. It therefore cannot reproduce
   the documented factor at half of each vehicle's lifetime. The passenger-car
   NOx checks fail for both lifetime samples. Correcting the policy requires
   distinguishing endpoint factors from lifetime-average factors and keeping
   sample/year coordinates intact.

Repair priorities and limits
----------------------------

First replace positional pollutant assignment with explicit name alignment,
restore NMHC mass conservation and preserve parent emissions where no species
profile exists. Then reconcile the fuel-energy boundary and deterioration
policy. Resolve Ethene using a scientifically justified inventory/LCIA mapping.
Re-run the audit after each change and evaluate the effect on toxicity,
photochemical ozone formation and particulate-related impacts.

The files are named ``EF_HBEFA42_*``, while several legacy docstrings and
documentation passages refer to HBEFA 4.1. This audit establishes propagation
from the shipped tables; it does not resolve their version provenance, refit
their coefficients or independently validate the manual NH3/N2O multipliers.
The existing speed-based urban/suburban/rural compartment convention is retained
as an assumption, rather than validated as a geographic exposure model.

Reproduce the audit
-------------------

Install matching checkouts of all four sibling packages, then run::

   python scripts/audit_hot_emission_inventory.py --output /tmp/hbefa-audit

The script writes every scalar comparison to ``checks.csv`` and the scope,
counts, failure examples and source-file SHA-256 hashes to ``summary.json``.
Exit status 1 means that accounting checks failed; a traceback means the audit
could not complete. Runtime exceptions are not converted into passing checks.
The recorded result is available as
:download:`summary.json <_static/hot_emission_audit/summary.json>`.
