"""Independent methane mass balances and characterized, exported leakage."""

import importlib
import itertools
import os
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.inventory import Inventory


def minimal_inventory():
    """Two gas sizes, reordered years/samples, and an unrelated diesel column."""
    inventory = Inventory.__new__(Inventory)
    inventory.scope = {
        "size": ["Large", "Small"],
        "powertrain": ["ICEV-g", "ICEV-d"],
        "year": [2030, 2025],
    }
    inventory.vm = SimpleNamespace(
        vehicle_type="car",
        _fuel_blend_years=(2030, 2025),
        fuel_blend={
            "methane": {
                "primary": {"share": np.array([0.25, 1]), "biogenic share": 0},
                "secondary": {"share": np.array([0.75, 0]), "biogenic share": 1},
            }
        },
    )
    inventory.inputs = {
        ("fuel supply for methane vehicles", "CH", "kilogram", "fuel"): 0,
        ("Methane, fossil", ("air",), "kilogram"): 1,
        ("Methane, non-fossil", ("air",), "kilogram"): 2,
        ("transport, car, ICEV-g, Large", "CH", "kilometer", "transport, car"): 3,
        ("transport, car, ICEV-d, Large", "CH", "kilometer", "transport, car"): 4,
        ("transport, car, ICEV-g, Small", "CH", "kilometer", "transport, car"): 5,
    }
    inventory.rev_inputs = {value: key for key, value in inventory.inputs.items()}
    inventory.A = np.zeros((2, 6, 6, 2))
    inventory.A[:, :, 4, :] = 123  # Unrelated vehicle must remain untouched.
    inventory.array = xr.DataArray(
        np.ones((2, 4, 2, 2)),
        dims=("value", "parameter", "combined_dim", "year"),
        coords={
            "value": [9, 2],
            "parameter": [
                "fuel consumption",
                "fuel density per kg",
                "CNG pump-to-tank leakage",
                "TtW energy",
            ],
            "combined_dim": ["Large - ICEV-g", "Small - ICEV-g"],
            "year": [2030, 2025],
        },
    )
    inventory.array.loc[dict(parameter="fuel consumption")] = [
        [[1, 2], [3, 4]],
        [[5, 6], [7, 8]],
    ]
    inventory.array.loc[dict(parameter="CNG pump-to-tank leakage")] = [
        [[0, 0.1], [0.2, 0.3]],
        [[0.4, 0.5], [0.6, 0.7]],
    ]
    return inventory


def test_mass_balance_alignment_and_repeatability():
    inventory = minimal_inventory()
    inventory.add_methane_leakage()
    # Hand-calculated kg: engine fuel, lost methane, then blend-origin split.
    engine = np.arange(1, 9).reshape(2, 2, 2)
    lost = np.array([0, 0.2, 0.6, 1.2, 2, 3, 4.2, 5.6]).reshape(2, 2, 2)
    columns = [3, 5]
    np.testing.assert_allclose(-inventory.A[:, 0, columns], engine + lost)
    np.testing.assert_allclose(-inventory.A[:, 1, columns], lost * [0.25, 1])
    np.testing.assert_allclose(-inventory.A[:, 2, columns], lost * [0.75, 0])
    np.testing.assert_array_equal(inventory.A[:, :, 4], 123)
    before = inventory.A.copy()
    inventory.add_methane_leakage()
    np.testing.assert_array_equal(inventory.A, before)


@pytest.mark.parametrize("rate", [-0.1, np.nan, np.inf])
def test_invalid_active_leakage_fails_before_inventory_mutation(rate):
    inventory = minimal_inventory()
    inventory.array.loc[
        dict(
            parameter="CNG pump-to-tank leakage",
            value=2,
            combined_dim="Small - ICEV-g",
            year=2025,
        )
    ] = rate
    before = inventory.A.copy()
    with pytest.raises(
        ValueError, match="CNG pump-to-tank leakage.*Small - ICEV-g.*2025"
    ):
        inventory.add_methane_leakage()
    np.testing.assert_array_equal(inventory.A, before)


@pytest.mark.parametrize("fraction", [-0.1, 1.1, np.nan, "invalid", [0.1, 0.2, 0.3]])
def test_invalid_carbon_origin_fails_before_inventory_mutation(fraction):
    inventory = minimal_inventory()
    inventory.vm.fuel_blend["methane"]["primary"]["biogenic share"] = fraction
    before = inventory.A.copy()
    with pytest.raises(ValueError, match="(?i)methane.*primary.*biogenic share"):
        inventory.add_methane_leakage()
    np.testing.assert_array_equal(inventory.A, before)


def test_year_specific_carbon_origin_override_is_preserved():
    inventory = minimal_inventory()
    inventory.vm.fuel_blend["methane"]["primary"]["biogenic share"] = [0.4, 0.8]
    before = deepcopy(inventory.vm.fuel_blend)
    inventory.add_methane_leakage()
    lost = np.array([0, 0.2, 0.6, 1.2, 2, 3, 4.2, 5.6]).reshape(2, 2, 2)
    np.testing.assert_allclose(-inventory.A[:, 2, [3, 5]], lost * [0.85, 0.8])
    for role in before["methane"]:
        for key in before["methane"][role]:
            np.testing.assert_array_equal(
                inventory.vm.fuel_blend["methane"][role][key],
                before["methane"][role][key],
            )


def test_unavailable_gas_vehicle_does_not_create_leakage():
    inventory = minimal_inventory()
    inventory.array.loc[dict(parameter="TtW energy", combined_dim="Small - ICEV-g")] = 0
    inventory.array.loc[
        dict(parameter="CNG pump-to-tank leakage", combined_dim="Small - ICEV-g")
    ] = np.nan
    inventory.add_methane_leakage()
    np.testing.assert_array_equal(inventory.A[:, :3, 5], 0)


def test_no_gas_powertrain_requires_no_gas_parameters():
    inventory = Inventory.__new__(Inventory)
    inventory.scope = {"powertrain": ["BEV", "ICEV-p"]}
    inventory.add_methane_leakage()


CASES = [
    ("carculator", "Car", "Medium", "BEV", {}),
    ("carculator_bus", "Bus", "13m-city", "BEV-depot", {}),
    ("carculator_truck", "Truck", "40t", "BEV", {"cycle": "Long haul"}),
]
BIOFUELS = ["methane - biomethane - sewage sludge", "methane - synthetic - biological"]
COMBINATIONS = list(itertools.product(CASES, BIOFUELS, ["recipe", "ef"]))


@pytest.fixture(
    scope="module",
    params=COMBINATIONS,
    ids=lambda case: f"{case[0][0]}-{case[1]}-{case[2]}",
)
def completed_run(request):
    case, biofuel, method = request.param
    name, prefix, size, bev, kwargs = case
    if importlib.util.find_spec(name) is None:
        if os.environ.get("CARCULATOR_REQUIRE_FAMILY") == "1":
            pytest.fail(f"Required family package {name} missing")
        pytest.skip(f"Optional family package {name} missing")
    package = importlib.import_module(name)
    parameters = getattr(package, prefix + "InputParameters")()
    parameters.static()
    _, array = fill_xarray_from_input_parameters(
        parameters,
        scope={
            "size": [size],
            "powertrain": [bev, "ICEV-g", "ICEV-d"],
            "year": [2020, 2025, 2030],
        },
    )
    array = (
        array.sel(year=[2030, 2025, 2020])
        .isel(value=[0, 0])
        .assign_coords(value=[1, 0])
    )
    array.loc[dict(parameter="average passengers", value=0)] *= 1.1
    blend = {
        "diesel": {"primary": {"type": "diesel", "share": 1}},
        "methane": {
            "primary": {"type": "methane", "share": [0, 0.65, 1]},
            "secondary": {"type": biofuel, "share": [1, 0.35, 0]},
        },
    }
    before = deepcopy(blend)
    model = getattr(package, prefix + "Model")(array, fuel_blend=blend, **kwargs)
    model.set_all()
    assert blend == before
    model["CNG pump-to-tank leakage"] = 0
    inventory_type = getattr(package, "Inventory" + prefix)
    baseline = inventory_type(model, scenario="static", method=method)
    baseline_impacts = baseline.calculate_impacts()
    assert np.isfinite(baseline_impacts).all()
    baseline_matrix = baseline.A.copy()
    baseline_inputs = baseline.inputs.copy()
    del baseline
    model.array.loc[dict(parameter="CNG pump-to-tank leakage", powertrain="ICEV-g")] = (
        xr.DataArray(
            [[0, 0.004, 0.08], [0.02, 0.008, 0]],
            dims=("value", "year"),
            coords={"value": [1, 0], "year": [2030, 2025, 2020]},
        )
    )
    inventory = inventory_type(model, scenario="static", method=method)
    impacts = inventory.calculate_impacts()
    assert np.isfinite(impacts).all()
    return (
        model,
        inventory,
        impacts,
        baseline_matrix,
        baseline_inputs,
        baseline_impacts,
        inventory_type,
    )


@pytest.mark.family
def test_completed_mass_balance_and_unchanged_upstream_boundary(completed_run):
    model, inventory, _, baseline, original_indices, _, _ = completed_run
    assert inventory.inputs == original_indices
    (transport,) = inventory.find_input_indices(
        (f"transport, {model.vehicle_type}, ICEV-g,",)
    )
    (market,) = inventory.find_input_indices(("fuel supply for methane vehicles",))
    fossil = inventory.inputs[("Methane, fossil", ("air",), "kilogram")]
    nonfossil = inventory.inputs[("Methane, non-fossil", ("air",), "kilogram")]
    # The baseline purchase equals engine fuel; loss rates are varied independently.
    engine = -baseline[:, market, transport, :]
    lost = engine * [[0, 0.004, 0.08], [0.02, 0.008, 0]]
    np.testing.assert_allclose(
        -inventory.A[:, market, transport, :], engine + lost, rtol=2e-6
    )
    np.testing.assert_allclose(
        -inventory.A[:, fossil, transport, :], lost * [0, 0.65, 1], rtol=2e-6
    )
    np.testing.assert_allclose(
        -inventory.A[:, nonfossil, transport, :], lost * [1, 0.35, 0], rtol=2e-6
    )
    purchased = -inventory.A[:, market, transport, :]
    total_leaked = (
        -inventory.A[:, fossil, transport, :] - inventory.A[:, nonfossil, transport, :]
    )
    np.testing.assert_allclose(purchased, engine + total_leaked, rtol=2e-6)
    # Only the gas transport's supply and two generic-air leakage rows change.
    restored = inventory.A.copy()
    for row in (market, fossil, nonfossil):
        restored[:, row, transport, :] = baseline[:, row, transport, :]
    np.testing.assert_array_equal(restored, baseline)
    before = inventory.A.copy()
    inventory.add_methane_leakage()
    np.testing.assert_array_equal(inventory.A, before)


@pytest.mark.family
def test_completed_leakage_is_in_characterized_results(completed_run):
    model, inventory, impacts, baseline, _, base_impacts, _ = completed_run
    (transport,) = inventory.find_input_indices(
        (f"transport, {model.vehicle_type}, ICEV-g,",)
    )
    (market,) = inventory.find_input_indices(("fuel supply for methane vehicles",))
    lost = -baseline[:, market, transport, :] * [[0, 0.004, 0.08], [0.02, 0.008, 0]]
    expected = lost * (np.array([0, 0.65, 1]) * 29.8 + np.array([1, 0.35, 0]) * 27)
    change = (
        (impacts - base_impacts)
        .sel(
            impact_category="climate change",
            impact="direct - non-exhaust",
            powertrain="ICEV-g",
        )
        .isel(size=0)
        .transpose("value", "year")
        .values
    )
    np.testing.assert_allclose(change, expected, rtol=2e-6, atol=1e-10)
    for origin in ("fossil", "non-fossil"):
        row = inventory.inputs[(f"Methane, {origin}", ("air",), "kilogram")]
        assert sum(group.count(row) for group in inventory.split_indices) == 1


@pytest.mark.family
@pytest.mark.export
def test_completed_leakage_survives_repeated_export(completed_run, tmp_path):
    pytest.importorskip("bw2io")
    from carculator_utils.export import rename_mapping

    model, _, _, _, _, _, inventory_type = completed_run
    model = deepcopy(model)
    # Select the second physical sample, labelled 0 for the static export API.
    model.array = model.array.isel(value=[1])
    inventory = inventory_type(model, scenario="static")
    before = inventory.A.copy()
    original_indices = inventory.inputs.copy()
    (transport,) = inventory.find_input_indices(
        (f"transport, {model.vehicle_type}, ICEV-g,",)
    )
    (market,) = inventory.find_input_indices(("fuel supply for methane vehicles",))
    name = inventory.rev_inputs[transport][0].replace(
        "ICEV-g", rename_mapping("rename_powertrains.yaml")["ICEV-g"]
    )
    for _ in range(2):
        exports = inventory.export_lci(
            ecoinvent_version="3.10", format="bw2io", directory=tmp_path
        )
        assert len(exports) == 3
        for year_index, importer in enumerate(exports):
            (vehicle,) = [
                dataset for dataset in importer.data if dataset["name"] == name
            ]
            (purchase,) = [
                exchange
                for exchange in vehicle["exchanges"]
                if exchange["name"] == inventory.rev_inputs[market][0]
            ]
            assert purchase["amount"] == pytest.approx(
                -before[0, market, transport, year_index]
            )
            for origin in ("fossil", "non-fossil"):
                flow = (f"Methane, {origin}", ("air",), "kilogram")
                amount = sum(
                    exchange["amount"]
                    for exchange in vehicle["exchanges"]
                    if exchange["type"] == "biosphere"
                    and exchange["name"] == flow[0]
                    and tuple(exchange["categories"]) == flow[1]
                )
                assert amount == pytest.approx(
                    -before[0, inventory.inputs[flow], transport, year_index], abs=1e-12
                )
    np.testing.assert_array_equal(inventory.A, before)
    assert inventory.inputs == original_indices
