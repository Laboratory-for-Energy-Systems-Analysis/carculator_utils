"""Electricity bills must use the same grid purchases as inventories."""

import importlib
import importlib.util
import os
from copy import deepcopy

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.model import VehicleModel

CASES = [
    (
        "carculator",
        "Car",
        "Medium",
        ["BEV", "ICEV-d", "HEV-d", "FCEV", "PHEV-p", "PHEV-d"],
        {},
    ),
    (
        "carculator_bus",
        "Bus",
        "13m-city",
        ["BEV-depot", "BEV-opp", "BEV-motion", "ICEV-d", "HEV-d", "FCEV"],
        {},
    ),
    (
        "carculator_truck",
        "Truck",
        "40t",
        ["BEV", "ICEV-d", "HEV-d", "FCEV", "PHEV-d"],
        {"cycle": "Long haul"},
    ),
    (
        "carculator_two_wheeler",
        "TwoWheeler",
        "Motorcycle 11-35kW",
        ["BEV", "ICEV-p"],
        {},
    ),
]
ELECTRIC = ["BEV", "BEV-depot", "BEV-opp", "BEV-motion", "PHEV-e"]


def load_package(name):
    if importlib.util.find_spec(name) is None:
        if os.environ.get("CARCULATOR_REQUIRE_FAMILY") == "1":
            pytest.fail(f"Required family package {name} missing")
        pytest.skip(f"Optional family package {name} missing")
    return importlib.import_module(name)


def price(model):
    if model.vehicle_type == "truck":
        share = model["share depot charging"]
        return model["energy cost per kWh (depot)"] * share + model[
            "energy cost per kWh (public)"
        ] * (1 - share)
    return model["energy cost per kWh"]


def completed_model(case, varied=False, utility_factor=None):
    name, prefix, size, powertrains, kwargs = case
    package = load_package(name)
    inputs = getattr(package, prefix + "InputParameters")()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs, scope={"size": [size], "powertrain": powertrains, "year": [2025, 2030]}
    )
    array = array.sel(year=[2030, 2025]).isel(value=[0, 0]).assign_coords(value=[9, 2])
    array.loc[dict(parameter="average passengers", value=2)] *= 1.1
    if varied:
        selected = [pt for pt in ELECTRIC if pt in array.powertrain.values]
        efficiencies = xr.DataArray(
            [[0.8, 1], [0.75, 0.9]],
            dims=("year", "value"),
            coords={"year": [2030, 2025], "value": [9, 2]},
        )
        array.loc[dict(parameter="charger efficiency", powertrain=selected)] = (
            efficiencies
        )
        tariffs = xr.DataArray(
            [[0, 0.2], [0.3, 0.4]], dims=("year", "value"), coords=efficiencies.coords
        )
        if prefix == "Truck":
            array.loc[dict(parameter="energy cost per kWh (depot)")] = tariffs
            array.loc[dict(parameter="energy cost per kWh (public)")] = tariffs * 2
            array.loc[dict(parameter="share depot charging", powertrain=selected)] = (
                xr.DataArray(
                    [[0, 0.5], [1, 0.25]],
                    dims=efficiencies.dims,
                    coords=efficiencies.coords,
                )
            )
        else:
            array.loc[dict(parameter="energy cost per kWh")] = tariffs
    original = array.copy(deep=True)
    kwargs = kwargs.copy()
    if prefix == "Car" and utility_factor is not None:
        kwargs["electric_utility_factor"] = {2030: utility_factor, 2025: utility_factor}
    model = getattr(package, prefix + "Model")(
        array, country="CH", drop_hybrids=False, **kwargs
    )
    model.set_all(
        **({"electric_utility_factor": utility_factor} if prefix == "Truck" else {})
    )
    xr.testing.assert_identical(array, original)
    return model, getattr(package, "Inventory" + prefix)


def assert_energy_bills(model):
    rate = price(model)
    divisor = model["average passengers"] if model.vehicle_type == "bus" else 1
    expected_electric = rate * model["electricity consumption"] / divisor
    electric = [pt for pt in ELECTRIC if pt in model.array.powertrain.values]
    np.testing.assert_allclose(
        model["energy cost"].sel(powertrain=electric),
        expected_electric.sel(powertrain=electric),
        rtol=2e-6,
        atol=1e-9,
    )
    # Combustion modes keep their previous cost convention.
    for pt in [
        pt
        for pt in model.array.powertrain.values
        if pt not in electric and pt not in ("PHEV-p", "PHEV-d")
    ]:
        expected = (
            rate.sel(powertrain=pt) * model["TtW energy"].sel(powertrain=pt) / 3600
        )
        if model.vehicle_type != "truck":
            charge = model["battery charge efficiency"].sel(powertrain=pt)
            expected /= charge.where(charge != 0, 1)
        if model.vehicle_type == "bus":
            expected /= divisor.sel(powertrain=pt)
        np.testing.assert_allclose(
            model["energy cost"].sel(powertrain=pt), expected, rtol=2e-6, atol=1e-9
        )
    for pt, combustion in [("PHEV-p", "PHEV-c-p"), ("PHEV-d", "PHEV-c-d")]:
        if pt not in model.array.powertrain.values:
            continue
        uf = model["electric utility factor"].sel(powertrain=pt)
        expected = expected_electric.sel(powertrain="PHEV-e") * uf + model[
            "energy cost"
        ].sel(powertrain=combustion) * (1 - uf)
        np.testing.assert_allclose(
            model["energy cost"].sel(powertrain=pt), expected, rtol=2e-6, atol=1e-9
        )


@pytest.mark.family
@pytest.mark.parametrize("case", CASES, ids=lambda case: case[0])
@pytest.mark.parametrize("varied", [False, True], ids=["default", "varied"])
def test_completed_charging_cost_matches_grid_purchase(case, varied):
    model, inventory_type = completed_model(case, varied)
    assert_energy_bills(model)
    retained = deepcopy(model)
    retained.drop_hybrid()
    inventory = inventory_type(retained, scenario="static", functional_unit="vkm")
    assert np.isfinite(inventory.calculate_impacts()).all()
    for pt in retained.array.powertrain.values:
        if not (pt.startswith("BEV") or pt in ("PHEV-p", "PHEV-d")):
            continue
        (column,) = inventory.find_input_indices(
            (f"transport, {model.vehicle_type}, {pt},",)
        )
        (row,) = inventory.get_vehicle_supply_indices(
            "electricity supply for electric vehicles", [column]
        )
        bought = -inventory.A[:, row, column, :]
        np.testing.assert_allclose(
            bought,
            retained["electricity consumption"]
            .sel(powertrain=pt)
            .isel(size=0)
            .transpose("value", "year"),
            rtol=2e-6,
        )
        tariff = price(model).sel(powertrain="PHEV-e" if pt.startswith("PHEV") else pt)
        billed = (
            xr.DataArray(
                bought,
                dims=("value", "year"),
                coords={"value": model.array.value, "year": model.array.year},
            )
            * tariff
        )
        if model.vehicle_type == "bus":
            billed /= model["average passengers"].sel(powertrain=pt)
        if pt.startswith("PHEV"):
            combustion = "PHEV-c-p" if pt.endswith("-p") else "PHEV-c-d"
            billed += model["energy cost"].sel(powertrain=combustion) * (
                1 - model["electric utility factor"].sel(powertrain=pt)
            )
        np.testing.assert_allclose(
            model["energy cost"].sel(powertrain=pt).transpose("value", "year", "size"),
            billed.transpose("value", "year", "size"),
            rtol=2e-6,
            atol=1e-9,
        )


@pytest.mark.family
@pytest.mark.parametrize("case", [CASES[0], CASES[2]], ids=lambda case: case[0])
@pytest.mark.parametrize("utility_factor", [0, 0.5, 1])
def test_phev_charging_cost_weighted_once(case, utility_factor):
    model, _ = completed_model(case, varied=True, utility_factor=utility_factor)
    assert_energy_bills(model)


def test_shared_charging_cost_preserves_fuel_costs_and_context():
    powertrains = ["BEV", "PHEV-e", "PHEV-p", "ICEV-p", "HEV-p", "FCEV"]
    array = xr.DataArray(
        np.zeros((1, 6, 2, 2, 2)),
        dims=("size", "powertrain", "parameter", "year", "value"),
        coords={
            "size": ["Medium"],
            "powertrain": powertrains,
            "parameter": ["energy cost", "electricity consumption"],
            "year": [2030, 2025],
            "value": [9, 2],
        },
    )
    array.loc[dict(parameter="energy cost")] = 123
    array.loc[dict(parameter="electricity consumption")] = 2
    original = array.copy(deep=True)
    model = VehicleModel(array)
    tariffs = xr.DataArray([0, 0.3], dims="year", coords={"year": [2030, 2025]})
    with model("BEV"):
        model.set_electricity_costs(tariffs)
        np.testing.assert_allclose(
            model["energy cost"].sel(powertrain="BEV"), [[[0, 0], [0.6, 0.6]]]
        )
    assert model["energy cost"].powertrain.values.tolist() == powertrains
    np.testing.assert_array_equal(
        model["energy cost"].sel(powertrain=powertrains[1:]), 123
    )
    model.set_electricity_costs(tariffs)
    for pt in ("BEV", "PHEV-e"):
        np.testing.assert_allclose(
            model["energy cost"].sel(powertrain=pt), [[[0, 0], [0.6, 0.6]]]
        )
    np.testing.assert_array_equal(
        model["energy cost"].sel(powertrain=powertrains[2:]), 123
    )
    xr.testing.assert_identical(array, original)
