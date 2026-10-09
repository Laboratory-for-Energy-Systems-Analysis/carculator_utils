"""Battery purchases must belong to exactly one selected vehicle and chemistry."""

import csv
import importlib
import importlib.util
import io
import os
import warnings
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.inventory import Inventory, format_array

BATTERIES = {
    "LFP": (
        "market for battery, Li-ion, LFP, rechargeable, prismatic",
        "GLO",
        "kilogram",
        "battery, Li-ion, LFP, rechargeable, prismatic",
    ),
    "NMC-811": (
        "market for battery, Li-ion, NMC811, rechargeable, prismatic",
        "GLO",
        "kilogram",
        "battery, Li-ion, NMC811, rechargeable, prismatic",
    ),
}
USED = ("market for used Li-ion battery", "GLO", "kilogram", "used Li-ion battery")


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("same_chemistry", [False, True])
def test_exact_size_powertrain_year_and_sample_mass_balance(reverse, same_chemistry):
    sizes = ["Medium SUV", "Large", "Medium", "Large SUV"]
    powertrains = ["HEV-p", "PHEV-p", "BEV"]
    years = [2030, 2025]
    shape = (len(sizes), len(powertrains), 2, len(years), 2)
    array = xr.DataArray(
        np.zeros(shape),
        dims=("size", "powertrain", "parameter", "year", "value"),
        coords={
            "size": sizes,
            "powertrain": powertrains,
            "parameter": ["energy battery mass", "battery lifetime replacements"],
            "year": years,
            "value": ["changed", "reference"],
        },
    )
    mass = np.arange(1, 49).reshape(4, 3, 2, 2) * 10
    array.loc[dict(parameter="energy battery mass")] = mass
    array.loc[dict(parameter="battery lifetime replacements", value="changed")] = 1.5
    chemistry = {
        (pt, size, year): (
            "LFP"
            if same_chemistry or (size.endswith(" SUV") + j + k) % 2
            else "NMC-811"
        )
        for size in sizes
        for j, pt in enumerate(powertrains)
        for k, year in enumerate(years)
    }
    if reverse:
        chemistry = dict(reversed(list(chemistry.items())))
    original = deepcopy(chemistry)
    inv = Inventory.__new__(Inventory)
    inv.vm = SimpleNamespace(
        vehicle_type="car", country="CH", energy_storage={"electric": chemistry}
    )
    inv.array = format_array(array)
    inv.scope = {"size": sizes, "powertrain": powertrains, "year": years}
    inv.func_unit, inv.scenario = "vkm", "static"
    vehicles = [
        (f"car, {pt}, {size}", "CH", "unit", "car")
        for size in sizes
        for pt in powertrains
    ]
    inv.inputs = {
        key: i for i, key in enumerate([*BATTERIES.values(), USED, *vehicles])
    }
    inv.rev_inputs = {i: key for key, i in inv.inputs.items()}
    inv.A = np.zeros((2, len(inv.inputs), len(inv.inputs), 2))
    inv.add_battery()
    for i, size in enumerate(sizes):
        for j, pt in enumerate(powertrains):
            col = inv.inputs[(f"car, {pt}, {size}", "CH", "unit", "car")]
            for k, year in enumerate(years):
                expected = mass[i, j, k] * [2.5, 1]
                for chem, key in BATTERIES.items():
                    np.testing.assert_array_equal(
                        -inv.A[:, inv.inputs[key], col, k],
                        expected if chem == chemistry[(pt, size, year)] else 0,
                    )
                np.testing.assert_array_equal(
                    inv.A[:, inv.inputs[USED], col, k], expected
                )
    assert chemistry == original


CASES = [
    (
        "carculator",
        "Car",
        ["Medium", "Medium SUV", "Large", "Large SUV"],
        ["BEV", "HEV-p", "PHEV-p"],
        {},
    ),
    ("carculator_bus", "Bus", ["9m", "13m-city"], ["BEV-depot", "BEV-opp", "FCEV"], {}),
    (
        "carculator_truck",
        "Truck",
        ["7.5t", "40t"],
        ["BEV", "HEV-d", "PHEV-d"],
        {"cycle": "Regional delivery"},
    ),
    (
        "carculator_two_wheeler",
        "TwoWheeler",
        ["Scooter <4kW", "Motorcycle 11-35kW"],
        ["BEV", "ICEV-p"],
        {},
    ),
]


@pytest.fixture(scope="module", params=CASES, ids=lambda case: case[0])
def completed(request):
    name, prefix, sizes, powertrains, kwargs = request.param
    if importlib.util.find_spec(name) is None:
        if os.environ.get("CARCULATOR_REQUIRE_FAMILY") == "1":
            pytest.fail(f"Required family package {name} missing")
        pytest.skip(f"Optional family package {name} missing")
    package = importlib.import_module(name)
    inputs = getattr(package, prefix + "InputParameters")()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs, scope={"size": sizes, "powertrain": powertrains, "year": [2025, 2030]}
    )
    array = array.sel(size=sizes[::-1], year=[2030, 2025]).isel(value=[0, 0])
    array = array.assign_coords(value=["long-life", "reference"])
    array.loc[dict(parameter="lifetime kilometers", value="long-life")] *= 2
    chemistry = {
        (pt, size, year): "LFP" if (i + k) % 2 == 0 else "NMC-811"
        for i, size in enumerate(sizes)
        for pt in array.powertrain.values
        for k, year in enumerate([2025, 2030])
    }
    # HEV and PHEV names overlap as well; their suppliers must stay independent.
    for key in chemistry:
        if key[0].startswith("HEV"):
            chemistry[key] = "NMC-811" if chemistry[key] == "LFP" else "LFP"
    source = array.copy(deep=True)
    storage = {"electric": chemistry}
    original_storage = deepcopy(storage)
    model = getattr(package, prefix + "Model")(
        array, country="CH", energy_storage=storage, **kwargs
    )
    model.set_all()
    xr.testing.assert_identical(array, source)
    assert storage == original_storage
    assert (model["TtW energy"] > 0).all()
    return model, getattr(package, "Inventory" + prefix)


def battery_rows(inventory, column):
    return {
        chem: inventory.get_vehicle_supply_indices(key[0], [column])[0]
        for chem, key in BATTERIES.items()
    }


def battery_impacts(inventory):
    """Isolate battery supply from other foreground construction assumptions."""
    total = inventory.calculate_impacts()
    assert np.isfinite(total).all()
    without = deepcopy(inventory)
    columns = [
        i
        for key, i in inventory.inputs.items()
        if key[0].startswith(inventory.vm.vehicle_type + ", ")
    ]
    for column in columns:
        for row in battery_rows(inventory, column).values():
            without.A[:, row, column, :] = 0
    return total - without.calculate_impacts()


@pytest.mark.family
def test_completed_battery_purchases_equal_selected_pack_and_replacements(completed):
    model, cls = completed
    inventory = cls(model, scenario="static")
    for size in model.array.coords["size"].values:
        for pt in model.array.powertrain.values:
            column = inventory.inputs[
                (
                    f"{model.vehicle_type}, {pt}, {size}",
                    "CH",
                    "unit",
                    model.vehicle_type,
                )
            ]
            rows = battery_rows(inventory, column)
            for y, year in enumerate(model.array.year.values):
                cell = model.array.sel(size=size, powertrain=pt, year=year)
                expected = (
                    cell.sel(parameter="energy battery mass")
                    * (1 + cell.sel(parameter="battery lifetime replacements"))
                ).values
                chosen = model.energy_storage["electric"][(pt, size, year)]
                for chem, row in rows.items():
                    np.testing.assert_allclose(
                        -inventory.A[:, row, column, y],
                        expected if chem == chosen else 0,
                        rtol=2e-6,
                    )
                np.testing.assert_allclose(
                    inventory.A[:, inventory.inputs[USED], column, y],
                    expected,
                    rtol=2e-6,
                )


@pytest.mark.family
@pytest.mark.parametrize("scenario", ["static", "SSP2-NPi"])
def test_selected_battery_impacts_equal_combined_scope(completed, scenario):
    model, cls = completed
    joint = cls(model, scenario=scenario)
    impacts = battery_impacts(joint)
    selected = deepcopy(model)
    # Keep the full chemistry mapping intentionally: omitted vehicles/years and
    # dropped hybrid intermediates must not supply this selected BEV inventory.
    size = model.array.coords["size"].values[0]
    pt = next(p for p in model.array.powertrain.values if p.startswith("BEV"))
    selected.array = model.array.sel(
        size=[size], powertrain=[pt], year=[2025], value=["long-life"]
    )
    single = cls(selected, scenario=scenario)
    xr.testing.assert_allclose(
        battery_impacts(single),
        impacts.sel(size=[size], powertrain=[pt], year=[2025], value=["long-life"]),
        rtol=2e-6,
        atol=1e-9,
    )


@pytest.mark.family
@pytest.mark.export
@pytest.mark.parametrize("version", ["3.9", "3.10"])
def test_battery_exports_are_exact_and_repeatable(completed, version):
    pytest.importorskip("bw2io")
    model, cls = completed
    model = deepcopy(model)
    model.array = model.array.sel(value=["long-life"])
    original_model = model.array.copy(deep=True)
    original_storage = deepcopy(model.energy_storage)
    inventory = cls(model, scenario="static")
    matrix, labels = inventory.A.copy(), inventory.inputs.copy()
    expected_by_year = {}
    for _ in range(2):
        importers = inventory.export_lci(format="bw2io", ecoinvent_version=version)
        assert len(importers) == 2
        for year, importer in zip(model.array.year.values, importers):
            vehicles = [
                a
                for a in importer.data
                if a["name"].startswith(model.vehicle_type + ", ")
            ]
            expected = []
            for size in model.array.coords["size"].values:
                for pt in model.array.powertrain.values:
                    cell = model.array.sel(size=size, powertrain=pt, year=year)
                    mass = (
                        cell.sel(parameter="energy battery mass")
                        * (1 + cell.sel(parameter="battery lifetime replacements"))
                    ).item()
                    if mass:
                        chem = model.energy_storage["electric"][(pt, size, year)]
                        expected.append((size, BATTERIES[chem], mass))
            actual = []
            for vehicle in vehicles:
                size = vehicle["name"].rsplit(", ", 1)[-1]
                batteries = [
                    e
                    for e in vehicle["exchanges"]
                    if any(e["name"].startswith(key[0]) for key in BATTERIES.values())
                ]
                assert len(batteries) <= 1
                for e in batteries:
                    assert e["type"] == "technosphere"
                    actual.append(
                        (
                            size,
                            (
                                e["name"].split(" [for ")[0],
                                e["location"],
                                e["unit"],
                                e["reference product"],
                            ),
                            e["amount"],
                        )
                    )
            actual, expected = sorted(actual), sorted(expected)
            expected_by_year[year] = expected
            assert [(s, k) for s, k, _ in actual] == [(s, k) for s, k, _ in expected]
            np.testing.assert_allclose(
                [m for _, _, m in actual], [m for _, _, m in expected], rtol=2e-6
            )
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*noise.*", category=UserWarning)
        csvs = inventory.export_lci(
            software="simapro", format="string", ecoinvent_version=version
        )
    assert len(csvs) == 2
    for year, content in zip(model.array.year.values, csvs):
        section, is_vehicle, actual = None, False, []
        for row in csv.reader(io.StringIO(content), delimiter=";"):
            if row == ["Process"]:
                section, is_vehicle = None, False
            elif not row or not row[0]:
                section = None
            elif len(row) == 1:
                section = row[0]
            elif section == "Products":
                is_vehicle = f"| {model.vehicle_type}, " in row[0].lower()
            elif section == "Materials/fuels" and is_vehicle:
                for chem, key in BATTERIES.items():
                    if key[0].lower() in row[0].lower():
                        assert row[1] == "kg"
                        actual.append((chem, float(row[2])))
        expected = sorted(
            (chem, mass)
            for _, key, mass in expected_by_year[year]
            for chem, identity in BATTERIES.items()
            if key == identity
        )
        actual.sort()
        assert [chem for chem, _ in actual] == [chem for chem, _ in expected]
        np.testing.assert_allclose(
            [mass for _, mass in actual], [mass for _, mass in expected], rtol=2e-6
        )
    np.testing.assert_array_equal(inventory.A, matrix)
    assert inventory.inputs == labels
    xr.testing.assert_identical(model.array, original_model)
    assert model.energy_storage == original_storage
