"""Pressure boundaries, blend accounting, and real family LCIA regressions."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from carculator_utils.background_systems import BackgroundSystemModel
from carculator_utils.inventory import Inventory, hydrogen_compression_electricity


def test_compression_matches_doe_order_of_magnitude_and_thermodynamic_bound():
    # DOE Program Record 9013: approximately 3 kWh/kg, 20 -> 880 bar.
    assert hydrogen_compression_electricity(20, 880) == pytest.approx(3.0, rel=0.03)
    # Reversible isothermal work is an independent lower bound (J -> kWh).
    reversible = 8.314462618 / 0.00201588 * 300 * np.log(700 / 30) / 3.6e6
    actual = hydrogen_compression_electricity(30, 700)
    assert reversible < actual < 3.0
    assert actual > hydrogen_compression_electricity(100, 700)
    assert actual > hydrogen_compression_electricity(30, 350)
    assert actual > hydrogen_compression_electricity(30, 700, stages=6)


@pytest.mark.parametrize("inlet", [700, 900])
def test_no_compression_or_negative_credit_at_sufficient_delivery_pressure(inlet):
    assert hydrogen_compression_electricity(inlet, 700) == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("inlet_pressure", 0),
        ("inlet_pressure", float("nan")),
        ("outlet_pressure", -1),
        ("temperature", float("inf")),
        ("stages", 1.5),
        ("stages", True),
        ("isentropic_efficiency", 1.01),
        ("motor_efficiency", 0),
        ("temperature", "300"),
        ("temperature", 300 + 0j),
    ],
)
def test_invalid_compressor_inputs_fail(field, value):
    args = {"inlet_pressure": 30, "outlet_pressure": 700, field: value}
    with pytest.raises(ValueError, match="Hydrogen compression"):
        hydrogen_compression_electricity(**args)


@pytest.fixture
def inventory():
    inv = Inventory.__new__(Inventory)
    inv.bs = BackgroundSystemModel()
    blends = inv.bs.define_fuel_blends(["FCEV"], "CH", [2030, 2025])
    for role, fuel, shares in (
        ("primary", "hydrogen - electrolysis - PEM", [0.25, 1.0]),
        ("secondary", "hydrogen - electrolysis - AEC", [0.75, 0.0]),
    ):
        blends["hydrogen"][role].update(
            type=fuel,
            name=tuple(inv.bs.fuel_specs[fuel]["name"]),
            share=np.array(shares),
        )
    inv.vm = SimpleNamespace(
        fuel_blend=blends, _fuel_blend_years=(2030, 2025), energy_storage={}
    )
    inv.scope = {"year": [2025, 2030]}
    inv.background_configuration = {}
    keys = [
        (
            "electricity supply for fuel preparation",
            "CH",
            "kilowatt hour",
            "electricity",
        ),
        ("fuel supply for hydrogen vehicles", "CH", "kilogram", "fuel"),
        blends["hydrogen"]["primary"]["name"],
        blends["hydrogen"]["secondary"]["name"],
    ]
    inv.inputs = {key: i for i, key in enumerate(keys)}
    inv.rev_inputs = dict(enumerate(keys))
    inv.A = np.broadcast_to(np.eye(4)[None, :, :, None], (2, 4, 4, 2)).copy()
    inv.A[:, 0, 2, :] = -54
    return inv


def test_blended_compression_retains_years_samples_and_producer_boundary(inventory):
    inv = inventory
    original, blend = inv.A.copy(), deepcopy(inv.vm.fuel_blend)
    inv.add_hydrogen_compression_electricity()
    pem = hydrogen_compression_electricity(30, 700)
    aec = hydrogen_compression_electricity(20, 700)
    np.testing.assert_allclose(-inv.A[:, 0, 1, :], [[pem, 0.25 * pem + 0.75 * aec]] * 2)
    np.testing.assert_equal(inv.A[:, :, 2:, :], original[:, :, 2:, :])
    np.testing.assert_equal(inv.vm.fuel_blend, blend)
    first = inv.A.copy()
    inv.add_hydrogen_compression_electricity()
    np.testing.assert_equal(inv.A, first)


def test_explicit_delivery_pressure_overrides_labels_without_mutation(inventory):
    config = {
        "delivery pressure": {
            "hydrogen - electrolysis - PEM": 700,
            "hydrogen - electrolysis - AEC": 900,
        }
    }
    before = deepcopy(config)
    inventory.background_configuration = {"hydrogen compression": config}
    inventory.add_hydrogen_compression_electricity()
    assert not inventory.A[:, 0, 1, :].any()
    assert config == before


def test_unknown_active_pressure_fails_but_zero_share_is_ignored(inventory):
    component = inventory.vm.fuel_blend["hydrogen"]["secondary"]
    component["name"] = ("custom hydrogen", "CH", "kilogram", "hydrogen")
    with pytest.raises(ValueError, match="delivery pressure is unspecified"):
        inventory.add_hydrogen_compression_electricity()
    component["share"][:] = 0
    inventory.add_hydrogen_compression_electricity()


def test_catalogue_pressure_proxy_is_visible_in_audit_metadata(inventory):
    fuel = "hydrogen - smr - natural gas"
    component = inventory.vm.fuel_blend["hydrogen"]["primary"]
    component.update(type=fuel, name=tuple(inventory.bs.fuel_specs[fuel]["name"]))
    inventory.add_hydrogen_compression_electricity()
    record = inventory.hydrogen_compression["components"][0]
    assert record["inlet pressure bar"] == 25
    assert record["pressure source"] == "catalogue pressure assumption"


def test_every_catalogued_hydrogen_route_has_a_documented_pressure(inventory):
    for fuel, spec in inventory.bs.fuel_specs.items():
        if not fuel.startswith("hydrogen -"):
            continue
        component = inventory.vm.fuel_blend["hydrogen"]["primary"]
        component.update(type=fuel, name=tuple(spec["name"]))
        inventory.add_hydrogen_compression_electricity()
        record = inventory.hydrogen_compression["components"][0]
        assert record["inlet pressure bar"] > 0
        assert record["electricity kWh/kg"] > 0


@pytest.mark.parametrize(
    "config",
    [
        None,
        {"efficiency": 0.5},
        {"delivery pressure": 30},
        {"delivery pressure": {"unselected fuel": 30}},
    ],
)
def test_invalid_inventory_compression_configuration_fails(inventory, config):
    inventory.background_configuration = {"hydrogen compression": config}
    with pytest.raises(ValueError, match="Hydrogen"):
        inventory.add_hydrogen_compression_electricity()


def test_target_pressure_follows_selected_tank_inventory(inventory, monkeypatch):
    monkeypatch.setattr(
        inventory, "_hydrogen_tank_name", lambda: "hydrogen tank, 350bar"
    )
    inventory.add_hydrogen_compression_electricity()
    assert inventory.hydrogen_compression["tank pressure bar"] == 350
    assert -inventory.A[0, 0, 1, 0] == pytest.approx(
        hydrogen_compression_electricity(30, 350)
    )


@pytest.mark.parametrize(
    "package_name,prefix,size,kwargs",
    [
        ("carculator", "Car", "Medium", {}),
        ("carculator_bus", "Bus", "13m-city", {}),
        ("carculator_truck", "Truck", "40t", {"cycle": "Long haul"}),
    ],
)
def test_real_family_inventory_compression_changes_only_fuel_supply(
    package_name, prefix, size, kwargs
):
    package = pytest.importorskip(package_name)
    from carculator_utils.array import fill_xarray_from_input_parameters

    inputs = getattr(package, prefix + "InputParameters")()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs, scope={"size": [size], "powertrain": ["FCEV"], "year": [2025]}
    )
    model = getattr(package, prefix + "Model")(array, **kwargs)
    model.set_all()
    cls = getattr(package, "Inventory" + prefix)
    compressed = cls(model, method="ef")
    before = compressed.A.copy()
    # Equal delivery/tank pressures remove only the compression purchase.
    pressures = {c["type"]: 700 for c in model.fuel_blend["hydrogen"].values()}
    uncompressed = cls(
        model,
        method="ef",
        background_configuration={
            "hydrogen compression": {"delivery pressure": pressures}
        },
    )
    (row,) = compressed.find_input_indices(("electricity supply for fuel preparation",))
    (market,) = compressed.find_input_indices(("fuel supply for hydrogen vehicles",))
    expected = uncompressed.A.copy()
    expected[:, row, market, :] = before[:, row, market, :]
    np.testing.assert_array_equal(before, expected)
    delta = (
        compressed.calculate_impacts().sel(impact_category="climate change").sum()
        - uncompressed.calculate_impacts().sel(impact_category="climate change").sum()
    )
    # Independently solve only the electricity supplier to price the added demand.
    from scipy.sparse import csc_matrix
    from scipy.sparse.linalg import spsolve

    demand = np.zeros(before.shape[1])
    demand[row] = 1
    supply = spsolve(csc_matrix(before[0, :, :, 0]), demand)
    factor = float(
        compressed.B.sel(category="climate change").interp(year=2025).values @ supply
    )
    h2_per_km = float(
        (model["fuel consumption"] * model["fuel density per kg"]).values.item()
    )
    expected_delta = h2_per_km * -before[0, row, market, 0] * factor
    assert expected_delta > 0
    assert float(delta) == pytest.approx(expected_delta, rel=2e-5)
    np.testing.assert_array_equal(compressed.A, before)
