# AGENTS.md

Guidance for automated agents working in this repository.

## Scope

These instructions apply to the whole repository.

## Project Overview

`carculator_utils` is a Python package with shared base classes and utilities for the `carculator` package suite. The core code builds and manipulates vehicle model parameters, energy use, emissions, background systems, inventories, and export mappings. Most model state is represented with `xarray.DataArray` objects whose key dimensions are usually `size`, `powertrain`, `parameter`, `year`, and `value`.

Important paths:

- `carculator_utils/`: package source.
- `carculator_utils/data/`: bundled model data, including CSV, YAML, JSON, and NPZ resources.
- `tests/`: pytest tests and small fixture files.
- `docs/`: Sphinx documentation.
- `conda/`: conda build recipe.
- `.github/workflows/main.yml`: CI formatting, test, packaging, and publish workflow.

Main modules:

- `vehicle_input_parameters.py`: loads vehicle parameter dictionaries/files into `klausen.NamedParameters`.
- `array.py`: converts input parameters into labeled `xarray` arrays.
- `model.py`: base vehicle model orchestration.
- `energy_consumption.py`: motive and auxiliary energy calculations.
- `hot_emissions.py`, `particulates_emissions.py`, `noise_emissions.py`: emissions models.
- `background_systems.py`: electricity mixes, fuel blends, sulfur content, and related background data.
- `inventory.py`: life cycle inventory assembly and impact-category helpers.
- `export.py`: SimaPro and inventory export mappings.
- `driving_cycles.py`: driving-cycle and gradient loading helpers.

## Environment

The package declares Python `>=3.10` in `setup.py`.

The local conda environment named `carculator` can be used to access all needed dependencies:

```bash
conda activate carculator
```

Typical local setup:

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
python -m pip install pytest pytest-cov
```

Documentation dependencies are separate:

```bash
python -m pip install -r docs/docs_requirements.txt
python -m pip install -e .
```

When dependencies change, keep the relevant files aligned:

- `setup.py`
- `requirements.txt`
- `conda/meta.yaml`
- documentation requirements, if the change affects docs builds

## Verification Commands

Run tests from the repository root:

```bash
python -m pytest
```

Run a focused test file:

```bash
python -m pytest tests/test_vehicle_input_parameters.py
```

Run coverage similarly to CI:

```bash
python -m pytest --cov=carculator_utils
```

Build documentation after installing docs dependencies:

```bash
make -C docs html
```

The test suite imports `carculator_utils`, whose `__init__.py` imports modules requiring scientific dependencies such as `xarray`; install the project dependencies before interpreting import failures as code regressions.

## Formatting and Style

- Follow Black formatting.
- Use isort with the Black profile: `isort --profile black .`
- Use Sphinx-style docstrings for public classes, functions, and modules.
- Prefer `pathlib.Path` and package-relative paths over hard-coded absolute paths.
- For package data access, prefer `carculator_utils.DATA_DIR` or `Path(__file__).resolve().parent / "data"` patterns already used in the codebase.
- Keep imports explicit and avoid adding expensive import-time side effects.
- Prefer vectorized `numpy`, `pandas`, and `xarray` operations when working with model arrays.

## Data Handling

The repository ships substantial package data. Be conservative when editing files under `carculator_utils/data/`.

- Preserve existing delimiters and formats, especially semicolon-delimited CSV files.
- Prefer text formats such as JSON, CSV, and YAML for new data when possible, matching `CONTRIBUTING.md`.
- If adding a new data file type or directory, update `MANIFEST.in` and verify that `setup.py` package data includes it.
- Keep schema-sensitive names stable: parameter names, powertrain labels, size labels, country codes, and xarray coordinates are part of the package's practical API.
- Do not regenerate or replace large IAM/LCIA matrix files unless the task explicitly requires it.

## Testing Guidance

- Add or update tests for behavior changes, especially parsing, interpolation, array shape/dimension changes, and data-loading logic.
- Use small fixtures in `tests/fixtures/` for new tests instead of depending on large production data where possible.
- For changes to bundled data loaders, include at least a smoke test that the loader returns the expected type and core dimensions/keys.
- Existing tests for `VehicleInputParameters` use fixture JSON directly; be careful when changing defaults or import behavior.

## Downstream Contracts

This package mostly provides parent classes and shared utilities for downstream packages such as `carculator`, `carculator_truck`, `carculator_two_wheeler`, and `carculator_bus`.

- Treat `VehicleModel`, `Inventory`, and `VehicleInputParameters` as inherited APIs, not only local implementation details.
- Keep parent constructors permissive enough for downstream subclasses; avoid calling overridable hooks before shared parent attributes are initialized.
- Preserve hook methods such as `set_all()`, `set_battery_chemistry()`, and `fill_in_A_matrix()` unless all downstream subclasses are checked.
- Maintain the core `xarray.DataArray` contract: dimensions `size`, `powertrain`, `parameter`, `year`, and `value`.
- When a parent class expects downstream data files, fail with explicit errors and document which subclass attributes or arguments should provide them.

## Documentation Guidance

- Update `docs/` for user-facing API or workflow changes.
- Keep docs examples aligned with the public API exported from `carculator_utils/__init__.py`.
- Build docs locally with `make -C docs html` when changing doc configuration, API docs, or example snippets.

## Git Hygiene

- Do not commit local editor files, `.DS_Store`, virtual environments, build artifacts, coverage output, or generated docs output.
- Leave unrelated dirty worktree changes untouched.
- Avoid broad refactors while making targeted scientific or data-model changes; these modules have implicit compatibility with downstream `carculator` packages.
