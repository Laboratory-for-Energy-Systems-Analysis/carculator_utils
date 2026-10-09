"""Biological methanation must reach fuel supply, combustion and export."""

import importlib
import os
from copy import deepcopy

import numpy as np
import pytest
from scipy import sparse

from carculator_utils import DATA_DIR
from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.background_systems import BackgroundSystemModel
from carculator_utils.fuel_supply import fill_fuel_suppliers, register_fuel_suppliers
from carculator_utils.inventory import get_dict_input, validate_fuel_mappings

FUEL = "methane - synthetic - biological"
DELIVERED = (
    "methane, synthetic, from biological methanation and carbon from atmosphere, "
    "at fuelling station",
    "RER",
    "kilogram",
    "methane, high pressure",
)
PRODUCTION = (
    "methane, from biological methanation, with carbon from atmosphere",
    "RER",
    "kilogram",
    "methane, from biological methanation",
)
SEWAGE = (
    "biomethane, gaseous, 5 bar, from sewage sludge fermentation, at fuelling station",
    "RER",
    "kilogram",
    "biomethane, high pressure",
)
SEWAGE_PRODUCTION = (
    "biomethane production, from biogas upgrading, using amine scrubbing",
    "RER",
    "kilogram",
    "biomethane, from biogas upgrading, using amine scrubbing",
)
HYDROGEN = (
    "market for hydrogen, gaseous, low pressure",
    "RER",
    "kilogram",
    "hydrogen, gaseous, low pressure",
)
CAPTURE = (
    "carbon dioxide, captured from atmosphere, with a sorbent-based direct air "
    "capture system, 100ktCO2",
    "RER",
    "kilogram",
    "carbon dioxide, captured from atmosphere",
)
CASES = [
    ("carculator", "Car", "Medium", {}),
    ("carculator_bus", "Bus", "13m-city", {}),
    ("carculator_truck", "Truck", "40t", {"cycle": "Long haul"}),
]


def test_supply_recipe_preserves_bundled_indices_and_delivery_inputs():
    inputs = get_dict_input()
    before = inputs.copy()
    blend = {"methane": {"primary": {"name": DELIVERED}}}
    recipes = register_fuel_suppliers(inputs, blend)
    validate_fuel_mappings(
        {
            "methane": {
                role: {"name": DELIVERED, "type": FUEL}
                for role in ("primary", "secondary")
            }
        },
        inputs,
    )
    assert {key: inputs[key] for key in before} == before
    assert inputs[DELIVERED] == len(before)
    assert len(recipes) == 1
    raw = sparse.load_npz(DATA_DIR / "IAM" / "A_matrix.npz").toarray()
    matrix = np.eye(len(inputs))
    matrix[: len(raw), : len(raw)] = raw
    matrix = np.broadcast_to(
        matrix[None, :, :, None], (2, len(inputs), len(inputs), 3)
    ).copy()
    fill_fuel_suppliers(matrix, inputs, recipes)
    np.testing.assert_array_equal(
        matrix[:, : len(raw), : len(raw), :],
        np.broadcast_to(raw[None, :, :, None], (2, len(raw), len(raw), 3)),
    )
    expected = np.zeros(len(inputs))
    expected[: len(raw)] = raw[:, before[SEWAGE]]
    expected[inputs[SEWAGE]] = 0
    expected[inputs[SEWAGE_PRODUCTION]] = 0
    expected[inputs[PRODUCTION]] = -1.02
    electricity = (
        "market group for electricity, medium voltage",
        "RER",
        "kilowatt hour",
        "electricity, medium voltage",
    )
    expected[inputs[electricity]] = -0.314
    expected[inputs[DELIVERED]] = 1
    # Premise compact stores source coefficients as float32. Retain the
    # independent 2% delivery-loss expectation within that source precision.
    np.testing.assert_allclose(
        matrix[:, :, inputs[DELIVERED], :],
        np.broadcast_to(expected[None, :, None], (2, len(inputs), 3)),
    )


def test_custom_supplier_and_unselected_fuels_do_not_add_activity():
    inputs = get_dict_input()
    before = inputs.copy()
    for blend in ({}, {"methane": {"primary": {"type": FUEL, "name": SEWAGE}}}):
        assert register_fuel_suppliers(inputs, blend) == []
        assert inputs == before


def test_missing_recipe_dependency_fails_without_changing_index():
    inputs = get_dict_input()
    del inputs[PRODUCTION]
    before = inputs.copy()
    with pytest.raises(KeyError, match="requires missing.*biological methanation"):
        register_fuel_suppliers(inputs, {"methane": {"primary": {"name": DELIVERED}}})
    assert inputs == before


@pytest.fixture(scope="module", params=CASES, ids=lambda case: case[0])
def completed_inventory(request):
    name, prefix, size, kwargs = request.param
    if importlib.util.find_spec(name) is None:
        if os.environ.get("CARCULATOR_REQUIRE_FAMILY") == "1":
            pytest.fail(f"Required family package {name} missing")
        pytest.skip(f"Optional family package {name} missing")
    package = importlib.import_module(name)
    parameters = getattr(package, prefix + "InputParameters")()
    parameters.static()
    _, array = fill_xarray_from_input_parameters(
        parameters,
        scope={"size": [size], "powertrain": ["ICEV-g"], "year": [2025, 2030]},
    )
    # Distinct physical samples exercise both inventory sample and year axes.
    array = array.isel(value=[0, 0]).assign_coords(value=[0, 1])
    array.loc[dict(parameter="average passengers", value=1)] *= 1.1
    blend = {
        "methane": {
            "primary": {"type": FUEL, "share": [1, 0.35]},
            "secondary": {"type": "methane", "share": [0, 0.65]},
        }
    }
    before = deepcopy(blend)
    model = getattr(package, prefix + "Model")(array, fuel_blend=blend, **kwargs)
    model.set_all()
    inventory = getattr(package, "Inventory" + prefix)(model, scenario="static")
    assert blend == before
    assert np.isfinite(inventory.calculate_impacts()).all()
    return model, inventory, package, prefix


@pytest.mark.family
def test_completed_biological_methane_supply_and_carbon(completed_inventory):
    model, inventory, _, _ = completed_inventory
    specs = BackgroundSystemModel().fuel_specs[FUEL]
    assert tuple(specs["name"]) == DELIVERED
    assert specs["lhv"] == 49.9
    assert specs["co2"] == 2.75
    assert specs["biogenic_share"] == 1
    A, inputs = inventory.A, inventory.inputs
    (market,) = inventory.find_input_indices(("fuel supply for methane vehicles",))
    (electricity,) = inventory.find_input_indices(
        ("electricity supply for fuel preparation",)
    )
    (transport,) = inventory.find_input_indices(
        (f"transport, {model.vehicle_type}, ICEV-g,",)
    )
    np.testing.assert_allclose(-A[:, inputs[DELIVERED], market, :], [[1, 0.35]] * 2)
    np.testing.assert_array_equal(A[:, inputs[SEWAGE], market, :], 0)
    np.testing.assert_allclose(-A[:, inputs[PRODUCTION], inputs[DELIVERED], :], 1.02)
    np.testing.assert_allclose(-A[:, electricity, inputs[DELIVERED], :], 0.314)
    np.testing.assert_array_equal(
        A[:, inputs[SEWAGE_PRODUCTION], inputs[DELIVERED], :], 0
    )
    # Distinguish station compression from reactor, hydrogen-market and DAC inputs.
    np.testing.assert_allclose(-A[:, electricity, inputs[PRODUCTION], :], 1.55)
    np.testing.assert_allclose(-A[:, inputs[HYDROGEN], inputs[PRODUCTION], :], 0.5)
    np.testing.assert_allclose(-A[:, inputs[CAPTURE], inputs[PRODUCTION], :], 2.75)
    uptake = inputs[
        ("Carbon dioxide, in air", ("natural resource", "in air"), "kilogram")
    ]
    np.testing.assert_allclose(-A[:, uptake, inputs[CAPTURE], :], 1)

    # Independent fuel and complete-oxidation expectations, kg per vehicle-km.
    energy = (
        model["TtW energy"].isel(size=0, powertrain=0).transpose("value", "year").values
    )
    mass = energy / (1000 * np.array([49.9, 0.35 * 49.9 + 0.65 * 47.5]))
    leakage = (
        model["CNG pump-to-tank leakage"]
        .isel(size=0, powertrain=0)
        .transpose("value", "year")
        .values
    )
    np.testing.assert_allclose(
        -A[:, market, transport, :], mass * (1 + leakage), rtol=2e-5
    )
    for label, factors in (
        ("non-fossil", [2.75, 0.35 * 2.75]),
        ("fossil", [0, 0.65 * 2.68]),
    ):
        row = inputs[(f"Carbon dioxide, {label}", ("air",), "kilogram")]
        np.testing.assert_allclose(-A[:, row, transport, :], mass * factors, rtol=2e-5)

    # Carbon capture and release use the same characterization convention.
    release = inputs[("Carbon dioxide, non-fossil", ("air",), "kilogram")]
    B = inventory.B
    for category, expected in (("climate change", 0), ("climate change w bio", 1)):
        np.testing.assert_allclose(
            B.sel(category=category).isel(activity=release), expected
        )
        np.testing.assert_allclose(
            B.sel(category=category).isel(activity=uptake), -expected
        )


@pytest.mark.family
@pytest.mark.export
def test_biological_methane_export_preserves_supplier_and_provenance(
    completed_inventory, tmp_path
):
    pytest.importorskip("bw2io")
    model, _, package, prefix = completed_inventory
    model = deepcopy(model)
    model.array = model.array.isel(value=[0])
    inventory = getattr(package, "Inventory" + prefix)(model, scenario="static")
    before = inventory.A.copy()
    indices = inventory.inputs.copy()
    for _ in range(2):
        exports = inventory.export_lci(
            ecoinvent_version="3.12", format="bw2io", directory=tmp_path
        )
        assert len(exports) == 2
        for importer in exports:
            (supplier,) = [d for d in importer.data if d["name"] == DELIVERED[0]]
            assert supplier["unit"] == "kilogram"
            assert "BioCat" in supplier["comment"]
            exchanges = supplier["exchanges"]
            production = [e for e in exchanges if e["name"] == PRODUCTION[0]]
            assert len(production) == 1
            assert production[0]["amount"] == pytest.approx(1.02)
            assert not any(
                e["name"] in (SEWAGE[0], SEWAGE_PRODUCTION[0]) for e in exchanges
            )
            (compression,) = [
                e
                for e in exchanges
                if e["name"].startswith("electricity supply for fuel preparation")
            ]
            assert compression["amount"] == pytest.approx(0.314)
    np.testing.assert_array_equal(inventory.A, before)
    assert inventory.inputs == indices
