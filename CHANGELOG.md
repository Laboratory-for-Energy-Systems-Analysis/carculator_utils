# Changelog

Notable user-facing changes to `carculator_utils`. The entry below is prepared for release;
it has not yet been published. Older entries, where present, retain their original record.

## [1.3.6] - Unreleased

### Compatibility and installation

- Require Python 3.12 (`>=3.12,<3.13`); older Python environments must be recreated.
- Use NumPy `>=1.26.4,<2` through the shared runtime.
- Build wheels and source distributions from centralized `pyproject.toml` metadata.
- Keep core model/LCIA use independent of Brightway; install `excel` or `brightway` extras for export. The Brightway extra targets the legacy stack (`bw2io<0.9`, `bw2data<4`, `bw2calc<2`).
- Align documentation versions with the package version and provide complete documentation-build dependencies.

### Model and inventory changes

- Separate stored battery energy, terminal DC energy and grid charging electricity; correct regenerative recovery, shaft/input energy balance and regenerative power limits.
- Restore paired VECTO speed/grade traces and duration conventions; interpret numeric gradient overrides as degrees and validate cycle inputs.
- Correct efficiency-map load accounting and add opt-in petrol start-stop/fuel-cut controls for passenger cars.
- Preserve fuel blend suppliers and shares through inventories and export; sum identical suppliers and compute PHEV fossil/non-fossil CO2 from fuel actually burned.
- Correct chromium emission identities, NMHC speciation, energy scaling and per-sample lifetime deterioration when translating hot pollutant factors into inventories.
- Restrict capacity and range overrides to selected vehicles and retain battery physical properties when chemistry-specific cost metadata is absent.
- Validate parameter records, coordinates, fuel blends and functional-unit loads; preserve caller-owned inputs and nested model selections.
- Bound sizing iterations per vehicle/sample, support zero-rate capital recovery, and make seeded input sampling local and reproducible.
- Preserve every year and the original inventory on repeated exports; align sample-specific passenger and tonne-kilometre normalization.

### Data and provenance

- Add reproducible 2025 measurement catalogs, cycle/road-load diagnostics, temporal continuity checks and BEV battery-sizing audits.
- Support grouped temporal uncertainty and retain original affected parameter records with provenance.
- Continue the IAM scenario names introduced in 1.3.5: `SSP2-NPi`, `SSP2-PkBudg1000`, `SSP2-PkBudg650`, and `static`. Legacy 1150/500 names remain rejected.

### Documentation and verification

- Add current installation and executable 2025 quick-start examples, migration notes and a release checklist.
- Record calibration scope, measurement boundaries and numerical consistency separately from empirical validation.
- Verify built wheels and sdist-built wheels, packaged resource hashes, installed tests with export extras and offline core-only model/LCIA smoke runs.

### Known limitations

- The electrochemical synthetic-methane supplier is absent from the bundled inventory index and raises a visible mapping error.
- Generic NMVOC characterization is used for ethene where the bundled biosphere index has no exact flow; HBEFA source-version provenance remains incomplete.
- Seeded parameter draws do not seed every downstream stochastic cost adjustment. Build fresh models for independent runs.

See [validation](docs/validity.rst) and [release preparation](RELEASING.md) for scope and verification instructions.

## 1.3.5 - 2026-04-29

### Added

- Added `AGENTS.md` with repository guidance for automated agents, including the `carculator` conda environment.
- Added a reproducible Brightway workflow at `dev/update_iam_b_matrices.py` to regenerate IAM B matrices from the `ecoinvent-3.12-cutoff` Brightway project.
- Added `dev/compare_iam_b_matrices.py` to compare current IAM B matrices against a previous git ref, including legacy scenario filename mapping.
- Added regression coverage for accepted and rejected IAM background scenario names.

### Changed

- Replaced public IAM scenario names `SSP2-PkBudg1150` and `SSP2-PkBudg500` with `SSP2-PkBudg1000` and `SSP2-PkBudg650`.
- Updated IAM characterized emission factors in all B matrix files using updated ecoinvent 3.12 cutoff-based Brightway databases.
- Used `SSP2-NPi` matrices for historical years 2005, 2010, and 2020 in the `SSP2-PkBudg1000` and `SSP2-PkBudg650` scenario files.
- Preserved existing custom noise characterization values where no Brightway LCIA method is available.
- Updated documentation to describe current IAM scenarios and ReCiPe 2016 (H) characterization.
- Bumped the package version from `1.3.4` to `1.3.5`.

### Fixed

- Avoided package import failures from eager `bw2io` imports by lazily loading `ExportInventory`.
- Ensured `pip` is available in the conda build host environment.
- Aligned runtime dependencies across packaging files.
- Hardened shared base class behavior used by downstream packages.
- Fixed numerical edge cases in shared calculations.
- Parsed inventory labels safely.
- Returned all SimaPro yearly exports.
- Ignored macOS `.DS_Store` metadata files.

### Notes

- IAM matrix updates were intentionally limited to activities present in the original `ecoinvent-3.12-cutoff` database.
- Direct elementary-flow columns were updated where matching biosphere flows and LCIA characterization factors were available.
- Temporary IAM matrix comparison CSV reports under `tmp/` are local analysis outputs and are not part of the tracked release.
