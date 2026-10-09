"""Sample identity through completed models, characterization and export."""

import csv
import importlib
import importlib.util
import io
import os
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.inventory import Inventory


@pytest.mark.parametrize("labels", [[9, 2], [1.0], ["changed", "reference"]])
@pytest.mark.parametrize("sensitivity", [False, True])
def test_results_table_retains_sample_labels(labels, sensitivity):
    inventory = Inventory.__new__(Inventory)
    inventory.array = xr.DataArray(labels, dims="value", coords={"value": labels})
    inventory.iterations = len(labels)
    inventory.impact_categories = {"climate change": {}}
    inventory.scope = {"size": ["Medium"], "powertrain": ["BEV"], "year": [2025]}
    inventory.list_cat = ["energy chain"]
    results = inventory.get_results_table(sensitivity=sensitivity)
    xr.testing.assert_identical(results.value, inventory.array.value)


@pytest.mark.parametrize("matrix_samples,model_samples", [(2, 2), (1, 2), (2, 1)])
def test_export_rejects_multiple_or_inconsistent_samples(matrix_samples, model_samples):
    from carculator_utils.export import ExportInventory

    exporter = ExportInventory.__new__(ExportInventory)
    exporter.array = np.zeros((matrix_samples, 0, 0, 1))
    exporter.vm = SimpleNamespace(
        array=xr.DataArray(np.zeros(model_samples), dims="value")
    )
    with pytest.raises(ValueError, match="Select one sample.*before constructing"):
        exporter.write_lci("3.10", 2025)


CASES = [
    ("carculator", "Car", "Medium", "BEV", "pkm", {}),
    ("carculator_bus", "Bus", "13m-city", "BEV-depot", "pkm", {}),
    ("carculator_truck", "Truck", "40t", "ICEV-d", "tkm", {"cycle": "Long haul"}),
    ("carculator_two_wheeler", "TwoWheeler", "Motorcycle 11-35kW", "BEV", "pkm", {}),
]


@pytest.fixture(params=CASES, ids=lambda case: case[0])
def family(request):
    name, prefix, size, powertrain, unit, kwargs = request.param
    if importlib.util.find_spec(name) is None:
        if os.environ.get("CARCULATOR_REQUIRE_FAMILY") == "1":
            pytest.fail(f"Required family package {name} missing")
        pytest.skip(f"Optional family package {name} missing")
    package = importlib.import_module(name)
    return SimpleNamespace(
        inputs=getattr(package, prefix + "InputParameters")(),
        model_type=getattr(package, prefix + "Model"),
        inventory_type=getattr(package, "Inventory" + prefix),
        scope={"size": [size], "powertrain": [powertrain], "year": [2025, 2030]},
        unit=unit,
        kwargs=kwargs,
    )


def complete_model(family, source):
    before = source.copy(deep=True)
    model = family.model_type(source, **family.kwargs)
    model.set_all()
    xr.testing.assert_identical(source, before)
    assert (model["TtW energy"] > 0).all()
    return model


def inventory_for(family, model):
    return family.inventory_type(model, scenario="static", functional_unit=family.unit)


@pytest.mark.family
def test_completed_stochastic_selection_and_reordering(family):
    family.inputs.stochastic(3, seed=42)
    _, source = fill_xarray_from_input_parameters(family.inputs, scope=family.scope)
    model = complete_model(family, source)
    original = inventory_for(family, model)
    expected = original.calculate_impacts()
    assert np.isfinite(expected).all()
    del original

    reordered = deepcopy(model)
    reordered.array = reordered.array.isel(value=[2, 0, 1])
    actual = inventory_for(family, reordered).calculate_impacts()
    xr.testing.assert_allclose(actual, expected.isel(value=[2, 0, 1]))

    # The original failure: construct and complete a model from sample 1 alone.
    selected = source.isel(value=[1])
    chosen = complete_model(family, selected)
    inventory = inventory_for(family, chosen)
    impacts = inventory.calculate_impacts()
    np.testing.assert_array_equal(impacts.value, selected.value)

    # Relabelling the same inputs must not change physics, inventories or LCIA.
    control = complete_model(family, selected.assign_coords(value=[0]))
    for parameter in ("driving mass", "TtW energy", "electric energy stored"):
        np.testing.assert_array_equal(
            chosen[parameter].values, control[parameter].values
        )
    control_inventory = inventory_for(family, control)
    np.testing.assert_array_equal(inventory.A, control_inventory.A)
    np.testing.assert_allclose(impacts, control_inventory.calculate_impacts())


@pytest.mark.family
@pytest.mark.export
@pytest.mark.parametrize("label", [1, "reference"])
def test_selected_sample_exports_preserve_data_and_metadata(family, label, tmp_path):
    pytest.importorskip("bw2io")
    family.inputs.stochastic(2, seed=42)
    _, source = fill_xarray_from_input_parameters(family.inputs, scope=family.scope)
    model = complete_model(family, source.isel(value=[1]).assign_coords(value=[label]))
    inventory = inventory_for(family, model)
    impacts = inventory.calculate_impacts()
    before = inventory.A.copy()
    model_before = model.array.copy(deep=True)
    inputs, reverse = inventory.inputs.copy(), inventory.rev_inputs.copy()

    powertrain = family.scope["powertrain"][0]
    energy_supplier = (
        "fuel supply for diesel vehicles"
        if powertrain == "ICEV-d"
        else "electricity supply for electric vehicles"
    )
    for _ in range(2):
        exports = inventory.export_lci(format="bw2io", directory=tmp_path)
        assert len(exports) == 2
        for year, importer in zip(family.scope["year"], exports):
            (transport,) = [
                activity
                for activity in importer.data
                if activity["name"].startswith(f"transport, {model.vehicle_type}, ")
            ]
            consumption = model["electricity consumption"].sel(year=year).item()
            if powertrain == "ICEV-d":
                consumption = (
                    (model["fuel consumption"] * model["fuel density per kg"])
                    .sel(year=year)
                    .item()
                )
            load = (
                model["cargo mass" if family.unit == "tkm" else "average passengers"]
                .sel(year=year)
                .item()
            )
            if family.unit == "tkm":
                load /= 1000
            (exchange,) = [
                e for e in transport["exchanges"] if e["name"] == energy_supplier
            ]
            assert exchange["amount"] == pytest.approx(consumption / load, rel=1e-6)
            energy = model["TtW energy"].sel(year=year).item()
            assert (
                f"Tank-to-wheel energy consumption: {int(energy)} kj/km"
                in transport["comment"]
            )
            assert f"Manufacture year: {year}" in transport["comment"]

        strings = inventory.export_lci(
            software="simapro", format="string", directory=tmp_path
        )
        assert len(strings) == 2
        for year, content, importer in zip(family.scope["year"], strings, exports):
            assert isinstance(content, str)
            assert f"Transport, {model.vehicle_type}," in content
            assert ("tkm" if family.unit == "tkm" else "personkm") in content
            rows = list(csv.reader(io.StringIO(content), delimiter=";"))
            # Compare each vehicle's metadata in the serialized CSV with Brightway.
            for activity in importer.data:
                if "Manufacture year:" not in activity.get("comment", ""):
                    continue
                index = next(
                    i
                    for i, row in enumerate(rows)
                    if row == ["Process name"]
                    and f"| {activity['name']} |" in rows[i + 1][0]
                    and f"{{{activity['location']}}}" in rows[i + 1][0]
                )
                comment = rows[rows.index(["Comment"], index) + 1][0]
                assert comment == activity["comment"]
                assert f"Manufacture year: {year}." in comment
                assert "Originally published in: None" not in comment
    np.testing.assert_array_equal(inventory.A, before)
    assert inventory.inputs == inputs
    assert inventory.rev_inputs == reverse
    xr.testing.assert_identical(model.array, model_before)
    xr.testing.assert_identical(inventory.calculate_impacts(), impacts)


@pytest.mark.family
def test_sensitivity_uses_named_reference_after_reordering(family):
    family.inputs.static()
    _, source = fill_xarray_from_input_parameters(
        family.inputs, scope=family.scope, sensitivity=True
    )
    source = source.sel(value=["glider base mass", "reference"])
    model = complete_model(family, source)
    inventory = inventory_for(family, model)
    absolute = inventory.calculate_impacts().sum("impact")
    assert np.isfinite(absolute).all()
    reference = absolute.sel(value="reference")
    ratios = inventory.calculate_impacts(sensitivity=True)
    xr.testing.assert_allclose(ratios, absolute / reference.where(reference != 0))
    assert ratios.value.values.tolist() == ["glider base mass", "reference"]
    assert (ratios.sel(value="reference").where(reference != 0, 1) == 1).all()
