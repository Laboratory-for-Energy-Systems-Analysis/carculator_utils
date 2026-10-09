"""Delivered fuel does not acquire an unsupported default loss overlay."""

import numpy as np
import pytest

from carculator_utils.array import fill_xarray_from_input_parameters


@pytest.mark.family
@pytest.mark.parametrize(
    "package,prefix,size,options",
    [
        ("carculator", "Car", "Medium", {}),
        ("carculator_bus", "Bus", "13m-city", {}),
        ("carculator_truck", "Truck", "40t", {"cycle": "Long haul"}),
    ],
)
@pytest.mark.parametrize(
    "fuel",
    [
        "methane",
        "methane - biomethane - sewage sludge",
        "methane - synthetic - biological",
    ],
)
def test_default_loss_boundary_preserves_upstream_and_exhaust(
    package, prefix, size, options, fuel
):
    module = pytest.importorskip(package)
    inputs = getattr(module, prefix + "InputParameters")()
    inputs.stochastic(2, seed=23)
    for key, metadata in inputs.metadata.items():
        if metadata["name"] == "CNG pump-to-tank leakage":
            np.testing.assert_array_equal(inputs.values[key], 0)
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={"size": [size], "powertrain": ["ICEV-g"], "year": [2020, 2025, 2030]},
    )
    model = getattr(module, prefix + "Model")(
        array,
        fuel_blend={"methane": {"primary": {"type": fuel, "share": 1}}},
        **options,
    )
    model.set_all()
    inventory = getattr(module, "Inventory" + prefix)(model, scenario="static")
    assert np.isfinite(inventory.calculate_impacts()).all()
    (column,) = inventory.find_input_indices(
        (f"transport, {model.vehicle_type}, ICEV-g, ",)
    )
    (market,) = inventory.find_input_indices(("fuel supply for methane vehicles",))
    burned = (model["fuel consumption"] * model["fuel density per kg"]).values.reshape(
        3
    )
    np.testing.assert_allclose(-inventory.A[0, market, column, :], burned, rtol=2e-6)
    for origin in ("fossil", "non-fossil"):
        row = inventory.inputs[(f"Methane, {origin}", ("air",), "kilogram")]
        np.testing.assert_array_equal(inventory.A[:, row, column, :], 0)
    # Combustion exhaust methane remains independently represented.
    exhaust = [
        index
        for key, index in inventory.inputs.items()
        if key[0].startswith("Methane,")
        and isinstance(key[1], tuple)
        and len(key[1]) > 1
    ]
    assert -inventory.A[:, exhaust, column, :].sum() > 0
    if fuel == "methane - biomethane - sewage sludge":
        supplier = inventory.inputs[
            tuple(model.fuel_blend["methane"]["primary"]["name"])
        ]
        row = inventory.inputs[("Methane, non-fossil", ("air",), "kilogram")]
        np.testing.assert_allclose(-inventory.A[:, row, supplier, :], 0.00030042)
