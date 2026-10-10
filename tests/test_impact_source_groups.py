"""Impact source groups must partition contributions without changing totals."""

from copy import deepcopy

import numpy as np
import pytest
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import spsolve

from carculator_utils.inventory import Inventory


def minimal_inventory():
    inv = Inventory.__new__(Inventory)
    names = [
        "market for charger, electric passenger car",
        "charger production, for electric scooter",
        "charger",
        "EV charger, level 3, plugin, 200 kW",
        "EV charger, level 3, with pantograph, 450 kW",
        "charging station, 500W",
    ]
    labels = [(name, "GLO", "unit", name) for name in names]
    labels += [
        (name, ("air",), "kilogram")
        for name in [
            "Carbon dioxide, fossil",
            "Carbon dioxide, non-fossil",
            "Sulfur dioxide",
            "Methane, fossil",
            "Methane, non-fossil",
            "Oxygen",
        ]
    ]
    inv.inputs = {label: i for i, label in enumerate(labels)}
    inv.rev_inputs = {i: label for label, i in inv.inputs.items()}
    inv.exhaust_emissions = []
    inv.noise_emissions = []
    return inv


def test_onboard_and_external_chargers_have_one_distinct_owner():
    inv = minimal_inventory()
    names, indices = inv.get_split_indices()
    for row, expected in enumerate(["powertrain"] * 2 + ["charger"] * 4):
        owners = [name for name, members in zip(names, indices) if row in members]
        assert owners == [expected]


def test_ambiguous_rules_raise_with_supplier_and_group_names(monkeypatch, tmp_path):
    import carculator_utils.inventory as module

    (tmp_path / "lcia").mkdir()
    (tmp_path / "lcia/impact_source_categories.yaml").write_text(
        "powertrain: ['market for charger']\ncharger: ['charger']\n"
        "direct - non-exhaust: []\n"
    )
    monkeypatch.setattr(module, "DATA_DIR", tmp_path)
    with pytest.raises(ValueError, match="market for charger.*powertrain.*charger"):
        minimal_inventory().get_split_indices()


@pytest.fixture(
    scope="module",
    params=[
        ("carculator", "Car", "Small", "BEV", "pkm", {}),
        ("carculator", "Car", "Lower medium", "PHEV-p", "vkm", {}),
        ("carculator_two_wheeler", "TwoWheeler", "Scooter 4-11kW", "BEV", "pkm", {}),
        ("carculator_truck", "Truck", "18t", "BEV", "tkm", {"cycle": "Urban delivery"}),
        ("carculator_bus", "Bus", "13m-city", "BEV-depot", "pkm", {}),
    ],
)
def completed_inventory(request):
    package, prefix, size, powertrain, unit, kwargs = request.param
    module = pytest.importorskip(package)
    ip = getattr(module, prefix + "InputParameters")()
    ip.static()
    _, array = module.fill_xarray_from_input_parameters(
        ip, scope={"size": [size], "powertrain": [powertrain], "year": [2025, 2030]}
    )
    model = getattr(module, prefix + "Model")(array, **kwargs)
    model.set_all()
    inv = getattr(module, "Inventory" + prefix)(
        model, scenario="static", functional_unit=unit
    )
    return inv


@pytest.mark.family
def test_grouped_totals_equal_complete_matrix_solution(completed_inventory):
    inv = completed_inventory
    totals = inv.calculate_impacts().sum("impact")
    columns = [
        i
        for i, label in inv.rev_inputs.items()
        if label[0].startswith(f"transport, {inv.vm.vehicle_type}, ")
    ]
    (column,) = columns
    for y, year in enumerate(inv.scope["year"]):
        load = (
            1
            if inv.func_unit == "vkm"
            else (
                inv.vm["average passengers"].sel(year=year).item()
                if inv.func_unit == "pkm"
                else inv.vm["cargo mass"].sel(year=year).item() / 1000
            )
        )
        demand = np.zeros(inv.A.shape[1])
        demand[column] = 1 / load
        expected = inv.B.isel(year=0).values @ spsolve(
            csc_matrix(inv.A[0, :, :, y]), demand
        )
        np.testing.assert_allclose(
            totals.sel(year=year).values.ravel(), expected, rtol=1e-6, atol=1e-10
        )


@pytest.mark.family
def test_unassigned_direct_contribution_is_rejected(completed_inventory):
    inv = deepcopy(completed_inventory)
    (column,) = [
        i
        for i, label in inv.rev_inputs.items()
        if label[0].startswith(f"transport, {inv.vm.vehicle_type}, ")
    ]
    copper = inv.inputs[("Copper ion", ("water", "ground-"), "kilogram")]
    inv.A[:, copper, column, :] = -1e-6
    with pytest.raises(ValueError, match="no impact source group.*Copper ion"):
        inv.calculate_impacts()
