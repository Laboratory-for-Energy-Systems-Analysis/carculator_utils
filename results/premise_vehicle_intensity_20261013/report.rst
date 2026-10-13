Direct vehicle energy intensities with cross-model compatibility
================================================================

The REMIND car/truck intensity correction is implemented, tested and installed
in the four local encrypted scenarios. Other IAMs retain their existing
efficiency calculation. The controlled 2020 database has no material inventory
changes. The 2050 differences are fully explained by recovered energy trends
and a separately corrected vehicle-manufacturing selection bug.

Implemented changes
--------------------

``energy_intensity_aliases`` are optional, model-specific mappings. The 30
REMIND car entries and 20 truck entries now also name their direct
``Energy intensity`` series, for both REMIND and REMIND-EU. All existing
fleet-volume, energy-use and fuel mappings were checked to be unchanged.

For direct series, the efficiency index is intensity(2020) / intensity(year).
The direct input requires MJ/vehicle-km units and a finite positive 2020 value.
It can be used even if 2020 fleet activity is zero. Existing monotonicity rules
and the default 1.25 maximum efficiency index remain in force. The inverse is
the multiplier applied to vehicle energy purchases, with a minimum of 0.8
under that cap.

Missing direct inputs can use an available energy/service pair from the same
technology and region. Otherwise they return a neutral factor explicitly marked
``unavailable``. Direct-intensity processing never borrows another technology's
or region's curve. Array attributes and each regionalized vehicle's
``log parameters / IAM efficiency source`` record the source. The separate
EUR Large Car class remains unavailable: no SUV fleet volume or intensity was
assigned without an agreed proxy rule.

Four locally installed encrypted files each gained 545 mapped rows:
SSP1-PkBudg1000, SSP2-NPi, SSP2-PkBudg1000 and SSP3-rollBack. Every original
plaintext byte is retained; only missing intensity rows are appended. The
restoration helper checks model, scenario, units, unique identities and the
existing transport values against the matching 3.5.2 original. It rejects
another scenario version and conflicting existing data. Reapplying it is
idempotent. Encrypted backups and candidates remain in the private workspace.

The source filtering notebook's whitelist now includes ``Energy intensity``.
Only that source-list entry was added. JSON and cell syntax were checked, the
whitelist was evaluated in isolation, and unrelated cells/outputs were verified
unchanged. The complete export notebook was not executed: it currently points
at IMAGE files and would write unrelated exports. This change and its before/
after hashes are in ``installation.json``. No remote scenario archive was
republished; future downloads require the same data preparation for direct
signals, with the documented fallback available for older archives.

Operating energy must not scale vehicle manufacture
---------------------------------------------------

The database comparison exposed an inherited bug in the substring fuel filter:
``diesel`` also matched ``lorry production, diesel``. This reduced the number
of trucks manufactured per tonne-kilometre when applying an efficiency trend.

The car/truck selector now requires an energy product and its appropriate unit,
in addition to the IAM fuel mapping. Fuel-labelled trucks, engines, fuel cells
and electricity meters do not qualify. Direct energy suppliers and market
groups remain supported. Regression fixtures include vehicle manufacture and
diesel-engine purchases, which must remain unchanged when operating energy is
scaled.

In the final 2050 build, 62 previously scaled manufacturing exchanges return
to their 2020 per-service quantities, each 25% above the incorrectly reduced
value. The number of units inside each vehicle-production inventory, nominal
battery capacities, replacement counts, physical masses and other hardware
specifications are unchanged by this correction. Coupled constant-range
hardware sizing remains a subsequent task.

Verification
-------------

* 223 focused tests pass, including direct-intensity normalization and units,
  missing regional/reference data, zero-fleet baselines, other IAM paths,
  encrypted data restoration, source logging and energy-product selection.
  Existing fuel-carbon, hydrogen compression, battery, emission-driver and
  CDR tests are included.
* Full IAMDataCollection runs cover the four restored REMIND scenarios and
  an isolated encrypted REMIND-EU SSP2-NPi original. An independent NumPy
  cumulative-maximum calculation verifies 51,120 direct-intensity year cells,
  including the cap and monotonicity policy. Every 2020 index is one.
* Ten real-file calculation checks cover cars and trucks in IMAGE, TIAM-UCL,
  MESSAGE, GCAM and WITCH. Outputs are identical to their existing calculation.
  These are efficiency-path checks, not full Brightway builds of those IAMs.
* Full REMIND SSP2-NPi / ecoinvent 3.12 cutoff builds for 2020 and 2050 each
  complete with zero validation errors. They use isolated project copies and
  do not write a database into the user's persistent Brightway project.

.. list-table:: Full database comparison against the previous emission-driver fix
   :header-rows: 1

   * - Check
     - 2020
     - 2050
   * - Activities
     - 42,564
     - 42,574
   * - Materially changed exchanges
     - 0
     - 688 in 325 vehicle services
   * - Corrected manufacturing purchases
     - 0
     - 62
   * - Fuel/CO2 balances checked
     - 495 passed
     - 495 passed
   * - Hydrogen/compression balances checked
     - 147 passed
     - 147 passed
   * - Validation errors
     - 0
     - 0
   * - Validation warnings
     - 401, unchanged
     - 460, previously 445

Every material exchange difference has an independent expected ratio from the
effective operating-energy change, or restores a manufacturing quantity checked
against 2020. The other 626 changed exchanges are energy purchases and
fuel-derived CO2 or sulphur. Generic-air methane leakage is also checked
against its expected fuel-demand ratio. HBEFA emissions, refrigerants, wear
and road infrastructure remain unchanged. All 15 additional
2050 warnings are the existing hot-emission screening diagnostic: changing
fuel demand while retaining distance/start-based factors changes its ratio.
These warnings do not establish EURO-limit exceedances.

.. list-table:: EUR 2050 operating-energy multipliers, relative to 2020
   :header-rows: 1

   * - Vehicle
     - Before
     - After
   * - Medium BEV car
     - 1.0000
     - 0.8116
   * - Medium FCEV car
     - 1.0000
     - 0.8000
   * - Medium hybrid-electric car
     - 1.0000
     - 0.8000
   * - 40 t BEV truck
     - 0.8000
     - 0.8000
   * - Separate Large BEV car
     - 1.0000
     - 1.0000, unavailable regional signal

Remaining boundaries
---------------------

The recovered direct series describe fleet-level technical energy trends,
not specifications for newly manufactured vehicles. A hybrid's total intensity
does not separately establish its electric/combustion mode engineering inputs.
Constant-range hardware calibration, the EUR Large Car proxy and unmapped
technologies remain explicit follow-up decisions.

Compatibility preserves the other models' existing efficiency calculations;
it does not certify all their input data. The inspected MESSAGE file has no
detailed car/truck mappings. Fourteen IMAGE truck fleet entries lack an energy
alias. One TIAM-UCL car energy alias and two GCAM truck aliases are absent from
the inspected files. The WITCH source has missing car aliases and reports tkm
for mapped car services and pkm for mapped truck services, requiring a separate
source/unit review. None of these gaps was filled with an invented improvement.

Reproduction and commits
-------------------------

Premise commits:

* ``ae2f3c5``: exclude vehicle manufacture from operating-energy scaling.
* ``c88ab55``: optional direct intensity mappings, calculations and source logs.
* ``9e3671b``: verified encrypted-scenario restoration and regression tests.

``dev/install_premise_vehicle_intensities.py`` records the local installation
and filtering edit. ``dev/audit_premise_vehicle_intensity.py`` verifies IAM
factors and cross-model calculations. ``dev/build_premise_vehicle_intensity.py``
builds isolated databases; ``dev/audit_premise_vehicle_intensity_builds.py``
checks complete inventories and fuel balances. Original source files, installed
files and scripts are identified by hashes. The installer was formatted after
execution; both hashes and verified AST equivalence are recorded.

The report files contain hashes, coverage, normalized factors and changed-flow
diagnostics. Complete inventories, validation dumps, backups and logs remain
private under ``/private/tmp/premise-vehicle-intensity-20261013`` or untracked.
