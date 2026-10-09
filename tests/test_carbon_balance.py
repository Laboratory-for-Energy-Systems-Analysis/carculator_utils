"""Carbon closure requires explicit composition, independent of climate allocation."""

import numpy as np
import pytest

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.carbon_balance import carbon_origin


def test_recycled_and_atmospheric_carbon_are_not_called_biogenic():
    assert "industrial" in carbon_origin(
        {"type": "diesel - synthetic - methanol - cement - economic allocation"}
    )
    assert "not biogenic" in carbon_origin(
        {"type": "diesel - synthetic - methanol - electrolysis - economic allocation"}
    )
    assert (
        carbon_origin({"type": "petrol - bioethanol - wheat straw"})
        == "biogenic carbon"
    )


@pytest.mark.family
@pytest.mark.parametrize(
    "package,prefix,size,powertrain,options",
    [
        ("carculator", "Car", "Medium", "ICEV-p", {}),
        ("carculator_bus", "Bus", "13m-city", "ICEV-d", {}),
        ("carculator_truck", "Truck", "40t", "ICEV-d", {"cycle": "Long haul"}),
        ("carculator_two_wheeler", "TwoWheeler", "Motorcycle 11-35kW", "ICEV-p", {}),
    ],
)
def test_completed_carbon_audit_and_explicit_reconciliation(
    package, prefix, size, powertrain, options
):
    module = pytest.importorskip(package)
    inputs = getattr(module, prefix + "InputParameters")()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs, scope={"size": [size], "powertrain": [powertrain], "year": [2030, 2025]}
    )
    model = getattr(module, prefix + "Model")(array, **options)
    model.set_all()
    inventory = getattr(module, "Inventory" + prefix)(model, scenario="static")
    before = inventory.A.copy()
    report = inventory.carbon_balance()
    assert (report.carbon_excess_lower_bound > 0).all()
    assert not report.attrs["closed_elemental_balance"]
    np.testing.assert_array_equal(inventory.A, before)
    # These are an explicit analytic scenario, not measured default fractions.
    fractions = {
        "Non-methane hydrocarbon": 0.8,
        "Hydrocarbons": 0.5,
        "PAH, polycyclic aromatic hydrocarbons": 0.9,
        "Particulate matters": 0.7,
    }
    with pytest.raises(ValueError, match="explicit carbon fraction"):
        inventory.reconcile_exhaust_carbon({}, source="analytic test")
    np.testing.assert_array_equal(inventory.A, before)
    balanced = inventory.reconcile_exhaust_carbon(
        fractions, source="analytic test of carbon conservation"
    )
    np.testing.assert_allclose(balanced.carbon_residual, 0, atol=1e-8)
    delta = report.co2_carbon - balanced.co2_carbon
    np.testing.assert_allclose(
        delta,
        report.known_exhaust_carbon + balanced.specified_other_exhaust_carbon,
        rtol=2e-5,
    )
    corrected = inventory.A.copy()
    inventory.reconcile_exhaust_carbon(
        fractions, source="analytic test of carbon conservation"
    )
    np.testing.assert_array_equal(inventory.A, corrected)
    assert np.isfinite(inventory.calculate_impacts()).all()
