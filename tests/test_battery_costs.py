"""Battery-price provenance and precedence, independently of vehicle sizing."""

import json
from copy import deepcopy

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.battery_costs import ENERGY_COST, POWER_COST, capture_inputs
from carculator_utils.model import VehicleModel
from carculator_utils.vehicle_input_parameters import VehicleInputParameters

CHEMISTRY_COST = ENERGY_COST + ", NMC-622"


@pytest.fixture
def input_class(tmp_path):
    records = {
        f"{name}-{year}": dict(
            name=name,
            amount=amount,
            loc=amount,
            uncertainty_type=1,
            sizes=["Medium"],
            powertrain=["BEV", "ICEV-p"],
            year=year,
        )
        for name, amount in [(ENERGY_COST, 100), (CHEMISTRY_COST, 70), (POWER_COST, 10)]
        for year in [2020, 2030]
    }
    path = tmp_path / "defaults.json"
    path.write_text(json.dumps(records))

    class Inputs(VehicleInputParameters):
        DEFAULT = path

    return Inputs


def build(input_class, parameters=None, sensitivity=False):
    inputs = input_class(parameters, extra=[])
    inputs.static()
    return fill_xarray_from_input_parameters(inputs, sensitivity=sensitivity)[1]


def project(array, **kwargs):
    storage = {
        "electric": {("BEV", "Medium", year): "NMC-622" for year in array.year.values}
    }
    model = VehicleModel(array, energy_storage=storage, **kwargs)
    model[ENERGY_COST] = 150
    model[POWER_COST] = 15
    model.apply_battery_cost_inputs(projected=True)
    return model


def test_array_edits_survive_interpolation_sample_selection_and_transpose(input_class):
    array = (
        build(input_class).isel(value=[0, 0]).assign_coords(value=["first", "second"])
    )
    array.loc[
        dict(parameter=ENERGY_COST, powertrain="BEV", year=2020, value="second")
    ] = 500
    array = array.interp(year=[2020, 2025, 2030]).sel(value=["second", "first"])
    array = array.transpose("value", "year", "parameter", "powertrain", "size")
    original = array.copy(deep=True)
    model = project(array)
    xr.testing.assert_identical(array, original)
    np.testing.assert_allclose(
        model[ENERGY_COST].sel(powertrain="BEV", value="second"), [[500, 300, 150]]
    )
    assert (model[ENERGY_COST].sel(value="first") == 150).all()
    assert (model[ENERGY_COST].sel(powertrain="ICEV-p") == 150).all()


@pytest.mark.parametrize("file_input", [False, True])
def test_custom_record_flags_interpolate_without_changing_untouched_endpoints(
    input_class, tmp_path, file_input
):
    parameters = json.loads(input_class.DEFAULT.read_text())
    parameters[f"{ENERGY_COST}-2020"]["amount"] = 500
    original = deepcopy(parameters)
    if file_input:
        path = tmp_path / "custom.json"
        path.write_text(json.dumps(parameters))
        array = build(input_class, path)
    else:
        array = build(input_class, parameters)
    model = project(array.interp(year=[2020, 2025, 2030]))
    np.testing.assert_allclose(
        model[ENERGY_COST].sel(powertrain="BEV").values.ravel(), [500, 300, 150]
    )
    assert parameters == original


def test_editing_sampled_values_before_array_creation_is_explicit(input_class):
    inputs = input_class(extra=[])
    inputs.stochastic(2, seed=7)
    inputs.values[f"{ENERGY_COST}-2020"][1] = 500
    array = fill_xarray_from_input_parameters(inputs)[1]
    model = project(array)
    np.testing.assert_allclose(
        model[ENERGY_COST].sel(year=2020, powertrain="BEV").values.ravel(), [150, 500]
    )


def test_explicit_generic_price_precedes_selected_chemistry_and_keeps_zero(input_class):
    array = build(input_class)
    array.loc[dict(parameter=CHEMISTRY_COST)] = 80
    array.loc[dict(parameter=ENERGY_COST, year=2020)] = 0
    model = project(array)
    assert model[ENERGY_COST].sel(powertrain="BEV", year=2020).item() == 0
    assert model[ENERGY_COST].sel(powertrain="BEV", year=2030).item() == 80
    assert model[ENERGY_COST].sel(powertrain="ICEV-p", year=2030).item() == 150


def test_generated_sensitivity_perturbs_projected_defaults(input_class):
    array = build(input_class, sensitivity=True).interp(year=[2020, 2025, 2030])
    model = project(array)
    for sample in [ENERGY_COST, CHEMISTRY_COST]:
        np.testing.assert_allclose(
            model[ENERGY_COST].sel(powertrain="BEV", value=sample), 165
        )
    np.testing.assert_allclose(model[ENERGY_COST].sel(value="reference"), 150)
    np.testing.assert_allclose(model[POWER_COST].sel(value=POWER_COST), 16.5)


def test_old_arrays_support_explicit_constructor_prices_and_input_ownership(
    input_class,
):
    array = build(input_class).reset_coords(drop=True)
    overrides = {ENERGY_COST: {("BEV", "Medium", 2020): 100}}
    original = deepcopy(overrides)
    model = project(array, battery_costs=overrides)
    assert model[ENERGY_COST].sel(powertrain="BEV", year=2020).item() == 100
    assert model[ENERGY_COST].sel(powertrain="BEV", year=2030).item() == 150
    assert overrides == original


def test_cost_reference_roundtrip_through_netcdf(input_class, tmp_path):
    array = build(input_class)
    array.loc[dict(parameter=ENERGY_COST, year=2020)] = 500
    path = tmp_path / "inputs.nc"
    array.to_netcdf(path)
    restored = xr.load_dataarray(path)
    xr.testing.assert_identical(restored, array)
    assert (project(restored)[ENERGY_COST].sel(year=2020) == 500).all()


@pytest.mark.parametrize("amount", [-1, np.nan, np.inf, True, "100", [100, 200]])
def test_invalid_constructor_price_fails_with_context(input_class, amount):
    with pytest.raises(ValueError, match="battery_costs.*finite"):
        project(
            build(input_class),
            battery_costs={ENERGY_COST: {("BEV", "Medium", 2020): amount}},
        )


def test_invalid_array_price_is_rejected(input_class):
    array = build(input_class)
    array.loc[dict(parameter=ENERGY_COST)] = -1
    with pytest.raises(ValueError, match="Explicit.*nonnegative"):
        capture_inputs(array)


def test_overrides_respect_context_selection(input_class):
    array = build(input_class)
    array.loc[dict(parameter=ENERGY_COST, powertrain="BEV")] = 500
    model = project(array)
    before = model.array.sel(powertrain="ICEV-p").copy(deep=True)
    with model("BEV"):
        model.set_battery_preferences()
        assert (model[ENERGY_COST] == 500).all()
    xr.testing.assert_identical(before, model.array.sel(powertrain="ICEV-p"))


def test_constructor_can_choose_an_unchanged_chemistry_price(input_class):
    array = build(input_class)
    model = project(
        array, battery_costs={CHEMISTRY_COST: {("BEV", "Medium", 2020): 70}}
    )
    assert model[ENERGY_COST].sel(powertrain="BEV", year=2020).item() == 70
    assert model[ENERGY_COST].sel(powertrain="BEV", year=2030).item() == 150


def test_constructor_accepts_scoped_sample_vectors_and_zero(input_class):
    array = (
        build(input_class).isel(value=[0, 0]).assign_coords(value=["first", "second"])
    )
    amounts = np.array([0, 500])
    model = project(
        array, battery_costs={ENERGY_COST: {("BEV", "Medium", 2020): amounts}}
    )
    amounts[:] = 999
    np.testing.assert_allclose(
        model[ENERGY_COST].sel(powertrain="BEV", year=2020).values.ravel(), [0, 500]
    )
