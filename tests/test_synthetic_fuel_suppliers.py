"""Carbon source and allocation labels must resolve to the named supplier."""

import numpy as np
import pytest

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.background_systems import get_fuels_specs
from carculator_utils.inventory import get_dict_input


@pytest.mark.parametrize("allocation", ["economic", "energy"])
def test_methanol_fuel_labels_match_supplier_processes(allocation):
    specs = get_fuels_specs()
    index = get_dict_input()
    for label, source in [("electrolysis", "DAC"), ("cement", "cement plant")]:
        fuel = f"diesel - synthetic - methanol - {label} - {allocation} allocation"
        supplier = tuple(specs[fuel]["name"])
        assert supplier in index
        assert f"CO2 from {source}, {allocation} allocation" in supplier[0]
    for label in ["electrolysis", "cement"]:
        fuel = f"petrol - synthetic - methanol - {label} - {allocation} allocation"
        supplier = tuple(specs[fuel]["name"])
        assert supplier in index
        assert f"CO2 from cement plant, {allocation} allocation" in supplier[0]


@pytest.mark.family
@pytest.mark.parametrize("allocation", ["economic", "energy"])
@pytest.mark.parametrize(
    "package,prefix,size,powertrain,options",
    [
        ("carculator", "Car", "Medium", "ICEV-d", {}),
        ("carculator_bus", "Bus", "13m-city", "ICEV-d", {}),
        ("carculator_truck", "Truck", "40t", "ICEV-d", {"cycle": "Long haul"}),
        ("carculator_two_wheeler", "TwoWheeler", "Scooter <4kW", "ICEV-p", {}),
    ],
)
def test_completed_inventory_uses_requested_carbon_source_and_allocation(
    package, prefix, size, powertrain, options, allocation
):
    module = pytest.importorskip(package)
    inputs = getattr(module, prefix + "InputParameters")()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs, scope={"size": [size], "powertrain": [powertrain], "year": [2025]}
    )
    fuel = "petrol" if powertrain == "ICEV-p" else "diesel"
    sources = ["cement", "cement"] if fuel == "petrol" else ["electrolysis", "cement"]
    blend = {
        fuel: {
            role: {
                "type": f"{fuel} - synthetic - methanol - {source} - {allocation} allocation",
                "share": share,
            }
            for role, source, share in zip(
                ["primary", "secondary"], sources, [0.25, 0.75]
            )
        }
    }
    model = getattr(module, prefix + "Model")(array, fuel_blend=blend, **options)
    model.set_all()
    inventory = getattr(module, "Inventory" + prefix)(model, scenario="static")
    assert np.isfinite(inventory.calculate_impacts()).all()
    (market,) = inventory.find_input_indices((f"fuel supply for {fuel} vehicles",))
    expected = (
        {"cement plant": 1.0}
        if fuel == "petrol"
        else {"DAC": 0.25, "cement plant": 0.75}
    )
    for source, share in expected.items():
        product = "gasoline" if fuel == "petrol" else fuel
        supplier = (
            f"{product} production, synthetic, from methanol, hydrogen from electrolysis, CO2 from {source}, {allocation} allocation, at fuelling station",
            "RER",
            "kilogram",
            f"{product}, synthetic, vehicle grade",
        )
        np.testing.assert_allclose(
            -inventory.A[:, inventory.inputs[supplier], market, :], share
        )
