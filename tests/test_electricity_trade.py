"""Consumption-mix conservation independently checked against two-country algebra."""

import numpy as np
import pytest
import xarray as xr

from carculator_utils.electricity_trade import consumption_mix


def network():
    generation = xr.DataArray(
        [[[10, 0]], [[0, 10]]],
        dims=("country", "year", "technology"),
        coords={"country": ["A", "B"], "year": [2025], "technology": ["coal", "wind"]},
        attrs={"unit": "TWh"},
    )
    trade = xr.DataArray(
        [[[0], [5]], [[4], [0]]],
        dims=("exporter", "importer", "year"),
        coords={"exporter": ["A", "B"], "importer": ["A", "B"], "year": [2025]},
        attrs={"unit": "TWh"},
    )
    return generation, trade


def test_reexports_conserve_each_technology_and_preserve_inputs():
    g, t = network()
    before = t.copy(deep=True)
    result = consumption_mix(g, t.sel(exporter=["B", "A"]), source="analytic example")
    np.testing.assert_allclose(
        result.sel(technology="coal").values.ravel(), [15 / 19, 5 / 19]
    )
    np.testing.assert_allclose(result.consumption.values.ravel(), [9, 11])
    np.testing.assert_allclose((result * result.consumption).sum("country"), [[10, 10]])
    xr.testing.assert_identical(t, before)


@pytest.mark.parametrize(
    "error",
    [
        "negative",
        "nan",
        "unit",
        "boundary",
        "diagonal",
        "exports",
        "cycle",
        "duplicate",
    ],
)
def test_invalid_network_fails(error):
    g, t = network()
    if error == "negative":
        g.values[0, 0, 0] = -1
    elif error == "nan":
        g = g.astype(float)
        g.values[0, 0, 0] = np.nan
    elif error == "unit":
        t.attrs["unit"] = "GWh"
    elif error == "boundary":
        t = t.assign_coords(exporter=["A", "C"])
    elif error == "diagonal":
        t.values[0, 0, 0] = 1
    elif error == "exports":
        t.values[0, 1, 0] = 100
    elif error == "cycle":
        g.values[:] = 0
        t.values[0, 1, 0] = 4
    else:
        g = g.assign_coords(country=["A", "A"])
    with pytest.raises(ValueError):
        consumption_mix(g, t, source="analytic example")


@pytest.mark.family
def test_labelled_consumption_mix_and_losses_reach_completed_car_inventory():
    car = pytest.importorskip("carculator")
    from carculator_utils.array import fill_xarray_from_input_parameters
    from carculator_utils.background_systems import BackgroundSystemModel

    inputs = car.CarInputParameters()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs, scope={"size": ["Medium"], "powertrain": ["BEV"], "year": [2025]}
    )
    model = car.CarModel(array)
    model.set_all()
    technologies = (
        BackgroundSystemModel().electricity_mix.coords["variable"].values.tolist()
    )
    g, t = network()
    result = consumption_mix(g, t, source="analytic example").sel(
        country="B", drop=True
    )
    # Map the example technologies explicitly to the inventory's technology names.
    result = result.assign_coords(technology=technologies[:2]).reindex(
        technology=technologies, fill_value=0
    )
    result = result.sel(technology=technologies[::-1])
    inventory = car.InventoryCar(
        model,
        scenario="static",
        background_configuration={
            "custom electricity mix": result,
            "electricity loss multiplier": 1.1,
            "electricity loss source": "analytic test, 1.1 kWh generated/kWh delivered",
        },
    )
    np.testing.assert_allclose(
        inventory.electricity_mix.sel(technology=technologies[0]), 5 / 19
    )
    assert inventory.electricity_losses == 1.1
    assert inventory.electricity_provenance["trade_method"] == "proportional sharing"
    (market,) = inventory.find_input_indices(
        ("electricity supply for fuel preparation",)
    )
    rows = [
        inventory.inputs[inventory.elec_map[technology]] for technology in technologies
    ]
    np.testing.assert_allclose(-inventory.A[0, rows, market, 0].sum(), 1.1)
    assert np.isfinite(inventory.calculate_impacts()).all()


@pytest.mark.parametrize("value", [-1, 0.9, np.inf, np.nan, [1.1], "invalid"])
def test_invalid_grid_loss_override_fails_before_inventory_changes(value):
    from carculator_utils.inventory import Inventory

    inventory = Inventory.__new__(Inventory)
    inventory.background_configuration = {"electricity loss multiplier": value}
    with pytest.raises(ValueError, match="Electricity loss multiplier"):
        inventory.create_electricity_mix_for_fuel_prep()
