Hot-pollutant inventory audit
=============================

The original 2026-10-07 audit of shared runtime commit ``161d4c2`` found six
pollutant-accounting defects. The repairs described below now pass all 34,518
scalar checks on completed runs across the four vehicle families. Ethene now uses the chemically equivalent Ethylene elementary flow, with
compartment-specific factors from the same methods as the bundled B matrices.

Scope and result
----------------

The counts in this section describe the historical October 7 audit. The
subsequent correction to evaporative speciation is described under
:ref:`evaporative-speciation`; it adds process-specific checks to the audit script.

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
   :widths: 55 15 15 15

   * - Check
     - Checked
     - Failed before
     - Failed after
   * - Coefficients to six principal pollutant outputs, including additions
     - 2,592
     - 0
     - 0
   * - Documented passenger-car lifetime-average NOx deterioration
     - 12
     - 12
     - 0
   * - Emission energy versus completed combustion fuel energy
     - 90
     - 74
     - 0
   * - Labelled hot-model output to vehicle parameters
     - 16,236
     - 408
     - 0
   * - NMHC mass before and after speciation
     - 144
     - 90
     - 0
   * - Vehicle parameters to inventory, retaining all mapping entries
     - 15,444
     - 84
     - 0

These are accounting checks, not independent empirical observations. The six
principal pollutants are CO, NOx, PM2.5, NH3, N2O and methane. Their unit checks
retain the current deterioration tables and manual NH3/N2O multipliers; a pass
does not validate those assumptions against the licensed HBEFA source data.

Original defects
----------------

The following descriptions record the original failing implementation.

1. **Chromium species were interchanged.** ``set_hot_emissions()`` assigns a
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

Implemented repairs and limits
------------------------------

.. _evaporative-speciation:

Evaporative NMHC correction, October 13
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Soak, diurnal and running-loss emissions are now kept separate while hot
exhaust and cold-start NMHC are speciated. Their existing process-specific
benzene quantities are retained, and the remaining evaporative mass is emitted
as generic NMVOC. Benzene is subtracted once from that residual. A process
with benzene exceeding its total evaporative NMHC is rejected.

The earlier implementation applied the exhaust profile to the combined pool.
For a 2020 Mini gasoline car with CH defaults, it attributed 0.59845 mg/km of
formaldehyde to evaporation. The correction removes this attribution and
retains 1.14240 mg/km from hot exhaust and cold starts. It also removes the
other unsupported exhaust-derived species from evaporation; this is not a
formaldehyde-only deletion. Vehicle energy, mass, battery, fuel demand and
the cold-start factors remain unchanged.

This is a limited speciation policy, not a newly calibrated evaporative profile.
It follows the separation of emission processes documented in
`EPA's onroad air-toxics report, section 5
<https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P1010TJM.TXT>`_ and
`MOVES4 speciation report, sections 3.2 and 4.2
<https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=P10186EB.TXT>`_. No US profile is
substituted for the European factors. The later cold-start audit below records
the HBEFA 5.1 source for cold-start, evaporative and running factors, and
the selected 2020 start count.
The correction does not resolve the separate accounting
boundary of directly tabulated exhaust benzene and the exhaust NMHC pool.

Tests isolate each evaporative process, independently check benzene plus
residual mass, retain hot/cold-start speciation, exercise hybrids and labelled
years/samples, and reject invalid evaporative mass balances. The completed
four-family audit also checks the named species against exhaust-only NMHC.
Only the car family currently ships the non-exhaust factor table.

.. _cold-start-audit:

Cold-start audit and daily start count, October 13
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Cold-start allocation is dimensionally correct: a coefficient in g/start is
multiplied by starts/day times 365 divided by annual kilometres. Hot-soak
coefficients use the same daily event count. Diurnal g/day and running-loss
g/km factors do not depend on that count. The public ``starts_per_day`` model
argument accepts a finite nonnegative scalar and retains the general default
of 2.3. Zero disables these per-event additions; it does not eliminate hot
exhaust or diurnal/running evaporation. Only cars currently ship this table.

The regenerated 2020 Premise cars explicitly use ``starts_per_day=1.8``, selected
by the user from `Switzerland's National Inventory Document 2026, Table 3-90,
page 167 <https://www.bafu.admin.ch/dam/en/sd-web/rMTT3CcvG0fJ/Switzerland%27s%20National%20Inventory%20Document%202026%20%28GHG%20inventory%201990-2024%29.pdf>`_.
This is the revised 2020 passenger-car value. It is an inventory-specific
assumption, not a newly calibrated all-country default. Annual mileage remains
12,000 km for combustion cars. The existing 6,000 km default for the electric
Micro car is unaffected. PHEV emissions retain the existing combustion-mode
weighting; this does not separately validate hybrid engine-start frequencies.

For Mini gasoline, cold-start NMHC is 0.925388694 g/start. At 2.3 starts/day
and 12,000 km/year, it produces 64.7387 mg/km of NMHC, of which 1.10056 mg/km
is formaldehyde at the existing 1.7% fraction. Hot exhaust adds 0.04184 mg/km.
At 1.8 starts/day, formaldehyde becomes 0.90314 mg/km in total. Evaporation
contributes no formaldehyde under the separately corrected speciation policy.

The `EMEP/EEA road-transport guidebook, June 2026 update
<https://www.eea.europa.eu/en/analysis/publications/emep-eea-guidebook-2023/part-b-sectoral-guidance-chapters/1-energy/1-a-combustion/1-a-3-b-i/@@download/file>`_
(Table 3-86d, page 107) retains a 1.70% formaldehyde fraction for Euro-6 petrol
NMVOC. Its method applies species fractions to total exhaust NMVOC. Applying
this fraction to cold as well as hot exhaust is therefore not, by itself, an
identified implementation error. Other species have revised profiles; a full
speciation refresh is a separate change.

The source attribution supplied by the model author on 13 October 2026 is:
"the original LCA model, carculator, uses emission factors for cold start,
evaporative and running emissions from the HBEFA 5.1 emissions handbook".
This is recorded in coefficient provenance and the regenerated combustion-car
dataset comments. The coefficients are retained. Detailed temperature, parking-time and trip-length settings are not
separately recorded in this repository. The ``country="CH"`` model option does
not select or recompute these fixed emission coefficients.

The `HBEFA 4.1 development report
<https://cdn.prod.website-files.com/6207922a2acc01004530a67e/625e8c74c30e26e022b319c8_HBEFA41_Development_Report.pdf>`_
(section 6, pages 23–30) treats cold emissions as excess above hot operation
and accounts for these conditions. It provides methodological context, not the
source of the retained HBEFA 5.1 factors. The separate exhaust-benzene mass
boundary and speciation questions are not resolved by the start-count change.

The historical ``dev/audit_car_cold_start.py`` audit decomposed hot, cold, soak,
diurnal and running emissions and verified the saved EF 3.1 scores. The script
is available at pre-cleanup Git revision ``862bc96``; its private intermediate
run files were archived during campaign closeout. The retained conclusions and
source boundaries are summarized here and in :doc:`premise_vehicle_update`.
No clamp or arbitrary formaldehyde reduction is introduced.

Earlier accounting repairs
~~~~~~~~~~~~~~~~~~~~~~~~~~

The October 13 PAH follow-up found no total-hydrocarbon-to-PAH confusion in
the shared library. Completed 2020 car, truck, bus and two-wheeler exports
preserve each model's PAH quantities. Increasing the diagnostic total
hydrocarbons by 1000 times leaves the PAH matrix rows and all exported
biosphere exchanges unchanged. A known-mass regression now protects this
separation in ``tests/test_hot_emissions.py``. The issue was in Premise's
downstream substring-based normalization and validation, which matched
``Hydrocarbon`` to ``PAH, polycyclic aromatic hydrocarbons``.

* Immediate rural exhaust is assigned to ``air, non-urban air or from high
  stacks``, together with suburban exhaust. Their masses are summed once per
  pollutant, while urban emissions keep their own compartment. The former
  ``low population density, long-term`` mapping was incorrect: ecoinvent uses
  long-term compartments for releases more than 100 years after the activity,
  not for rural roads. See `ecoinvent's LCIA definitions
  <https://support.ecoinvent.org/lcia-results>`_. Existing long-term matrix and
  ethylene-cache entries are retained for index compatibility, but receive no
  direct road-exhaust demand. Background waste-treatment releases are unchanged.
* Total hydrocarbons are retained as a vehicle diagnostic but are no longer
  mapped to ``Hydrocarbons, chlorinated`` or counted alongside their components.
  Methane, named non-methane species and residual NMVOC enter the inventory once,
  including the modeled cold-start and evaporative contributions. Carbon
  diagnostics and explicit CO2 reconciliation also exclude the aggregate.
  This follows the pollutant definitions in the
  `HBEFA reference, section 2.2.1 <https://download.hbefa.net/helpfiles/HBEFA51_help_en.pdf>`_.
  That definition does not resolve the packaged tables' extraction provenance.
* Hot-model output is mapped to vehicle parameters by explicit pollutant names
  and documented aliases, preserving chromium oxidation states.
* Hybrid powertrain names are mapped to their combustion category before
  selecting NMHC species. Named fractions plus the unspeciated remainder sum
  to the original NMHC mass. Missing profiles, including gas, leave the parent
  mass in generic NMVOC rather than inventing a species distribution.
* Many-to-one inventory mappings now sum all contributing parameters. Ethane
  retains its own flow; Ethene uses Ethylene (C2H4). Three exact air-compartment
  flows are appended to private inventory indices and characterized using
  ``data/emission_factors/ethylene_characterization.json``. Existing bundled
  matrix positions are preserved. Missing method factors remain explicitly
  recorded zeros; they are not substituted with generic NMVOC factors.
* The positive motive/auxiliary fuel-input profile, including optional
  combustion-control losses, is normalized to the completed combustion fuel
  energy. Hybrid recovery thus reduces fuel demand without creating negative
  pollutant emissions during braking. This proportional distribution preserves
  cycle totals and existing user energy overrides; it is not a validated
  second-by-second hybrid engine dispatch model. The calibrated fuel-energy
  calculations themselves are unchanged.
* Deterioration is evaluated independently for each size, powertrain, year and
  sample. With endpoint factor ``f`` at reference mileage ``K`` and lifetime
  ``L``, the lifetime-average factor is ``1 + (max(f, 1) - 1) * L / (2*K)``.
  Reference mileage remains 200,000 km for cars and 890,000 km for heavy
  vehicles. This implements linear deterioration from unity and the documented
  half-lifetime averaging convention, with linear extrapolation beyond the
  reference mileage. The original powertrain-specific endpoint tables are
  retained. As corrected on 14 October 2026, HEVs and PHEV combustion modes
  select the corresponding ICEV petrol/diesel endpoint, consistently with hot
  factor lookup. Hybrid labels previously selected unity placeholders or a
  missing-row fallback instead. This is an ICE-engine ageing proxy, retaining
  vehicle lifetime kilometres without a second PHEV utility-factor adjustment.
  PHEV mode weighting still occurs once when assembling the final vehicle.
  Cold-start and evaporative factors are added after hot-exhaust deterioration
  and are unaffected. Electric modes and absent source factors retain unity;
  two-wheelers still have no deterioration table. This correction does not
  establish hybrid-specific ageing behaviour or validate the high truck NOx
  coefficients whose derivation is no longer available.

These repairs change pollutant inventories and their LCIA results, particularly
toxicity and NMVOC-related impacts. They do not recalibrate HBEFA-derived
coefficients or change the earlier fuel-blend/CO2 accounting fixes. Regression
coverage includes the complete audit, independent per-sample deterioration
expectations and the Ethane/Ethylene/generic-NMVOC mapping contract.

The files are named ``EF_HBEFA42_*``, while several legacy docstrings and
documentation passages refer to HBEFA 4.1. The model author has since specified
HBEFA 5.1 for passenger-car cold-start, evaporative and running factors, as
documented above. This attribution does not extend to every vehicle-family
table or manual multiplier.
This audit establishes propagation from the shipped tables; it does not refit
their coefficients or independently validate the manual NH3/N2O multipliers.
Table hashes, scoped source-version attribution, and all retained manual
multipliers are published in ``data/emission_factors/provenance.json`` and
returned by ``get_emission_factor_provenance()``. Local truck and bus workbook artifacts were recovered and their hashes are
recorded without distributing the workbooks. They do not establish the extraction
version or a reproducible derivation of every shipped coefficient. Changing the NH3/N2O multipliers
without that source or matched measurements would be another unsupported
calibration, so this part of the scientific validation remains open.

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
The original failing result is retained as
:download:`baseline summary <_static/hot_emission_audit/summary.json>`.
The repaired result, with updated source hashes, is available as
:download:`repaired summary <_static/hot_emission_audit/repaired_summary.json>`.

The family installation verifier also passed 455 tests with one pre-existing
expected failure, checked bundled resources in wheels and source distributions,
and completed offline model/LCIA smoke runs from both artifact types. See the
:download:`installation verification report <_static/hot_emission_audit/installation_verification.json>`.
