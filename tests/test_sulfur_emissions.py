"""Year-specific sulfur concentrations and independently balanced SO2 flows."""

import importlib
import importlib.util
import os
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.inventory import Inventory


def sulfur_table():
    """Synthetic kg S/kg fuel; deliberately distinct years and a zero endpoint."""
    return xr.DataArray(
        np.array([[[10, 4], [5, 3], [0, 2]], [[20, 9], [15, 8], [12, 7]]]) / 1e6,
        dims=("country", "year", "fuel"),
        coords={
            "country": ["CH", "RER"],
            "year": [2020, 2025, 2030],
            "fuel": ["diesel", "petrol"],
        },
    )


@pytest.mark.parametrize("years", [[2025], [2030, 2020, 2025]])
@pytest.mark.parametrize("country", ["CH", "RER", "missing"])
@pytest.mark.parametrize("fuel", ["diesel", "petrol"])
def test_sulfur_lookup_preserves_years_and_fallback(years, country, fuel, capsys):
    inventory = Inventory.__new__(Inventory)
    inventory.scope = {"year": years}
    inventory.bs = SimpleNamespace(sulfur=sulfur_table())
    before = inventory.bs.sulfur.copy(deep=True)
    expected_ppm = {
        ("CH", "diesel"): {2020: 10, 2025: 5, 2030: 0},
        ("CH", "petrol"): {2020: 4, 2025: 3, 2030: 2},
        ("RER", "diesel"): {2020: 20, 2025: 15, 2030: 12},
        ("RER", "petrol"): {2020: 9, 2025: 8, 2030: 7},
    }[("RER" if country == "missing" else country, fuel)]

    result = inventory.get_sulfur_content(country, fuel)

    assert isinstance(result, xr.DataArray)
    assert result.dims == ("year",)
    assert result.year.values.tolist() == years
    np.testing.assert_allclose(result, [expected_ppm[year] / 1e6 for year in years])
    assert ("European average" in capsys.readouterr().out) == (country == "missing")
    result[:] = 123
    xr.testing.assert_identical(inventory.bs.sulfur, before)


@pytest.mark.parametrize("years", [[2025], [2030, 2020, 2025]])
@pytest.mark.parametrize("fuel", ["methane", "hydrogen"])
def test_fuel_without_sulfur_data_returns_labelled_zeros(years, fuel):
    inventory = Inventory.__new__(Inventory)
    inventory.scope = {"year": years}
    inventory.bs = SimpleNamespace(sulfur=sulfur_table())
    result = inventory.get_sulfur_content("CH", fuel)
    assert isinstance(result, xr.DataArray)
    assert result.dims == ("year",)
    assert result.year.values.tolist() == years
    np.testing.assert_array_equal(result, 0)


def minimal_inventory():
    inventory = Inventory.__new__(Inventory)
    inventory.scope = {"year": [2030, 2020, 2025]}
    inventory.vm = SimpleNamespace(country="CH", vehicle_type="car")
    inventory.bs = SimpleNamespace(sulfur=sulfur_table())
    inventory.inputs = {
        ("Sulfur dioxide", ("air",), "kilogram"): 0,
        ("transport, car, ICEV-d, Large", "CH", "kilometer", "transport"): 1,
        ("transport, car, BEV, Large", "CH", "kilometer", "transport"): 2,
        ("transport, car, ICEV-d, Small", "CH", "kilometer", "transport"): 3,
        ("transport, car, ICEV-g, Small", "CH", "kilometer", "transport"): 4,
    }
    inventory.rev_inputs = {value: key for key, value in inventory.inputs.items()}
    inventory.A = np.full((2, 5, 5, 3), 123.0)
    inventory.array = xr.DataArray(
        np.zeros((2, 2, 4, 3)),
        dims=("value", "parameter", "combined_dim", "year"),
        coords={
            "value": [9, 2],
            "parameter": ["fuel mass", "range"],
            "combined_dim": [
                "Large - ICEV-d",
                "Large - BEV",
                "Small - ICEV-d",
                "Small - ICEV-g",
            ],
            "year": inventory.scope["year"],
        },
    )
    inventory.array.loc[dict(parameter="range")] = 100
    inventory.array.loc[dict(parameter="fuel mass", combined_dim="Large - ICEV-d")] = [
        [10, 20, 30],
        [70, 80, 90],
    ]
    inventory.array.loc[dict(parameter="fuel mass", combined_dim="Small - ICEV-d")] = [
        [40, 0, 60],
        [100, 110, 120],
    ]
    inventory.array.loc[
        dict(parameter="range", combined_dim="Small - ICEV-d", value=9, year=2020)
    ] = 0
    return inventory


@pytest.mark.parametrize("reorder", [False, True])
def test_sulfur_emissions_align_years_samples_and_vehicle_columns(reorder):
    inventory = minimal_inventory()
    if reorder:
        inventory.array = inventory.array.transpose(
            "year", "combined_dim", "parameter", "value"
        )
    before = inventory.A.copy()
    inventory.add_sulphur_emissions("diesel", "EV-d", ["ICEV-d", "HEV-d", "PHEV-d"])
    # Each entry is kg fuel/km for the known 100-km batches above.
    fuel_per_km = np.array(
        [[[0.1, 0.2, 0.3], [0.4, 0, 0.6]], [[0.7, 0.8, 0.9], [1, 1.1, 1.2]]]
    )
    expected = before.copy()
    expected[:, 0, [1, 3], :] = -fuel_per_km * [0, 10e-6, 5e-6] * 2
    np.testing.assert_allclose(inventory.A, expected)
    inventory.add_sulphur_emissions("diesel", "EV-d", ["ICEV-d"])
    np.testing.assert_allclose(inventory.A, expected)


def test_zero_sulfur_clears_previous_emissions():
    inventory = minimal_inventory()
    inventory.bs.sulfur[:] = 0
    expected = inventory.A.copy()
    expected[:, 0, [1, 3], :] = 0
    inventory.add_sulphur_emissions("diesel", "EV-d", ["ICEV-d"])
    np.testing.assert_array_equal(inventory.A, expected)


def test_methane_keeps_zero_fuel_based_sulfur():
    inventory = minimal_inventory()
    expected = inventory.A.copy()
    expected[:, 0, 4, :] = 0
    inventory.add_sulphur_emissions("methane", "EV-g", ["ICEV-g"])
    np.testing.assert_array_equal(inventory.A, expected)


CASES = [
    (
        "carculator",
        "Car",
        "Medium",
        ["ICEV-p", "ICEV-d", "HEV-p", "HEV-d", "ICEV-g", "BEV"],
        {},
    ),
    (
        "carculator_bus",
        "Bus",
        "13m-city",
        ["ICEV-d", "HEV-d", "ICEV-g", "BEV-depot"],
        {},
    ),
    (
        "carculator_truck",
        "Truck",
        "40t",
        ["ICEV-d", "HEV-d", "ICEV-g", "BEV"],
        {"cycle": "Long haul"},
    ),
    (
        "carculator_two_wheeler",
        "TwoWheeler",
        "Motorcycle 11-35kW",
        ["ICEV-p", "BEV"],
        {},
    ),
]


@pytest.fixture(scope="module", params=CASES, ids=lambda case: case[0])
def completed_run(request):
    name, prefix, size, powertrains, kwargs = request.param
    if importlib.util.find_spec(name) is None:
        if os.environ.get("CARCULATOR_REQUIRE_FAMILY") == "1":
            pytest.fail(f"Required family package {name} missing")
        pytest.skip(f"Optional family package {name} missing")
    package = importlib.import_module(name)
    inputs = getattr(package, prefix + "InputParameters")()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={"size": [size], "powertrain": powertrains, "year": [2020, 2025, 2030]},
    )
    array = (
        array.sel(year=[2030, 2020, 2025])
        .isel(value=[0, 0])
        .assign_coords(value=[9, 2])
    )
    array.loc[dict(parameter="average passengers", value=2)] *= 1.1
    model = getattr(package, prefix + "Model")(array, country="CH", **kwargs)
    model.set_all()
    inventory_type = getattr(package, "Inventory" + prefix)
    inventory = inventory_type(model, scenario="static", functional_unit="vkm")
    impacts = inventory.calculate_impacts()
    assert np.isfinite(impacts).all()
    return model, inventory, inventory_type


@pytest.mark.family
def test_completed_inventory_sulfur_mass_balance(completed_run):
    model, inventory, _ = completed_run
    row = inventory.inputs[("Sulfur dioxide", ("air",), "kilogram")]
    # The bundled Swiss values are 10 ppm diesel, 8 ppm petrol in each test year.
    for powertrain in model.array.powertrain.values:
        (column,) = inventory.find_input_indices(
            (f"transport, {model.vehicle_type}, {powertrain},",)
        )
        if powertrain.endswith(("-d", "-p")):
            fuel = "diesel" if powertrain.endswith("-d") else "petrol"
            sulfur = 10e-6 if fuel == "diesel" else 8e-6
            (market,) = inventory.get_vehicle_supply_indices(
                f"fuel supply for {fuel} vehicles", [column]
            )
            fuel_mass = -inventory.A[:, market, column, :]
            assert (fuel_mass > 0).all()
            expected = fuel_mass * sulfur * 2
        else:
            expected = 0
        np.testing.assert_allclose(
            -inventory.A[:, row, column, :], expected, rtol=2e-6, atol=1e-12
        )


@pytest.mark.family
def test_same_completed_vehicle_has_same_sulfur_in_single_year_inventory(completed_run):
    model, full, inventory_type = completed_run
    single = deepcopy(model)
    single.array = single.array.sel(year=[2025])
    single.energy_storage["electric"] = {
        key: chemistry
        for key, chemistry in single.energy_storage["electric"].items()
        if key[2] == 2025
    }
    yi = list(model.array.year.values).index(2025)
    for components in single.fuel_blend.values():
        for component in components.values():
            for key in ("share", "lhv", "density", "CO2", "biogenic share"):
                value = np.asarray(component[key])
                if value.ndim:
                    component[key] = value[yi : yi + 1]
    inventory = inventory_type(single, scenario="static", functional_unit="vkm")
    impacts = inventory.calculate_impacts()
    assert np.isfinite(impacts).all()
    full_row = full.inputs[("Sulfur dioxide", ("air",), "kilogram")]
    row = inventory.inputs[("Sulfur dioxide", ("air",), "kilogram")]
    for powertrain in model.array.powertrain.values:
        search = (f"transport, {model.vehicle_type}, {powertrain},",)
        (column,) = inventory.find_input_indices(search)
        (full_column,) = full.find_input_indices(search)
        np.testing.assert_allclose(
            inventory.A[:, row, column, 0],
            full.A[:, full_row, full_column, yi],
            rtol=2e-6,
        )


@pytest.mark.family
@pytest.mark.export
def test_sulfur_survives_annual_exports(completed_run, tmp_path):
    pytest.importorskip("bw2io")
    from carculator_utils.export import rename_mapping

    model, _, inventory_type = completed_run
    selected = deepcopy(model)
    selected.array = selected.array.sel(value=[2])
    inventory = inventory_type(selected, scenario="static", functional_unit="vkm")
    before = inventory.A.copy()
    original_indices = inventory.inputs.copy()
    exports = inventory.export_lci(
        ecoinvent_version="3.10", format="bw2io", directory=tmp_path
    )
    assert len(exports) == 3
    renamed = rename_mapping("rename_powertrains.yaml")
    row = inventory.inputs[("Sulfur dioxide", ("air",), "kilogram")]
    for yi, (year, importer) in enumerate(zip(selected.array.year.values, exports)):
        assert importer.db_name.endswith(str(year))
        datasets = {dataset["name"]: dataset for dataset in importer.data}
        for powertrain in selected.array.powertrain.values:
            (column,) = inventory.find_input_indices(
                (f"transport, {selected.vehicle_type}, {powertrain},",)
            )
            name = inventory.rev_inputs[column][0].replace(
                powertrain, renamed[powertrain]
            )
            amount = sum(
                exchange["amount"]
                for exchange in datasets[name]["exchanges"]
                if exchange["type"] == "biosphere"
                and exchange["name"] == "Sulfur dioxide"
                and tuple(exchange["categories"]) == ("air",)
            )
            assert amount == pytest.approx(-inventory.A[0, row, column, yi], abs=1e-12)
    np.testing.assert_array_equal(inventory.A, before)
    assert inventory.inputs == original_indices
