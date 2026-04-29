# Changelog

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
