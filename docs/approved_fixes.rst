Approved robustness work: implementation status
===============================================

The 18 approved items have separate, targeted implementation commits in the
repositories they affect. **Eleven items are closed at the software/data-boundary
level; seven are partially addressed and still require scientific evidence or
destination-system verification.** A passing numerical test is not treated as
empirical validation. No commits have been pushed as part of this task.

The implementation spans 41 issue-specific commits: 18 in ``carculator_utils``,
6 each in ``carculator`` and ``carculator_bus``, 4 in ``carculator_truck``, and
7 in ``carculator_two_wheeler``. Cross-repository fixes have a separate commit
in each affected repository. Follow-up integration corrections retain their
issue number. This overview is a separate documentation commit.

The :download:`status and verification record <_static/approved_fix_status_20261009.json>`
lists every implementation commit, issue qualification and verification result.

Closed items
------------

.. list-table::
   :header-rows: 1
   :widths: 6 36 58

   * - Issue
     - Problem
     - Implemented correction
   * - 1
     - Repeated completed runs drift or lose PHEV inputs
     - Retain original inputs, preserve explicit edits, and rebuild derived state.
   * - 2
     - Synthetic-fuel supplier labels disagree with carbon source/allocation
     - Correct exact supplier mappings and verify completed family inventories.
   * - 3
     - Public fuel catalogue advertises unavailable routes
     - Exclude unsupported choices and explain rejection before sizing.
   * - 4
     - Overlapping bundled parameter records
     - Resolve scopes while retaining effective values, uncertainty and provenance.
   * - 5
     - Missing declared inputs become silent zeros
     - Carry coverage metadata and reject missing active-vehicle inputs before sizing.
   * - 6
     - Human bicycle purchase and maintenance are zero
     - Add the sourced EUR 500 mechanical-bicycle anchor and an explicitly provisional maintenance assumption.
   * - 7
     - Shared annual finance uses distance and fails at zero interest
     - Use lifetime years and stable capital recovery, with independent cash-flow checks.
   * - 8
     - Stale documentation and hidden warnings
     - Refresh API contracts, remove global warning suppression and correct pandas reductions.
   * - 9
     - Petrol scooter disposal counted twice
     - Remove additional dismantling where complete-vehicle production includes disposal.
   * - 10
     - Complete scooter proxy overlaps separate production components
     - Use one documented dry-mass-scaled complete-vehicle boundary.
   * - 12
     - Generic 0.4% methane loss may duplicate supplier emissions
     - Remove the unqualified overlay; retain upstream/exhaust emissions and explicit residual-loss inputs.

Partially addressed items
--------------------------

.. list-table:: Implemented work and remaining requirement
   :header-rows: 1
   :widths: 6 45 49

   * - Issue
     - Implemented
     - Still required before scientific closure
   * - 11
     - Physical-carbon diagnostics and repeatable CO2 reconciliation with explicit sourced exhaust fractions; default export limitation disclosed.
     - Defensible unspecified HC/PM composition and a complete audit of cement-capture credit allocation. Default full-oxidation CO2 remains unclosed with separately estimated carbon pollutants. See :doc:`carbon_accounting`.
   * - 13
     - Exact Ethylene flows and characterization; table fingerprints and recovered workbook hashes; manual multipliers made explicit.
     - Verified HBEFA extraction version, reproducible derivation of shipped coefficients and independent NH3/N2O calibration. See :doc:`hot_emission_audit`.
   * - 14
     - Conservative import/re-export tracing, labelled consumption mixes and sourced grid-loss overrides.
     - Updated default bilateral trade/loss observations and improved coarse technology LCI proxies. See :doc:`electricity_scenarios`.
   * - 15
     - Missing bus climates require explicit input; automatic Swiss substitution removed; HVAC profiles validated.
     - Broader representative climate coverage and measured thermal models beyond the retained fixed-cabin bus curve and other-family annual priors. See :doc:`input_validation`.
   * - 16
     - Explicit calibration/held-out qualification, failure-reporting and 40 fresh completed model runs.
     - Matched independent measurement datasets and the unrecovered primary 32t VECTO trace. All 41 paired observations remain screening. See :doc:`energy_measurements`.
   * - 17
     - Complete retail purchase quotes replace the two-wheeler component sum once; cost evidence and price-year gaps recorded.
     - Matched component quotations, maintenance evidence and consistent currency-year rebasing. The generic e-bike component total is not calibrated to the ZIV market average.
   * - 18
     - Reachable export chains, exact destination-link audits, explicit unsupported 3.9 routes, openLCA method UUID forwarding and retained SimaPro noise audit quantities.
     - Exact openLCA product/provider UUID matching, a destination custom-noise method and native SimaPro/openLCA import/LCIA parity. See :doc:`inventory_export`.

Verification and provenance
---------------------------

The issue-specific checks include completed model/inventory/LCIA cases across
all four vehicle families, repeated runs, year/sample alignment, independent
cash-flow and mass/energy expectations, and format-level exports. The energy
catalogue rerun completed 40 runs with no errors; it retained 41 screening
comparisons and 77 exclusions. Eight export audits matched all ordinary flows
against exact installed ecoinvent 3.9/3.10 cutoff identities after removing
unreachable chains. Custom noise remains outside those standard databases.

Installed-package verification on macOS arm64 / Python 3.12.13 covered
1,585 distinct tests: 1,234 shared, 77 car, 130 truck, 43 bus and 101 two-wheeler.
The full runs identified 12 obsolete integration expectations for comments,
early fuel rejection, missing-input visibility and the historical methane data
hash. After correcting those expectations, focused reruns passed all 25
sample/export checks and all 7 affected car/truck checks. There are no unresolved
test failures. Runtime code and resource bytes were unchanged between the
full-suite builds, final rebuilt packages and current checkouts.

All five wheel/source-distribution builds passed resource-hash checks,
dependency checks and fresh-environment offline model/LCIA smoke tests.
Wheel and source-distribution model results agree. This does not establish
Linux/Windows or conda validation, or native destination-software LCIA parity.

All five Sphinx documentation builds passed with warnings treated as errors.
Original user notebooks, inventory exports, and staged changes were checked
against their saved hashes and remain intact.
