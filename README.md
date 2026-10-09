# carculator_utils

Shared physics, parameter handling, background systems, inventories and export machinery for the carculator vehicle models.

[![Installed artifacts](https://github.com/Laboratory-for-Energy-Systems-Analysis/carculator_utils/actions/workflows/main.yml/badge.svg?branch=master)](https://github.com/Laboratory-for-Energy-Systems-Analysis/carculator_utils/actions/workflows/main.yml)
[![PyPI](https://img.shields.io/pypi/v/carculator_utils)](https://pypi.org/project/carculator_utils/)

Developed at the [Paul Scherrer Institute](https://www.psi.ch/en).
This checkout prepares **1.3.6**; see [CHANGELOG.md](https://github.com/Laboratory-for-Energy-Systems-Analysis/carculator_utils/blob/master/CHANGELOG.md) for release status and changes.

## Installation

Use **Python 3.12** (`>=3.12,<3.13`) and a fresh environment. The shared runtime
requires NumPy `>=1.26.4,<2`.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

On Windows, activate with `.venv\Scripts\activate`. After publication, install
this release from PyPI:

```bash
python -m pip install "carculator_utils==1.3.6"
```

Before publication, use the matching source checkouts as described under development.
Core calculations use bundled resources and need no Brightway project, ecoinvent
installation or network access. Brightpath supplies Brightway Excel, SimaPro CSV
and openLCA JSON-LD export as a runtime dependency. To select the tested legacy
Brightway stack:

```bash
python -m pip install "carculator_utils[excel,brightway]==1.3.6"
```

The Brightway extra supports the legacy stack (`bw2io<0.9`, `bw2data<4`,
`bw2calc<2`). Exports default to **ecoinvent 3.12 cutoff**; importing them
requires that background database in the destination tool. Legacy 3.9/3.10
targets reject newly introduced suppliers without a reviewed backward mapping.
openLCA export currently supplies foreground processes and requires manual
background/elementary-flow linking before calculation. See the
[export guide](docs/inventory_export.rst) for examples and compatibility details.

## Vehicle packages

| Package | Prepared version |
| --- | --- |
| `carculator_utils` | 1.3.6 |
| `carculator` | 1.9.6 |
| `carculator_truck` | 0.5.1 |
| `carculator_bus` | 0.1.1 |
| `carculator_two_wheeler` | 0.1.1 |

## Quick start

```python
from carculator_utils.background_systems import BackgroundSystemModel

background = BackgroundSystemModel()
print(sorted(background.fuel_specs))
```

This shared package has no standalone default vehicle. Choose a vehicle package from the family table below for complete model/LCIA runs.

## Modelling and validation

The bundled A matrix and all 57 B matrices were rebuilt with **premise 2.5.4**
and **ecoinvent 3.12 cutoff**. B contains precomputed LCIA coefficients.
See the [rebuild and validation guide](docs/background_rebuild.rst) for scenarios,
reproducible scripts and source hashes. The former `NMC-523` option is now
`NMC-532`, using the actual 5:3:2 chemistry; update custom chemistry selections.

Explicit battery unit prices now survive chemistry selection and cost adjustment.
Use `battery_costs` for scoped prices, including zero or values equal to packaged
defaults; see [battery-cost inputs and precedence](docs/battery_costs.rst).

The vehicle models include native **2025** parameters and documented temporal
extensions. These combine engineering priors and selected calibration evidence;
they are not independent measurements for every vehicle configuration.

`TtW energy` is in kJ/km. For BEVs it is net stored-energy depletion;
`model.battery_terminal_energy` reports terminal DC separately, while
`electricity consumption` is grid electricity in kWh/km. Identify the measurement
boundary before comparing energy outputs. Availability-masked zeroes do not
represent physically zero consumption.

Supported background scenarios are `SSP2-NPi`, `SSP2-PkBudg1000`,
`SSP2-PkBudg650`, and `static`. ReCiPe supports midpoint/endpoint and EF midpoint.
Use fresh model instances for independent cases. `inputs.stochastic(n, seed=...)`
seeds parameter sampling, not every downstream cost adjustment.

See [validation and limitations](https://github.com/Laboratory-for-Energy-Systems-Analysis/carculator_utils/blob/master/docs/validity.rst), [migration notes](https://github.com/Laboratory-for-Energy-Systems-Analysis/carculator_utils/blob/master/docs/release.rst)
and the [documentation](https://github.com/Laboratory-for-Energy-Systems-Analysis/carculator_utils/tree/master/docs).

## Development and release

Use matching sibling checkouts, especially `carculator_utils` **1.3.6 or newer**:

```bash
python -m pip install -e ".[test,docs,excel,brightway]"
python -m pip check
python -m pytest
python -m sphinx -b html docs docs/_build/html
```

The `docs` extra includes the extensions used by this repository.
See [RELEASING.md](https://github.com/Laboratory-for-Energy-Systems-Analysis/carculator_utils/blob/master/RELEASING.md) for artifact verification, release order and publication.

## Support and license

Contact [carculator@psi.ch](mailto:carculator@psi.ch) or open an [issue](https://github.com/Laboratory-for-Energy-Systems-Analysis/carculator_utils/issues).
Maintained by [Romain Sacchi](https://github.com/romainsacchi), with contributions
from the carculator development team. See [contributing](https://github.com/Laboratory-for-Energy-Systems-Analysis/carculator_utils/blob/master/CONTRIBUTING.md).
Licensed under [BSD-3-Clause](https://github.com/Laboratory-for-Energy-Systems-Analysis/carculator_utils/blob/master/LICENSE).
