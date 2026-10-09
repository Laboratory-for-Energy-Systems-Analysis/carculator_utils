"""The empirical bus HVAC curve supports only its fixed cabin setting."""

import importlib
import os
from copy import deepcopy

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.energy_consumption import EnergyConsumptionModel

UNSUPPORTED = [15, 25, 19.9, 20.1, np.nextafter(20.0, 21.0), [20] * 11 + [21]]
MALFORMED = [None, np.nan, np.inf, [20], [[20] * 12], "unavailable"]


def energy_model(**kwargs):
    return EnergyConsumptionModel(
        "bus", ["13m-city"], ["BEV-depot"], np.array([0, 10, 0]), None, **kwargs
    )


def hvac_loads(model):
    return model.calculate_hvac_energy(
        xr.DataArray(18000.0), xr.DataArray(2750.0), xr.DataArray(500.0)
    )


@pytest.mark.parametrize("temperature", UNSUPPORTED + MALFORMED)
def test_direct_energy_constructor_rejects_unsupported_cabin_temperature(temperature):
    with pytest.raises(ValueError, match="Indoor temperature.*20"):
        energy_model(indoor_temperature=temperature)


@pytest.mark.parametrize("temperature", UNSUPPORTED + MALFORMED)
def test_hvac_calculation_rejects_later_cabin_temperature_change(temperature):
    model = energy_model(ambient_temperature=0)
    model.indoor_temperature = temperature
    with pytest.raises(ValueError, match="Indoor temperature.*20"):
        hvac_loads(model)


@pytest.mark.parametrize("temperature", [20, 20.0, np.full(12, 20.0)])
@pytest.mark.parametrize(
    "ambient,expected",
    [(-10, [0, 5220, 0, 500]), (20, [1440, 0, 0, 0]), (30, [8100, 0, 2750, 0])],
)
def test_supported_cabin_setting_preserves_existing_hvac_loads(
    temperature, ambient, expected
):
    requested = deepcopy(temperature)
    model = energy_model(ambient_temperature=ambient, indoor_temperature=requested)
    # Independent expectations from the existing ambient-temperature curve,
    # before COP/efficiency: 29%, 8% and 45% of the 18 kW HVAC rating.
    np.testing.assert_allclose(np.asarray(hvac_loads(model)).ravel(), expected)
    np.testing.assert_array_equal(requested, temperature)


@pytest.fixture(scope="module")
def bus_inputs():
    name = "carculator_bus"
    if importlib.util.find_spec(name) is None:
        if os.environ.get("CARCULATOR_REQUIRE_FAMILY") == "1":
            pytest.fail(f"Required family package {name} missing")
        pytest.skip(f"Optional family package {name} missing")
    package = importlib.import_module(name)
    inputs = package.BusInputParameters()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={
            "size": ["13m-city"],
            "powertrain": ["ICEV-d", "FCEV", "BEV-depot"],
            "year": [2020, 2025, 2030],
        },
    )
    array = (
        array.sel(year=[2030, 2020, 2025])
        .isel(value=[0, 0])
        .assign_coords(value=[9, 2])
    )
    array.loc[dict(parameter="average passengers", value=2)] *= 1.1
    return package, array


@pytest.mark.family
@pytest.mark.parametrize("temperature", UNSUPPORTED)
def test_bus_rejects_unsupported_cabin_temperature_before_sizing(
    bus_inputs, temperature
):
    package, array = bus_inputs
    before = array.copy(deep=True)
    requested = deepcopy(temperature)
    with pytest.raises(ValueError, match="Indoor temperature.*20"):
        package.BusModel(array, indoor_temperature=requested)
    np.testing.assert_array_equal(requested, temperature)
    xr.testing.assert_identical(array, before)


@pytest.mark.family
@pytest.mark.parametrize("ambient", [None, 0, np.linspace(-5.5, 30.5, 12)])
def test_completed_bus_default_agrees_with_explicit_fixed_cabin_setting(
    bus_inputs, ambient
):
    package, array = bus_inputs
    before = array.copy(deep=True)
    requested_ambient = deepcopy(ambient)
    requested_indoor = np.full(12, 20.0)
    baseline = package.BusModel(array, ambient_temperature=requested_ambient)
    baseline.set_all()
    explicit = package.BusModel(
        array,
        ambient_temperature=requested_ambient,
        indoor_temperature=requested_indoor,
    )
    explicit.set_all()
    xr.testing.assert_identical(array, before)
    np.testing.assert_array_equal(requested_indoor, np.full(12, 20.0))
    np.testing.assert_array_equal(requested_ambient, ambient)
    xr.testing.assert_allclose(baseline.array, explicit.array)
    assert np.isfinite(explicit["TtW energy"]).all()
    assert (explicit["TtW energy"] > 0).all()
    assert (explicit["electricity consumption"].sel(powertrain="BEV-depot") > 0).all()
    assert (explicit["fuel consumption"].sel(powertrain=["ICEV-d", "FCEV"]) > 0).all()
    original = package.InventoryBus(baseline, scenario="static", functional_unit="vkm")
    retained = package.InventoryBus(explicit, scenario="static", functional_unit="vkm")
    impacts = retained.calculate_impacts()
    assert np.isfinite(impacts).all()
    np.testing.assert_array_equal(original.A, retained.A)
    xr.testing.assert_allclose(original.calculate_impacts(), impacts)
