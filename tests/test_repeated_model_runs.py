"""A completed model must not feed derived outputs into its next run."""

import importlib
from copy import deepcopy

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters

CASES = [
    ("carculator", "Car", "Medium", ["BEV", "ICEV-p"], {}),
    ("carculator", "Car", "Medium", ["PHEV-p"], {}),
    ("carculator_truck", "Truck", "40t", ["BEV", "ICEV-d"], {"cycle": "Long haul"}),
    ("carculator_bus", "Bus", "13m-city", ["BEV-depot", "ICEV-d"], {}),
    ("carculator_two_wheeler", "TwoWheeler", "Scooter <4kW", ["BEV", "ICEV-p"], {}),
]


@pytest.fixture(params=CASES)
def case(request):
    package, prefix, size, powertrains, options = request.param
    module = pytest.importorskip(package)
    parameters = getattr(module, prefix + "InputParameters")()
    parameters.stochastic(2, seed=902)
    _, array = fill_xarray_from_input_parameters(
        parameters,
        scope={
            "size": [size],
            "powertrain": powertrains,
            "year": [2025, 2030],
        },
    )
    array = array.assign_coords(value=["first", "second"])
    return getattr(module, prefix + "Model"), array, options


@pytest.mark.family
def test_repeated_completion_is_identical_including_phevs(case):
    Model, array, options = case
    original = array.copy(deep=True)
    model = Model(array, **options)
    model.set_all()
    first = model.array.copy(deep=True)
    module = importlib.import_module(Model.__module__.split(".")[0])
    Inventory = getattr(module, "Inventory" + Model.__name__.removesuffix("Model"))
    impacts = Inventory(model, scenario="static").calculate_impacts()
    assert np.isfinite(impacts).all()
    energy = model.energy.copy(deep=True)
    model.set_all()
    xr.testing.assert_identical(model.array, first)
    xr.testing.assert_identical(model.energy, energy)
    xr.testing.assert_identical(array, original)
    xr.testing.assert_identical(
        Inventory(model, scenario="static").calculate_impacts(), impacts
    )
    # State also survives serializable copies and narrower/reordered scopes.
    model = deepcopy(model)
    model.array = model.array.sel(year=[2030], value=["second"])
    model.set_all()
    xr.testing.assert_allclose(
        model.array, first.sel(year=[2030], value=["second"]), rtol=2e-6
    )


@pytest.mark.family
def test_explicit_edits_to_completed_inputs_match_a_fresh_run(case):
    Model, array, options = case
    model = Model(array, **options)
    model.set_all()
    if "PHEV-p" in model.array.powertrain:
        model["glider base mass"] *= 1.1
        with pytest.raises(ValueError, match="component inputs"):
            model.set_all()
        return
    model["glider base mass"] *= 1.1
    model.set_all()
    changed = array.copy(deep=True)
    changed.loc[dict(parameter="glider base mass")] *= 1.1
    fresh = Model(changed, **options)
    fresh.set_all()
    xr.testing.assert_allclose(model.array, fresh.array, rtol=2e-6)
