import numpy as np
import pytest

from carculator_utils.inventory import Inventory, check_scenario, get_dict_input


def test_get_dict_input_parses_compartment_tuples():
    inputs = get_dict_input()

    assert ("Copper ion", ("water", "ground-"), "kilogram") in inputs


@pytest.mark.parametrize(
    "scenario",
    ["SSP2-NPi", "SSP2-PkBudg1000", "SSP2-PkBudg650", "static"],
)
def test_check_scenario_accepts_current_scenarios(scenario):
    assert check_scenario(scenario) == scenario


@pytest.mark.parametrize("scenario", ["SSP2-PkBudg1150", "SSP2-PkBudg500"])
def test_check_scenario_rejects_legacy_scenarios(scenario):
    with pytest.raises(ValueError):
        check_scenario(scenario)


@pytest.fixture
def fuel_inventory():
    inventory = Inventory.__new__(Inventory)
    labels = [
        ("target fuel", "CH", "kilogram", "fuel"),
        ("electricity, original", "CH", "kilowatt hour", "electricity"),
        ("electricity, replacement", "CH", "kilowatt hour", "electricity"),
        ("fuel intermediate", "CH", "kilogram", "intermediate"),
        ("unrelated battery", "CH", "kilogram", "battery"),
    ]
    inventory.inputs = {key: i for i, key in enumerate(labels)}
    inventory.rev_inputs = dict(enumerate(labels))
    inventory.A = np.broadcast_to(np.eye(5)[None, :, :, None], (2, 5, 5, 2)).copy()
    inventory.A[:, 1, 4, :] = -7
    return inventory


def rewire_fuel(inventory, **kwargs):
    inventory.find_input_requirement(
        "kilowatt hour", "target fuel", find_input_by="unit", replace_by=[2], **kwargs
    )


def test_fuel_rewiring_ignores_unrelated_solver_residuals(fuel_inventory, monkeypatch):
    inventory = fuel_inventory
    # Keep a real, very small link and a supply loop. A numerical threshold
    # would lose the link; a traversal must also terminate at the loop.
    inventory.A[:, 3, 0, :] = -1e-30
    inventory.A[:, 0, 3, :] = -0.2
    inventory.A[:, 1, 3, :] = -2
    inventory.A[:, 2, 3, :] = -0.5
    before = inventory.A.copy()
    # Sparse solvers can report tiny residuals for disconnected activities.
    monkeypatch.setattr(
        "carculator_utils.inventory.sparse.linalg.spsolve",
        lambda *args, **kwargs: np.array([1, 2e-30, 0.5e-30, 1e-30, 1e-35]),
    )
    rewire_fuel(inventory)
    expected = before.copy()
    expected[:, 1, 3, :] = 0
    expected[:, 2, 3, :] = -2.5
    np.testing.assert_array_equal(inventory.A, expected)
    rewire_fuel(inventory)
    np.testing.assert_array_equal(inventory.A, expected)


@pytest.mark.parametrize("sample,year", [(0, 1), (1, 0), (1, 1)])
def test_fuel_rewiring_finds_routes_in_later_cells(fuel_inventory, sample, year):
    inventory = fuel_inventory
    inventory.A[sample, 3, 0, year] = -1
    inventory.A[sample, 1, 3, year] = -2
    expected = inventory.A.copy()
    expected[sample, 1, 3, year] = 0
    expected[sample, 2, 3, year] = -2
    rewire_fuel(inventory)
    np.testing.assert_array_equal(inventory.A, expected)


def test_fuel_rewiring_does_not_cancel_inputs_across_samples(fuel_inventory):
    inventory = fuel_inventory
    inventory.A[:, 3, 0, :] = -1
    inventory.A[0, 1, 3, :] = -2
    inventory.A[1, 1, 3, :] = 2
    expected = inventory.A.copy()
    expected[:, 1, 3, :] = 0
    expected[0, 2, 3, :] = -2
    expected[1, 2, 3, :] = 2
    rewire_fuel(inventory, filter_activities=["fuel intermediate"])
    np.testing.assert_array_equal(inventory.A, expected)
