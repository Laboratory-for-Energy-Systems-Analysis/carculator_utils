# Changelog

Notable user-facing changes to `carculator_utils`. The entry below is prepared for release;
it has not yet been published. Older entries, where present, retain their original record.

## [1.3.6] - Unreleased

### Compatibility and installation

- Require Python 3.12 (`>=3.12,<3.13`); older Python environments must be recreated.
- Use NumPy `>=1.26.4,<2` through the shared runtime.
- Build wheels and source distributions from centralized `pyproject.toml` metadata.
- Add `brightpath>=1.0.0a6,<1.1` for inventory export. Its dependencies include `bw2io`, XlsxWriter and `olca-schema`; core model/LCIA calculations keep lazy imports and require no Brightway project. The `brightway` extra selects the legacy stack (`bw2io<0.9`, `bw2data<4`, `bw2calc<2`); `excel` remains a compatibility extra.
- Align documentation versions with the package version and provide complete documentation-build dependencies.

### Model and inventory changes

- Calculate fuel-based SO2 from fuel burned per kilometre, consistently with fuel purchases and CO2. Correct underestimated PHEV emissions caused by dividing stored fuel by combined range; verify petrol/diesel PHEVs, electric-driving shares from 0% to 100%, completed family inventories and annual exports. See [mass balance and migration](docs/validity.rst#sulfur-year-accounting).
- Preserve year-specific sulfur concentrations in fuel-based SO2 inventories instead of summing across selected years. Keep country fallback and fuel assumptions, handle zero concentrations, and return a labelled year array from `get_sulfur_content`. Verify sulfur mass balance, single/multi-year inventory agreement and annual exports across all four vehicle families. See [scope and migration](docs/validity.rst#sulfur-year-accounting).
- Delegate Brightway Excel and SimaPro CSV formatting to Brightpath and add `software="openlca"` foreground JSON-LD ZIP export. Preserve per-year outputs and inventory state; correct foreground database links. SimaPro now uses valid categories, canonical supplier labels and Latin-1 encoding, and warns when omitting unsupported custom noise flows. openLCA warns that ecoinvent providers and characterized elementary flows still need linking. See [export behavior and limits](docs/inventory_export.rst).
- Correct fuel-blend density for mass-fraction shares using additive component volumes. Preserve heating values and mass-based fuel/CO2 accounting while correcting reported litres; verify known-volume batches and completed car, bus, truck and two-wheeler inventories, including pure fuels and year-specific property overrides. See [assumption and checks](docs/validity.rst#fuel-blend-density).
- Restrict the empirical bus HVAC model to its existing 20-degree Celsius cabin assumption. Reject unsupported indoor temperatures before sizing and in the direct energy/HVAC API; accept scalar 20 or twelve all-20 monthly values. Preserve ambient-temperature dependence, overrides and default results. See [scope and migration](docs/validity.rst#cabin-temperature-limitation).
- Fix the bus temperature fallback for countries absent from the bundled table: preserve Swiss decimal temperatures instead of crashing during integer parsing. Retain the printed fallback notice and explicit temperature overrides; verify diesel, fuel-cell and depot BEV models, fuel/charging exchanges and LCIA across five affected countries. See [scope and limitations](docs/validity.rst#temperature-fallback-checks).
- Separate default hydrogen supply from petrol bioethanol shares. Use the configured primary route (100% natural-gas steam methane reforming) as an explicit fallback assumption for every country and year; preserve user hydrogen mixes. Verify completed car, bus and truck fuel supplies, unchanged driving energy and hydrogen demand, zero direct CO2 and annual exports. See [assumption and verification](docs/validity.rst#default-hydrogen-supply).
- Preserve default biofuel shares above 30% by replacing the universal cap with physical 0--100% bounds. Restore the bundled biomethane shares for Sweden, Norway and Iceland through fuel supply, combustion CO2, methane leakage and exports; retain interpolation, regional fallback and explicit blends. See [scope and verification](docs/validity.rst#default-biofuel-shares).
- Validate fuel-property overrides before sizing: positive heating values and densities, nonnegative CO2 factors, and biogenic fractions within [0, 1]. Reject nonnumeric, nonfinite and malformed values for both components, including zero shares. Normalize year-specific properties and verify their mass/energy balance, fossil/non-fossil CO2 and exported inventories across all four families.
- Reject known fuel types used under an incompatible blend category, such as hydrogen under diesel or petrol. Validate both components, including zero shares, during model construction with category, role and fuel context; retain supported fossil, biofuel and synthetic routes.
- Treat custom fuel blends as overrides of supplied fuel categories, retaining country/year defaults for other selected fuels. Preserve complementary secondary shares and caller data; validate partial blends through completed family runs, fuel suppliers and fossil/non-fossil CO2. Mixed-powertrain comparisons no longer fail because an untouched fuel category is missing.
- Calculate default electricity mixes per vehicle and sample using their own operating lifetime. Keep distinct charging/fuel-production supply paths where needed, and characterize each sample's actual matrix. Preserve custom mixes, export supplier links and provenance; expose labelled `electricity_mix` shares while retaining `mix` as a reporting summary. See [scope and verification](docs/electricity_lifetime.rst).
- Preserve generated vehicle comments and activity-specific sources in SimaPro exports. Use catalog metadata only for absent fields and omit missing-source placeholders. Align string CSV quoting with file exports so empty comments and special characters serialize correctly. Verify CSV metadata in completed car, bus, truck and two-wheeler exports, including selected samples and multiple years.
- Preserve retained and reordered sample labels in LCIA results. Export a single selected numeric or named sample without requiring label zero, keeping exchange amounts and vehicle comments aligned. Reject multi-sample exports with selection instructions; verify completed models, sensitivity ratios and repeated exports across all four vehicle families.
- Share methane-leakage accounting across gas cars, buses and trucks: balance additional fuel purchases with emitted methane, preserve fuel-blend fossil/non-fossil shares, and include both flows in impact totals and exports. Validate active loss rates and retain the existing kg-lost/kg-engine-fuel convention. Document the historical default's possible overlap with upstream station losses; see [boundaries and verification](docs/methane_leakage.rst).
- Correct biological synthetic methane's silent sewage-biomethane substitution. Supply the bundled PEM-hydrogen/atmospheric-CO2 methanation route through an explicit delivery activity, with documented distribution proxies and BioCat's 0.314 kWh/kg compression assumption. Align this route's heating value (49.9 MJ/kg) and combustion CO2 (2.75 kg/kg); verify completed car, bus and truck inventories and repeated exports. See [scope and limitations](docs/biological_methane.rst).
- Correct the shared FCEV cost projection to update the fuel-cell-stack price without overwriting the hydrogen-tank price. Retain the existing curves and sampled factors; car and bus overrides and the normal truck workflow are unaffected.
- Retain projected-cost uncertainty with seeded input samples for cars, buses and two-wheelers. Preserve factors through selection, interpolation and serialization without global RNG draws; keep static/sensitivity factors deterministic and explicit prices authoritative. Single stochastic samples now retain uncertainty, including `stochastic(1)`; regenerate old stochastic cost results.
- Validate triangular modes and bounds when loading parameter records, with year and vehicle context in errors. Test sampling of each vehicle family's complete defaults before scope selection, including the repaired truck cost distributions.
- Align automatic component-cost projections by year and sample, correcting mixed-year prices in multi-year uncertainty and sensitivity runs. Keep the price curves, uncertainty draws and explicit battery-cost overrides; verify static reference agreement and unchanged physical/inventory results.
- Preserve explicit generic and selected-chemistry battery unit costs through chemistry selection and cost projection. Add scoped `battery_costs` constructor inputs, labelled input provenance and effective-default sensitivity; leave existing default price trajectories unchanged. Reject combined-only PHEV prices that aggregation would discard.
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

- Refresh national electricity generation using attributed Ember history and three explicit GECO 2025 scenarios through 2070, with 211 geographic codes, validated shares, source hashes and reproducible import/audit scripts. Preserve the former table as `legacy`; disclose regional projections, coarse LCI proxies, source exclusions and GECO residual reconciliation. Hold refreshed endpoints across complete vehicle lifetimes and retain scenario/loss provenance in exports. TYNDP 2026 remains an audited candidate pending reliable LCI mappings. See [data, assumptions and reproduction](docs/electricity_scenarios.rst).
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
