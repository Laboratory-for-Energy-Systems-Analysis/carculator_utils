"""Completed family fuel balances survive year selection and reordering."""

import importlib
import importlib.util
import os
from copy import deepcopy

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.background_systems import BackgroundSystemModel

CASES = [
    (
        "carculator",
        "Car",
        "Medium",
        ["ICEV-p", "ICEV-d", "ICEV-g", "PHEV-p", "PHEV-d", "FCEV", "BEV"],
        {},
    ),
    (
        "carculator_bus",
        "Bus",
        "13m-city",
        ["ICEV-d", "ICEV-g", "FCEV", "BEV-depot"],
        {},
    ),
    (
        "carculator_truck",
        "Truck",
        "40t",
        ["ICEV-d", "ICEV-g", "PHEV-d", "FCEV", "BEV"],
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
FUELS = {
    "petrol": ("petrol", "petrol - bioethanol - sugarbeet"),
    "diesel": ("diesel", "diesel - biodiesel - cooking oil"),
    "methane": ("methane", "methane - biomethane - sewage sludge"),
    "hydrogen": ("hydrogen - smr - natural gas", "hydrogen - electrolysis - PEM"),
}
PT_FUEL = {
    "ICEV-p": "petrol",
    "ICEV-d": "diesel",
    "ICEV-g": "methane",
    "PHEV-p": "petrol",
    "PHEV-d": "diesel",
    "FCEV": "hydrogen",
}


@pytest.fixture(
    scope="module",
    params=[(c, custom) for c in CASES for custom in [False, True]],
    ids=lambda p: f"{p[0][0]}-{'custom' if p[1] else 'default'}",
)
def completed(request):
    (name, prefix, size, pts, kwargs), custom = request.param
    if importlib.util.find_spec(name) is None:
        if os.environ.get("CARCULATOR_REQUIRE_FAMILY") == "1":
            pytest.fail(f"Required family package {name} missing")
        pytest.skip(f"Optional family package {name} missing")
    package = importlib.import_module(name)
    inputs = getattr(package, prefix + "InputParameters")()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs, scope={"size": [size], "powertrain": pts, "year": [2025, 2030]}
    )
    array = (
        array.sel(year=[2030, 2025])
        .isel(value=[0, 0])
        .assign_coords(value=["reference", "more-load"])
    )
    array.loc[dict(parameter="average passengers", value="more-load")] *= 1.1
    array.loc[dict(parameter="cargo mass", value="more-load")] *= 1.1
    specs, blends = BackgroundSystemModel().fuel_specs, None
    if custom:
        blends = {}
        for fuel in {PT_FUEL[pt] for pt in pts if pt in PT_FUEL}:
            blends[fuel] = {}
            for role, name, shares in zip(
                ("primary", "secondary"), FUELS[fuel], ([0.5, 0.9], [0.5, 0.1])
            ):
                component = {"type": name, "share": shares}
                for field, catalog in [
                    ("lhv", "lhv"),
                    ("density", "density"),
                    ("CO2", "co2"),
                ]:
                    component[field] = (
                        specs[name][catalog] * np.array([0.95, 1.05])
                    ).tolist()
                component["biogenic share"] = (
                    [0.2, 0] if role == "primary" else [0.9, 1]
                )
                blends[fuel][role] = component
    before = deepcopy(blends)
    model = getattr(package, prefix + "Model")(
        array, country="CH", fuel_blend=blends, **kwargs
    )
    model.set_all()
    assert blends == before
    cls = getattr(package, "Inventory" + prefix)
    inventory = cls(model, scenario="static")
    impacts = inventory.calculate_impacts()
    assert np.isfinite(impacts).all()
    return model, cls, impacts


def properties_for_years(source, years):
    """Independent reference: look up each value in the source model's year list."""
    original_years = list(source.array.year.values)
    indices = [original_years.index(year) for year in years]
    return {
        fuel: {
            role: {
                field: np.broadcast_to(component[field], (len(original_years),))[
                    indices
                ]
                for field in ("share", "lhv", "density", "CO2", "biogenic share")
            }
            for role, component in blend.items()
        }
        for fuel, blend in source.fuel_blend.items()
    }


def check_fuel_balance(inventory, source):
    properties = properties_for_years(source, inventory.scope["year"])
    for pt in inventory.scope["powertrain"]:
        cell = inventory.vm.array.sel(size=inventory.scope["size"][0], powertrain=pt)
        (column,) = inventory.find_input_indices(
            (f"transport, {inventory.vm.vehicle_type}, {pt},",)
        )
        active = cell.sel(parameter="TtW energy") > 0
        burned = (
            (
                cell.sel(parameter="fuel consumption")
                * cell.sel(parameter="fuel density per kg")
            )
            .where(active, 0)
            .transpose("value", "year")
            .values
        )
        fossil, biogenic = np.zeros_like(burned), np.zeros_like(burned)
        fuel = PT_FUEL.get(pt)
        if fuel:
            components = properties[fuel].values()
            lhv = sum(c["share"] * c["lhv"] for c in components)
            density = 1 / sum(c["share"] / c["density"] for c in components)
            np.testing.assert_allclose(
                cell.sel(parameter="LHV fuel MJ per kg").transpose("value", "year"),
                np.broadcast_to(lhv, burned.shape),
                rtol=2e-6,
            )
            np.testing.assert_allclose(
                cell.sel(parameter="fuel density per kg").transpose("value", "year"),
                np.broadcast_to(density, burned.shape),
                rtol=2e-6,
            )
            fossil = burned * sum(
                c["share"] * c["CO2"] * (1 - c["biogenic share"]) for c in components
            )
            biogenic = burned * sum(
                c["share"] * c["CO2"] * c["biogenic share"] for c in components
            )
        for label, expected in [("fossil", fossil), ("non-fossil", biogenic)]:
            row = inventory.inputs[(f"Carbon dioxide, {label}", ("air",), "kilogram")]
            np.testing.assert_allclose(
                -inventory.A[:, row, column, :], expected, rtol=2e-6, atol=1e-10
            )
        for category, blend in source.fuel_blend.items():
            (market,) = inventory.get_vehicle_supply_indices(
                f"fuel supply for {category} vehicles", [column]
            )
            expected = np.zeros_like(burned)
            if category == fuel:
                expected = burned
                if fuel == "methane":
                    leakage = (
                        cell.sel(parameter="CNG pump-to-tank leakage")
                        .transpose("value", "year")
                        .values
                    )
                    expected = burned * (1 + leakage)
                    for origin, fraction in [
                        (
                            "fossil",
                            1
                            - sum(c["share"] * c["biogenic share"] for c in components),
                        ),
                        (
                            "non-fossil",
                            sum(c["share"] * c["biogenic share"] for c in components),
                        ),
                    ]:
                        row = inventory.inputs[
                            (f"Methane, {origin}", ("air",), "kilogram")
                        ]
                        np.testing.assert_allclose(
                            -inventory.A[:, row, column, :],
                            burned * leakage * fraction,
                            rtol=2e-6,
                            atol=1e-10,
                        )
            np.testing.assert_allclose(
                -inventory.A[:, market, column, :], expected, rtol=2e-6, atol=1e-10
            )
            mapping = inventory.electricity_supply_indices.get(column, {})
            for role, component in blend.items():
                original = inventory.inputs[component["name"]]
                row = mapping.get(original, original)
                shares = properties[category][role]["share"]
                np.testing.assert_allclose(
                    -inventory.A[:, row, market, :],
                    np.broadcast_to(shares, expected.shape),
                    rtol=2e-6,
                )


@pytest.mark.family
@pytest.mark.parametrize("years", [[2025, 2030], [2025], [2030]])
def test_completed_selected_years_preserve_fuel_and_impacts(completed, years):
    source, cls, baseline = completed
    selected = deepcopy(source)
    selected.array = source.array.sel(year=years, value=["more-load", "reference"])
    original, blend = selected.array.copy(deep=True), deepcopy(selected.fuel_blend)
    inventory = cls(selected, scenario="static")
    check_fuel_balance(inventory, source)
    xr.testing.assert_allclose(
        inventory.calculate_impacts(),
        baseline.sel(year=years, value=["more-load", "reference"]),
        rtol=2e-5,
        atol=1e-9,
    )
    xr.testing.assert_identical(selected.array, original)
    np.testing.assert_equal(selected.fuel_blend, blend)


@pytest.mark.family
@pytest.mark.export
@pytest.mark.parametrize("version", ["3.12"])
def test_selected_year_exports_preserve_fuel_suppliers_and_carbon(completed, version):
    pytest.importorskip("bw2io")
    from carculator_utils.export import rename_mapping

    source, cls, _ = completed
    names = rename_mapping("rename_powertrains.yaml")
    for years in [[2025, 2030], [2030]]:
        model = deepcopy(source)
        model.array = source.array.sel(year=years, value=["more-load"])
        inventory = cls(model, scenario="static")
        matrix, index, blend = (
            inventory.A.copy(),
            inventory.inputs.copy(),
            deepcopy(model.fuel_blend),
        )
        expected = properties_for_years(source, years)
        # Export twice to catch accidental trimming of the model metadata.
        for _ in range(2):
            exports = inventory.export_lci(format="bw2io", ecoinvent_version=version)
            if not isinstance(exports, list):
                exports = [exports]
            assert len(exports) == len(years)
            for yi, (year, importer) in enumerate(zip(years, exports)):
                assert importer.db_name.endswith(str(year))
                for fuel, components in source.fuel_blend.items():
                    markets = [
                        a
                        for a in importer.data
                        if a["name"].startswith(f"fuel supply for {fuel} vehicles")
                    ]
                    assert markets
                    for market in markets:
                        actual = {}
                        for exchange in market["exchanges"]:
                            if exchange["type"] == "technosphere":
                                key = (
                                    exchange["name"].split(" [for ")[0],
                                    exchange["location"],
                                    exchange["unit"],
                                    exchange["reference product"],
                                )
                                actual[key] = actual.get(key, 0) + exchange["amount"]
                        wanted = {
                            c["name"]: expected[fuel][role]["share"][yi]
                            for role, c in components.items()
                            if expected[fuel][role]["share"][yi] > 0
                        }
                        assert actual.keys() == wanted.keys()
                        for key in wanted:
                            assert actual[key] == pytest.approx(wanted[key])
                for pt in model.array.powertrain.values:
                    (column,) = inventory.find_input_indices(
                        (f"transport, {model.vehicle_type}, {pt},",)
                    )
                    name = inventory.rev_inputs[column][0].replace(pt, names[pt])
                    (dataset,) = [a for a in importer.data if a["name"] == name]
                    for label in ["fossil", "non-fossil"]:
                        flow = (f"Carbon dioxide, {label}", ("air",), "kilogram")
                        amount = sum(
                            e["amount"]
                            for e in dataset["exchanges"]
                            if e["type"] == "biosphere"
                            and e["name"] == flow[0]
                            and tuple(e["categories"]) == flow[1]
                        )
                        assert amount == pytest.approx(
                            -inventory.A[0, inventory.inputs[flow], column, yi],
                            abs=1e-10,
                        )
        np.testing.assert_array_equal(inventory.A, matrix)
        assert inventory.inputs == index
        np.testing.assert_equal(model.fuel_blend, blend)
