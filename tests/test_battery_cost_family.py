"""Completed model/cost/LCIA checks for explicit battery unit prices."""

import importlib
import importlib.util
import json
from copy import deepcopy

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.battery_costs import ENERGY_COST, POWER_COST

pytestmark = pytest.mark.family
CASES = [
    ("carculator", "Car", "Medium", "BEV", "NMC-811"),
    ("carculator_bus", "Bus", "13m-city", "BEV-depot", "NMC-622"),
    ("carculator_two_wheeler", "TwoWheeler", "Scooter <4kW", "BEV", "NMC-811"),
]


@pytest.fixture(params=CASES, ids=lambda c: c[0])
def case(request):
    name, prefix, size, powertrain, chemistry = request.param
    if importlib.util.find_spec(name) is None:
        pytest.skip(f"Optional family package {name} missing")
    package = importlib.import_module(name)
    return (
        getattr(package, prefix + "InputParameters"),
        getattr(package, prefix + "Model"),
        getattr(package, "Inventory" + prefix),
        size,
        powertrain,
        chemistry,
    )


def inputs(case, years=(2025,), parameters=None):
    Input, _, _, size, powertrain, _ = case
    ip = Input(parameters=parameters)
    ip.static()
    return fill_xarray_from_input_parameters(
        ip, scope={"size": [size], "powertrain": [powertrain], "year": list(years)}
    )[1]


def complete(case, array, **kwargs):
    model = case[1](array, **kwargs)
    model.set_all()
    return model


@pytest.mark.parametrize("source", ["generic", "chemistry", "records", "constructor"])
def test_battery_price_changes_reach_purchase_and_replacement_costs(case, source):
    Input, _, Inventory, size, pwt, chemistry = case
    models = []
    # NMC-811's packaged chemistry input is already 100. A no-op array
    # assignment cannot signal intent; the constructor route covers that case.
    low_price = 125 if source == "chemistry" else 100
    for price in [low_price, 500]:
        kwargs = {}
        if source == "records":
            records = json.loads(Input.DEFAULT.read_text())
            for record in records.values():
                if record["name"] == ENERGY_COST and record["year"] == 2025:
                    record.update(amount=price, loc=price, uncertainty_type=1)
                    record.pop("minimum", None)
                    record.pop("maximum", None)
            array = inputs(case, parameters=records)
        else:
            array = inputs(case)
            if source == "constructor":
                kwargs = {"battery_costs": {ENERGY_COST: {(pwt, size, 2025): price}}}
            else:
                parameter = (
                    ENERGY_COST
                    if source == "generic"
                    else f"{ENERGY_COST}, {chemistry}"
                )
                if parameter not in array.parameter.values:
                    array = array.reindex(
                        parameter=[*array.parameter.values, parameter], fill_value=0
                    )
                array.loc[dict(parameter=parameter)] = price
        original = array.copy(deep=True)
        original_kwargs = deepcopy(kwargs)
        model = complete(case, array, **kwargs)
        xr.testing.assert_identical(array, original)
        assert kwargs == original_kwargs
        np.testing.assert_allclose(model[ENERGY_COST], price)
        models.append(model)

    low, high = models
    delta = low["electric energy stored"] * (500 - low_price) * low["markup factor"]
    np.testing.assert_allclose(
        high["purchase cost"] - low["purchase cost"], delta, rtol=2e-6, atol=0.01
    )
    np.testing.assert_allclose(
        high["component replacement cost"] - low["component replacement cost"],
        delta * low["battery lifetime replacements"],
        rtol=2e-6,
        atol=0.01,
    )
    assert (high["total cost per km"] > low["total cost per km"]).all()
    for parameter in [
        "driving mass",
        "electric energy stored",
        "TtW energy",
        "electricity consumption",
        "battery lifetime replacements",
    ]:
        np.testing.assert_array_equal(high[parameter], low[parameter])
    if source == "generic":
        inventories = [
            Inventory(model, scenario="static", functional_unit="vkm")
            for model in models
        ]
        impacts = [inv.calculate_impacts() for inv in inventories]
        np.testing.assert_array_equal(inventories[0].A, inventories[1].A)
        xr.testing.assert_identical(impacts[0], impacts[1])


def test_untouched_defaults_retain_legacy_results(case):
    array = inputs(case, years=(2020, 2025, 2030))

    class Legacy(case[1]):
        # Equivalent to the original unconditional cost-adjustment behavior.
        def apply_battery_cost_inputs(self, projected=False):
            pass

    old = Legacy(array)
    old.set_all()
    model = complete(case, array)
    xr.testing.assert_identical(model.array, old.array)
    expected = 2.75e86 * np.exp(-0.0961 * model.array.year.values) + 50.59
    np.testing.assert_allclose(model[ENERGY_COST].values.ravel(), expected, rtol=1e-6)


def test_scoped_sample_prices_preserve_other_years_and_costs(case):
    _, _, _, size, pwt, _ = case
    array = inputs(case, years=(2020, 2025, 2030))
    array = array.isel(value=[0, 0]).assign_coords(value=["reference", "priced"])
    original = array.copy(deep=True)
    array.loc[dict(parameter=ENERGY_COST, year=2025, value="priced")] = 500
    model = complete(case, array)
    default = complete(case, original)
    np.testing.assert_allclose(model[ENERGY_COST].sel(year=2025, value="priced"), 500)
    xr.testing.assert_identical(
        model.array.sel(year=[2020, 2030]), default.array.sel(year=[2020, 2030])
    )
    xr.testing.assert_identical(
        model.array.sel(value="reference"), default.array.sel(value="reference")
    )


def test_multiyear_battery_cost_sensitivity_preserves_static_reference(case):
    Input, _, _, size, pwt, _ = case
    ip = Input()
    ip.static()
    _, array = fill_xarray_from_input_parameters(
        ip,
        sensitivity=True,
        scope={"size": [size], "powertrain": [pwt], "year": [2020, 2025, 2030]},
    )
    # Keep only the reference and cost perturbation; unrelated sensitivities
    # need not take part in this cost-contract regression.
    array = array.sel(value=["reference", ENERGY_COST])
    model = complete(case, array)
    static = complete(case, inputs(case, years=(2020, 2025, 2030)))
    reference = model[ENERGY_COST].sel(value="reference")
    np.testing.assert_allclose(reference, static[ENERGY_COST].squeeze("value"))
    np.testing.assert_allclose(
        model.array.sel(value="reference").values,
        static.array.squeeze("value").values,
        rtol=1e-6,
        atol=1e-5,
    )
    np.testing.assert_allclose(
        model[ENERGY_COST].sel(value=ENERGY_COST), reference * 1.1, rtol=1e-6
    )
    expected = (
        model["electric energy stored"].sel(value="reference")
        * reference
        * 0.1
        * model["markup factor"].sel(value="reference")
    )
    np.testing.assert_allclose(
        model["purchase cost"].sel(value=ENERGY_COST)
        - model["purchase cost"].sel(value="reference"),
        expected,
        rtol=2e-5,
        atol=0.02,
    )


def test_stochastic_defaults_preserve_existing_cost_draws(case):
    Input, Model, _, size, pwt, _ = case
    ip = Input()
    ip.stochastic(3, seed=42)
    _, array = fill_xarray_from_input_parameters(
        ip, scope={"size": [size], "powertrain": [pwt], "year": [2025]}
    )

    class Legacy(Model):
        def apply_battery_cost_inputs(self, projected=False):
            pass

    # Cost projection still uses the global RNG. Pair draws without changing
    # the caller's global state or claiming the input seed controls these costs.
    state = np.random.get_state()
    try:
        np.random.seed(17)
        old = Legacy(array)
        old.set_all()
        np.random.seed(17)
        model = complete(case, array)
    finally:
        np.random.set_state(state)
    xr.testing.assert_identical(model.array, old.array)


def test_power_battery_price_reaches_completed_hybrid_purchase():
    car = pytest.importorskip("carculator")
    ip = car.CarInputParameters()
    ip.static()
    _, array = fill_xarray_from_input_parameters(
        ip, scope={"size": ["Medium"], "powertrain": ["HEV-p"], "year": [2025]}
    )
    models = []
    for price in (10, 50):
        model = car.CarModel(
            array, battery_costs={POWER_COST: {("HEV-p", "Medium", 2025): price}}
        )
        model.set_all()
        np.testing.assert_allclose(model[POWER_COST], price)
        models.append(model)
    low, high = models
    assert (low["battery power"] > 0).all()
    np.testing.assert_allclose(
        high["purchase cost"] - low["purchase cost"],
        40 * low["battery power"] * low["markup factor"],
        rtol=2e-5,
        atol=0.01,
    )


def test_phev_component_prices_reach_combined_cost_and_reject_discarded_override():
    car = pytest.importorskip("carculator")
    ip = car.CarInputParameters()
    ip.static()
    _, array = fill_xarray_from_input_parameters(
        ip, scope={"size": ["Medium"], "powertrain": ["PHEV-p"], "year": [2025]}
    )
    with pytest.raises(ValueError, match="PHEV aggregation"):
        car.CarModel(
            array, battery_costs={ENERGY_COST: {("PHEV-p", "Medium", 2025): 500}}
        )
    models = []
    for price in (100, 500):
        model = car.CarModel(
            array,
            battery_costs={
                ENERGY_COST: {
                    (pwt, "Medium", 2025): price for pwt in ("PHEV-e", "PHEV-c-p")
                }
            },
        )
        model.set_all()
        np.testing.assert_allclose(model[ENERGY_COST].sel(powertrain="PHEV-p"), price)
        models.append(model)
    low, high = models
    np.testing.assert_allclose(
        (high["purchase cost"] - low["purchase cost"]).sel(powertrain="PHEV-p"),
        (400 * low["electric energy stored"] * low["markup factor"]).sel(
            powertrain="PHEV-p"
        ),
        rtol=2e-5,
        atol=0.01,
    )


def test_truck_native_costs_and_completed_inventory_remain_unchanged():
    truck = pytest.importorskip("carculator_truck")
    ip = truck.TruckInputParameters()
    ip.static()
    _, array = fill_xarray_from_input_parameters(
        ip, scope={"size": ["40t"], "powertrain": ["BEV"], "year": [2025]}
    )

    class Legacy(truck.TruckModel):
        def apply_battery_cost_inputs(self, projected=False):
            pass

    old = Legacy(array)
    old.set_all()
    model = truck.TruckModel(array)
    model.set_all()
    xr.testing.assert_identical(model.array, old.array)
    inventories = [
        truck.InventoryTruck(m, scenario="static", functional_unit="vkm")
        for m in (old, model)
    ]
    impacts = [inv.calculate_impacts() for inv in inventories]
    np.testing.assert_array_equal(inventories[0].A, inventories[1].A)
    xr.testing.assert_identical(impacts[0], impacts[1])
