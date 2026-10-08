"""Cost projections must preserve each year and uncertainty-sample identity."""

import math

import numpy as np
import pytest
import xarray as xr

from carculator_utils.cost_uncertainty import FCEV_FACTOR, GENERAL_FACTOR
from carculator_utils.model import VehicleModel

ENERGY = "energy battery cost per kWh"
POWER = "power battery cost per kW"
TANK = "fuel tank cost per kg"
STACK = "fuel cell cost per kW"
GAS = "combustion powertrain cost per kW"
PARAMETERS = [ENERGY, POWER, TANK, STACK, GAS, "unrelated cost"]
CURVES = {
    ENERGY: (2.75e86, -0.0961, 50.59),
    POWER: (8.337e40, -0.0449, 11.17),
    TANK: (1.078e58, -0.0632, 343),
    STACK: (3.15e66, -0.0735, 23.9),
    GAS: (5.92e160, -0.1819, 26.76),
}


@pytest.fixture(
    params=[
        "shared",
        pytest.param("carculator", marks=pytest.mark.family),
        pytest.param("carculator_bus", marks=pytest.mark.family),
        pytest.param("carculator_two_wheeler", marks=pytest.mark.family),
    ]
)
def projection(request):
    name = request.param
    if name == "shared":
        return (
            VehicleModel,
            {
                "BEV": [ENERGY],
                "HEV-p": [POWER],
                "FCEV": [TANK, STACK, POWER],
                "ICEV-g": [POWER, GAS],
            },
            False,
        )
    module = pytest.importorskip(name)
    if name == "carculator":
        return (
            module.CarModel,
            {
                "BEV": [ENERGY],
                "PHEV-e": [ENERGY],
                "PHEV-c-p": [ENERGY, POWER],
                "HEV-p": [POWER],
                "FCEV": [TANK, STACK, POWER],
                "ICEV-g": [POWER, GAS],
            },
            False,
        )
    if name == "carculator_bus":
        return (
            module.BusModel,
            {
                "BEV-depot": [ENERGY],
                "BEV-opp": [ENERGY],
                "BEV-motion": [ENERGY],
                "HEV-d": [POWER],
                "FCEV": [TANK, STACK, POWER],
                "ICEV-g": [POWER, GAS],
            },
            True,
        )
    return (
        module.TwoWheelerModel,
        {"BEV": [ENERGY], "ICEV-p": [POWER], "Human": []},
        False,
    )


@pytest.mark.parametrize("years", [[2020, 2025, 2030], [2030, 2020, 2025], [2025]])
@pytest.mark.parametrize(
    "samples", [["a"], ["b", "reference", "a"], ["d", "b", "a", "c"]]
)
def test_each_projection_keeps_year_sample_and_vehicle_labels(
    projection, years, samples, monkeypatch
):
    Model, affected, bus = projection
    model = Model.__new__(Model)
    coords = dict(
        size=["first", "second"],
        powertrain=list(affected),
        parameter=PARAMETERS,
        year=years,
        value=samples,
    )
    model.array = xr.DataArray(
        np.full(tuple(len(v) for v in coords.values()), 17, dtype=np.float32),
        dims=list(coords),
        coords=coords,
    )
    # Distinct known draws reveal mixing even when there are more samples than
    # years; the factor belongs to a sample and must apply to every year.
    draws = dict(a=0.8, b=1.0, c=1.2, d=0.9)
    fcev_draws = dict(a=3.5, b=5.5, c=4.0, d=5.0)
    deterministic = len(samples) == 1 or "reference" in samples
    model.array = model.array.assign_coords(
        {
            GENERAL_FACTOR: (
                "value",
                [1 if deterministic else draws[s] for s in samples],
            ),
            FCEV_FACTOR: (
                "value",
                [5 if deterministic else fcev_draws[s] for s in samples],
            ),
        }
    )

    def unexpected_draw(*args, **kwargs):
        pytest.fail("Cost projection must reuse retained input draws.")

    monkeypatch.setattr(np.random, "triangular", unexpected_draw)
    monkeypatch.setattr(np.random, "default_rng", unexpected_draw)
    model.adjust_cost()
    expected = xr.full_like(model.array, 17)
    for pwt, parameters in affected.items():
        for parameter in parameters:
            a, b, c = CURVES[parameter]
            for year in years:
                for sample in samples:
                    if bus and parameter in (TANK, STACK):
                        factor = 5 if deterministic else fcev_draws[sample]
                    else:
                        factor = 1 if deterministic else draws[sample]
                    price = (a * math.exp(b * year) + c) * factor
                    if parameter == GAS and not bus:
                        price = min(price, 100)
                    expected.loc[
                        dict(
                            powertrain=pwt, parameter=parameter, year=year, value=sample
                        )
                    ] = price
    xr.testing.assert_allclose(model.array, expected)


@pytest.mark.parametrize(
    "parameter,pwt",
    [(ENERGY, "BEV"), (POWER, "HEV-p"), (TANK, "FCEV"), (STACK, "FCEV")],
)
def test_shared_projection_is_independent_of_sample_axis_order(parameter, pwt):
    model = VehicleModel.__new__(VehicleModel)
    coords = dict(
        size=["Medium"],
        powertrain=["BEV", "HEV-p", "FCEV"],
        parameter=[ENERGY, POWER, TANK, STACK],
        year=[2030, 2020, 2025],
        value=["other", "reference"],
    )
    model.array = xr.DataArray(
        np.zeros(tuple(len(v) for v in coords.values())),
        dims=list(coords),
        coords=coords,
    ).transpose("value", "year", "parameter", "powertrain", "size")
    model.adjust_cost()
    a, b, c = CURVES[parameter]
    for year in coords["year"]:
        np.testing.assert_allclose(
            model[parameter].sel(powertrain=pwt, year=year),
            a * math.exp(b * year) + c,
        )


def test_shared_fcev_years_match_separate_runs():
    coords = dict(
        size=["Medium"],
        powertrain=["FCEV"],
        parameter=PARAMETERS,
        year=[2020, 2025, 2030],
        value=["reference", "other"],
    )
    array = xr.DataArray(
        np.zeros(tuple(len(v) for v in coords.values())),
        dims=list(coords),
        coords=coords,
    )
    combined = VehicleModel.__new__(VehicleModel)
    combined.array = array.copy(deep=True)
    combined.adjust_cost()
    for year in array.year.values:
        separate = VehicleModel.__new__(VehicleModel)
        separate.array = array.sel(year=[year]).copy(deep=True)
        separate.adjust_cost()
        xr.testing.assert_identical(combined.array.sel(year=[year]), separate.array)


@pytest.mark.family
@pytest.mark.parametrize("mode", ["static", "sensitivity", "seeded"])
def test_shared_fcev_projection_matches_completed_car_costs_and_inventory(mode):
    """Exercise the inherited hook through a real sizing/cost/LCIA workflow."""
    car = pytest.importorskip("carculator")

    class SharedCostCar(car.CarModel):
        adjust_cost = VehicleModel.adjust_cost

    inputs = car.CarInputParameters()
    if mode == "seeded":
        inputs.stochastic(3, seed=42)
    else:
        inputs.static()
    _, array = car.fill_xarray_from_input_parameters(
        inputs,
        scope={"size": ["Medium"], "powertrain": ["FCEV"], "year": [2020, 2025, 2030]},
        sensitivity=mode == "sensitivity",
    )
    if mode == "sensitivity":
        array = array.sel(value=[STACK, "reference", TANK])
    elif mode == "seeded":
        array = array.sel(value=[2, 0, 1])
    array = array.sel(year=[2030, 2020, 2025])
    original = array.copy(deep=True)
    expected = car.CarModel(array)
    expected.set_all()
    actual = SharedCostCar(array)
    actual.set_all()
    xr.testing.assert_identical(array, original)
    xr.testing.assert_identical(actual.array, expected.array)
    xr.testing.assert_identical(actual.energy, expected.energy)

    # Check the price units in the downstream component-cost calculation:
    # tank cost uses kg of stored hydrogen, stack cost uses fuel-cell kW,
    # and both completed component costs include the vehicle markup.
    for component, amount, price in (
        ("fuel tank cost", "fuel mass", TANK),
        ("fuel cell cost", "fuel cell power", STACK),
    ):
        np.testing.assert_allclose(
            actual[component],
            actual[amount] * actual[price] * actual["markup factor"],
        )
        assert (actual[component] > 0).all()

    if mode == "seeded":
        inventories = [
            car.InventoryCar(m, scenario="static", functional_unit="vkm")
            for m in (expected, actual)
        ]
        impacts = [inventory.calculate_impacts() for inventory in inventories]
        np.testing.assert_array_equal(inventories[0].A, inventories[1].A)
        xr.testing.assert_identical(impacts[0], impacts[1])
        assert np.isfinite(impacts[1]).all()
