"""Completed family runs: energy -> fuel mass -> suppliers and tailpipe carbon.

Fuel shares are mass fractions. These checks deliberately do not call the
inventory's carbon-intensity helper when calculating expected exchanges.
"""

import importlib
import importlib.util
import os

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
@pytest.mark.parametrize("blend_mode", ["default", "bio", "synthetic", "same-supplier"])
def test_completed_fuel_blend_inventory(case, blend_mode):
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
    model = getattr(package, prefix + "Model")(array, fuel_blend=blends, **kwargs)
    model.set_all()
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
