# Energy-validation artifacts

Keep the primary evidence, reproducible inputs, output tables and provenance in
this directory. They are scientific audit records, not disposable build output.
Temporary logs, experimental reruns and local build environments belong outside
the checkout. Rendered Sphinx output belongs in `docs/_build/` or an external
build directory, not here.

| Location | Status and purpose |
| --- | --- |
| `expanded/measurements.json` | Source catalog, comparison settings and explicit exclusions. |
| `expanded/calibrated_2025/` | Preserved 40-run, 41-pair corrected-model comparison snapshot. The name does not imply universal empirical calibration. |
| `defaults_2025/` | Export of the preserved 2025 input snapshot. Current package data additionally contain temporal-uncertainty metadata. |
| `temporal/` | Annual before/after outputs, independent 2025 checks, plots, provenance and installed-artifact verification. |
| `adac_cycle/sensitivity/` | Final 24-run graph-reconstruction sensitivity, not an official ADAC numerical cycle. |
| `adac_cycle/results/` | Earlier 20-run investigation snapshot, superseded by `sensitivity/`. |
| `truck_diagnostics/verified/` | Source-road-load and meter-boundary diagnostic results. |
| `petrol_controls/` | Public opt-in controller validation and sensitivities; not a fitted class default. |
| Other baseline, component and auxiliary-fit directories | Retained intermediate investigation records; consult their provenance and the historical report before quoting values. |

The maintained narrative is `docs/energy_model_repairs.rst`; intermediate
findings are separated into `docs/energy_model_repairs_history.rst`. Vehicle
packages each maintain their own `docs/validity.rst` with model-specific scope.

Do not overwrite old provenance to make it match current source hashes. New
experiments write to a new output directory. Do not delete a trace, source
catalog or older result merely because a newer snapshot exists: its role in a
comparison or calibration may still need to be reproduced.
