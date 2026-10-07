"""Completed family runs: energy -> fuel mass -> suppliers and tailpipe carbon.

Fuel shares are mass fractions. These checks deliberately do not call the
inventory's carbon-intensity helper when calculating expected exchanges.
"""

import importlib
import importlib.util
import os
from copy import deepcopy

import numpy as np
import pytest

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.background_systems import BackgroundSystemModel

pytestmark = pytest.mark.family

CASES = [
    (
        "carculator",
        "Car",
        "Medium",
        [
            "ICEV-p",
            "ICEV-d",
            "ICEV-g",
            "HEV-p",
            "HEV-d",
            "PHEV-p",
            "PHEV-d",
            "FCEV",
            "BEV",
        ],
        {},
    ),
    (
        "carculator_bus",
        "Bus",
        "13m-city",
        ["ICEV-d", "ICEV-g", "HEV-d", "FCEV", "BEV-depot"],
        {},
    ),
    (
        "carculator_truck",
        "Truck",
        "40t",
        ["ICEV-d", "ICEV-g", "HEV-d", "PHEV-d", "FCEV", "BEV"],
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
SYNTHETIC_FUELS = {
    **FUELS,
    "petrol": (
        "petrol - synthetic - methanol - coal - economic allocation",
        "petrol - bioethanol - sugarbeet",
    ),
    "diesel": (
        "diesel - synthetic - FT - coal - economic allocation",
        "diesel - synthetic - FT - wood - economic allocation",
    ),
}
POWERTRAIN_FUEL = {
    "ICEV-p": "petrol",
    "HEV-p": "petrol",
    "PHEV-p": "petrol",
    "ICEV-d": "diesel",
    "HEV-d": "diesel",
    "PHEV-d": "diesel",
    "ICEV-g": "methane",
    "FCEV": "hydrogen",
}


@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
@pytest.mark.parametrize(
    "blend_mode", ["default", "bio", "synthetic", "same-supplier", "primary-only"]
)
def test_completed_fuel_blend_inventory(case, blend_mode):
    _completed_fuel_blend_inventory(case, blend_mode)


def _completed_fuel_blend_inventory(case, blend_mode):
    name, prefix, size, powertrains, kwargs = case
    if importlib.util.find_spec(name) is None:
        if os.environ.get("CARCULATOR_REQUIRE_FAMILY") == "1":
            pytest.fail(f"Required family package {name} missing")
        pytest.skip(f"Optional family package {name} missing")
    package = importlib.import_module(name)
    inputs = getattr(package, prefix + "InputParameters")()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={
            "size": [size],
            "powertrain": powertrains,
            "year": [2020, 2025, 2030],
        },
    )
    # Distinct samples exercise matrix axis alignment, without stochastic noise.
    array = array.isel(value=[0, 0]).assign_coords(value=[0, 1])
    array.loc[dict(parameter="average passengers", value=1)] *= 1.1
    specs = BackgroundSystemModel().fuel_specs
    blends = None
    if blend_mode != "default":
        blends = {
            fuel: {
                "primary": {"type": pair[0], "share": [1, 0.65, 0]},
                "secondary": {
                    "type": pair[0] if blend_mode == "same-supplier" else pair[1],
                    "share": [0, 0.35, 1],
                },
            }
            for fuel, pair in (
                SYNTHETIC_FUELS if blend_mode == "synthetic" else FUELS
            ).items()
            if fuel in {POWERTRAIN_FUEL.get(pt) for pt in powertrains}
        }
    if blend_mode == "primary-only":
        for components in blends.values():
            components.pop("secondary")
            components["primary"]["share"] = 0.65
    requested = deepcopy(blends)
    model = getattr(package, prefix + "Model")(array, fuel_blend=blends, **kwargs)
    model.set_all()
    assert blends == requested
    if requested:
        for fuel, components in requested.items():
            for role, component in components.items():
                assert model.fuel_blend[fuel][role]["type"] == component["type"]
                np.testing.assert_array_equal(
                    model.fuel_blend[fuel][role]["share"],
                    np.broadcast_to(component["share"], (3,)),
                )
    if blend_mode == "primary-only":
        for fuel in requested:
            np.testing.assert_allclose(
                model.fuel_blend[fuel]["secondary"]["share"], 0.35
            )
            assert model.fuel_blend[fuel]["secondary"]["type"] == FUELS[fuel][1]
    inventory = getattr(package, "Inventory" + prefix)(model)
    impacts = inventory.calculate_impacts()
    assert np.isfinite(impacts).all()

    # One kg of blend must procure one kg of components, including when two
    # roles point to the same supplier. Check all years and both sample axes.
    for fuel, blend in model.fuel_blend.items():
        (market,) = inventory.find_input_indices((f"fuel supply for {fuel} vehicles",))
        expected_suppliers = {}
        for component in blend.values():
            supplier = tuple(specs[component["type"]]["name"])
            expected_suppliers[supplier] = (
                expected_suppliers.get(supplier, 0) + component["share"]
            )
        for supplier, shares in expected_suppliers.items():
            np.testing.assert_allclose(
                -inventory.A[:, inventory.inputs[supplier], market, :],
                np.broadcast_to(shares, (2, 3)),
                atol=1e-8,
            )

    for pt in powertrains:
        (column,) = inventory.find_input_indices(
            (f"transport, {model.vehicle_type}, ", ", " + pt + ",", size)
        )
        select = dict(size=size, powertrain=pt)
        fuel = POWERTRAIN_FUEL.get(pt)
        expected_carbon = [np.zeros((2, 3)), np.zeros((2, 3))]
        if fuel:
            blend = model.fuel_blend[fuel]
            lhv = sum(c["share"] * specs[c["type"]]["lhv"] for c in blend.values())
            mass = (
                (model["fuel consumption"] * model["fuel density per kg"])
                .sel(**select)
                .transpose("value", "year")
                .values
            )
            energy = model["TtW energy"].sel(**select)
            if pt.startswith("PHEV"):
                energy = model["TtW energy, combustion mode"].sel(**select) * (
                    1 - model["electric utility factor"].sel(**select)
                )
            energy_mass = energy.transpose("value", "year").values / (lhv * 1000)
            np.testing.assert_allclose(mass, energy_mass, rtol=2e-5, atol=1e-9)
            assert (mass > 0).all()
            purchased = mass.copy()
            if fuel == "methane":
                purchased *= (
                    1
                    + model["CNG pump-to-tank leakage"]
                    .sel(**select)
                    .transpose("value", "year")
                    .values
                )
            for biogenic in (0, 1):
                factor = sum(
                    c["share"]
                    * specs[c["type"]]["co2"]
                    * (
                        specs[c["type"]]["biogenic_share"]
                        if biogenic
                        else 1 - specs[c["type"]]["biogenic_share"]
                    )
                    for c in blend.values()
                )
                expected_carbon[biogenic] = mass * factor
        for candidate in model.fuel_blend:
            (market,) = inventory.find_input_indices(
                (f"fuel supply for {candidate} vehicles",)
            )
            np.testing.assert_allclose(
                -inventory.A[:, market, column, :],
                purchased if candidate == fuel else 0,
                rtol=2e-5,
                atol=1e-9,
            )
        for label, expected in zip(("fossil", "non-fossil"), expected_carbon):
            row = inventory.inputs[(f"Carbon dioxide, {label}", ("air",), "kilogram")]
            np.testing.assert_allclose(
                -inventory.A[:, row, column, :],
                expected,
                rtol=2e-5,
                atol=1e-9,
                err_msg=f"{name} {pt} {label}",
            )

    return model, inventory, package


@pytest.mark.export
@pytest.mark.parametrize("case", CASES, ids=lambda c: c[0])
@pytest.mark.parametrize("blend_mode", ["bio", "same-supplier", "primary-only"])
def test_fuel_blends_survive_brightway_export(case, blend_mode, tmp_path):
    pytest.importorskip("bw2io")
    from carculator_utils.export import rename_mapping

    model, _, package = _completed_fuel_blend_inventory(case, blend_mode)
    model = deepcopy(model)
    model.array = model.array.isel(value=[0])
    inventory = getattr(package, "Inventory" + case[1])(model)
    before = inventory.A.copy()
    indices_before = inventory.inputs.copy()
    exports = inventory.export_lci(
        ecoinvent_version="3.10", format="bw2io", directory=tmp_path
    )
    assert len(exports) == 3
    renamed = rename_mapping("rename_powertrains.yaml")
    for yi, (year, importer) in enumerate(zip(model.array.year.values, exports)):
        assert importer.db_name.endswith(str(year))
        datasets = {d["name"]: d for d in importer.data}
        for fuel, blend in model.fuel_blend.items():
            expected = {}
            for component in blend.values():
                supplier = component["name"]
                expected[supplier] = expected.get(supplier, 0) + component["share"][yi]
            (dataset,) = [
                d
                for name, d in datasets.items()
                if name.startswith(f"fuel supply for {fuel} vehicles")
            ]
            assert dataset["unit"] == "kilogram"
            exchanges = {
                (e["name"], e["location"], e["unit"], e["reference product"]): e[
                    "amount"
                ]
                for e in dataset["exchanges"]
                if e["type"] == "technosphere"
            }
            assert set(exchanges) == {s for s, share in expected.items() if share > 0}
            for supplier, share in expected.items():
                assert exchanges.get(supplier, 0) == pytest.approx(share)
            assert sum(exchanges.values()) == pytest.approx(1)
        for pt in case[3]:
            (column,) = inventory.find_input_indices(
                (f"transport, {model.vehicle_type}, ", f", {pt},", case[2])
            )
            name = inventory.rev_inputs[column][0].replace(pt, renamed[pt])
            dataset = datasets[name]
            for fuel in model.fuel_blend:
                (market,) = inventory.find_input_indices(
                    (f"fuel supply for {fuel} vehicles",)
                )
                amount = sum(
                    e["amount"]
                    for e in dataset["exchanges"]
                    if e["type"] == "technosphere"
                    and e["name"] == inventory.rev_inputs[market][0]
                )
                assert amount == pytest.approx(
                    -inventory.A[0, market, column, yi], abs=1e-12
                )
            for label in ("fossil", "non-fossil"):
                flow = (f"Carbon dioxide, {label}", ("air",), "kilogram")
                amount = sum(
                    e["amount"]
                    for e in dataset["exchanges"]
                    if e["type"] == "biosphere"
                    and e["name"] == flow[0]
                    and tuple(e["categories"]) == flow[1]
                )
                assert amount == pytest.approx(
                    -inventory.A[0, inventory.inputs[flow], column, yi], abs=1e-12
                )
    np.testing.assert_array_equal(inventory.A, before)
    assert inventory.inputs == indices_before
