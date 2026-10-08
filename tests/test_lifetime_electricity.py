"""Independent electricity averages and completed scope-invariance checks."""

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
from carculator_utils.inventory_electricity import lifetime_mix

CASES = [
    ("carculator", "Car", "Medium", "BEV", "pkm", {}),
    ("carculator_bus", "Bus", "13m-city", "BEV-depot", "pkm", {}),
    ("carculator_truck", "Truck", "40t", "BEV", "tkm", {"cycle": "Regional delivery"}),
    ("carculator_two_wheeler", "TwoWheeler", "Motorcycle 11-35kW", "BEV", "pkm", {}),
]


def family_case(case):
    name, prefix, size, powertrain, unit, kwargs = case
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


@pytest.fixture(params=CASES, ids=lambda case: case[0])
def family(request):
    return family_case(request.param)


def complete_model(case, source):
    model = case.model_type(source, **case.kwargs)
    model.set_all()
    assert (model["TtW energy"] > 0).all()
    return model


def inventory_for(case, model):
    return case.inventory_type(model, scenario="static", functional_unit=case.unit)


def small_inputs():
    data = xr.DataArray(
        np.ones((2, 1, 3, 1)),
        dims=("value", "combined_dim", "parameter", "year"),
        coords={
            "value": [9, 2],
            "combined_dim": ["Small - BEV"],
            "parameter": ["lifetime kilometers", "kilometers per year", "TtW energy"],
            "year": [2025],
        },
    )
    data.loc[dict(parameter="lifetime kilometers")] = np.array([5, 2])[:, None, None]
    generation = xr.DataArray(
        [[1, 0], [0, 1]],
        dims=("year", "variable"),
        coords={"year": [2025, 2030], "variable": ["coal", "wind"]},
    )
    return data, generation


def test_each_sample_gets_its_own_annual_average():
    data, generation = small_inputs()
    result = lifetime_mix(data, generation, ["wind", "coal"])
    np.testing.assert_allclose(result.values[:, 0, 0], [[0.4, 0.6], [0.1, 0.9]])
    assert result.value.values.tolist() == [9, 2]
    assert result.technology.values.tolist() == ["wind", "coal"]


@pytest.mark.parametrize(
    "duration,year,expected",
    [(0.5, 2025, [1, 0]), (25, 2025, [0.5, 0.5]), (25, 2040, [0, 1])],
)
def test_short_lifetime_and_background_horizon(duration, year, expected):
    data, generation = small_inputs()
    data = data.assign_coords(year=[year])
    data.loc[dict(parameter="lifetime kilometers")] = duration
    result = lifetime_mix(data, generation, ["coal", "wind"])
    np.testing.assert_allclose(result.values[:, 0, 0], [expected, expected])


@pytest.mark.parametrize("duration", [0, -1, np.nan, np.inf])
def test_invalid_active_lifetime_has_context(duration):
    data, generation = small_inputs()
    data.loc[dict(parameter="lifetime kilometers", value=2)] = duration
    with pytest.raises(ValueError, match="operating lifetime.*Small - BEV.*2025"):
        lifetime_mix(data, generation, ["coal", "wind"])
    data.loc[dict(parameter="TtW energy", value=2)] = 0
    assert np.isfinite(lifetime_mix(data, generation, ["coal", "wind"])).all()


def test_custom_mix_is_preserved_and_broadcast_without_mutation():
    data, generation = small_inputs()
    custom = np.array([[0.25, 0.75]])
    result = lifetime_mix(data, generation, ["coal", "wind"], custom)
    np.testing.assert_allclose(result.values[:, 0, 0], [[0.25, 0.75]] * 2)
    np.testing.assert_array_equal(custom, [[0.25, 0.75]])


@pytest.mark.parametrize("custom", [[[0, 0]], [[np.nan, 1]], [[1, 0], [1, 0]], [[1]]])
def test_invalid_custom_mix_fails_clearly(custom):
    data, generation = small_inputs()
    with pytest.raises(ValueError, match="[Ee]lectricity mix"):
        lifetime_mix(data, generation, ["coal", "wind"], custom)


@pytest.mark.family
def test_completed_samples_agree_alone_together_and_reordered(family):
    family.inputs.static()
    _, source = fill_xarray_from_input_parameters(family.inputs, scope=family.scope)
    source = source.isel(value=[0, 0]).assign_coords(value=[9, 2])
    source.loc[dict(parameter="lifetime kilometers")] = xr.DataArray(
        [100000, 500000], dims="value", coords={"value": [9, 2]}
    )
    source.loc[dict(parameter="kilometers per year")] = 20000
    family.kwargs = {**family.kwargs, "country": "DE"}
    model = complete_model(family, source)
    inventory = inventory_for(family, model)
    together = inventory.calculate_impacts()
    mixes = inventory.electricity_mix.copy(deep=True)
    del inventory
    assert not np.allclose(mixes.sel(value=9), mixes.sel(value=2))
    for sample in [9, 2]:
        selected = complete_model(family, source.sel(value=[sample]))
        standalone = inventory_for(family, selected)
        xr.testing.assert_allclose(
            standalone.calculate_impacts(), together.sel(value=[sample])
        )
        xr.testing.assert_identical(
            standalone.electricity_mix, mixes.sel(value=[sample])
        )
        del standalone
    reordered = deepcopy(model)
    reordered.array = reordered.array.sel(value=[2, 9])
    xr.testing.assert_allclose(
        inventory_for(family, reordered).calculate_impacts(), together.sel(value=[2, 9])
    )


@pytest.mark.family
@pytest.mark.parametrize("powertrain", ["BEV", "FCEV", "ICEV-g"])
@pytest.mark.parametrize("scenario", ["static", "SSP2-NPi"])
def test_two_vehicle_sizes_keep_independent_supplies(powertrain, scenario):
    case = family_case(CASES[0])
    case.inputs.static()
    case.scope = {
        "size": ["Medium", "Large"],
        "powertrain": [powertrain],
        "year": [2025, 2030],
    }
    _, source = fill_xarray_from_input_parameters(case.inputs, scope=case.scope)
    source = source.isel(value=[0, 0]).assign_coords(value=[9, 2])
    source = source.sel(year=[2030, 2025])
    source.loc[dict(parameter="kilometers per year")] = 20000
    for size, lifetimes in [("Medium", [100000, 200000]), ("Large", [300000, 500000])]:
        source.loc[dict(parameter="lifetime kilometers", size=size)] = xr.DataArray(
            lifetimes, dims="value", coords={"value": [9, 2]}
        )
    model = case.model_type(source, country="DE")
    model.set_all()
    inventory = case.inventory_type(model, scenario=scenario)
    result = inventory.calculate_impacts()
    assert inventory.electricity_supply_originals
    assert np.isfinite(result).all()
    for size in source.coords["size"].values:
        selected = deepcopy(model)
        selected.array = selected.array.sel(size=[size])
        individual = case.inventory_type(selected, scenario=scenario)
        xr.testing.assert_allclose(
            individual.calculate_impacts(), result.sel(size=[size])
        )
    # Supplying a fixed mix must remove the need for vehicle-specific copies.
    custom = inventory.electricity_mix.isel(value=0, combined_dim=0).values.copy()
    fixed = case.inventory_type(
        model,
        scenario=scenario,
        background_configuration={"custom electricity mix": custom},
    )
    assert not fixed.electricity_supply_originals
    np.testing.assert_allclose(fixed.mix, custom)


@pytest.mark.family
@pytest.mark.export
@pytest.mark.parametrize("powertrain", ["BEV", "FCEV", "ICEV-g"])
def test_vehicle_specific_supplies_survive_export(powertrain, tmp_path):
    pytest.importorskip("bw2io")
    case = family_case(CASES[0])
    case.inputs.static()
    _, source = fill_xarray_from_input_parameters(
        case.inputs,
        scope={
            "size": ["Large", "Medium"],
            "powertrain": [powertrain],
            "year": [2025, 2030],
        },
    )
    source = source.assign_coords(value=[7])
    source.loc[dict(parameter="kilometers per year")] = 20000
    source.loc[dict(parameter="lifetime kilometers", size="Large")] = 100000
    source.loc[dict(parameter="lifetime kilometers", size="Medium")] = 500000
    model = case.model_type(source, country="DE")
    model.set_all()
    inventory = case.inventory_type(model, scenario="static", functional_unit="pkm")
    before = inventory.A.copy()
    inputs = inventory.inputs.copy()
    impacts = inventory.calculate_impacts()
    assert inventory.electricity_supply_originals
    if powertrain == "BEV":
        inventory.add_electricity_to_electric_vehicles()
    elif powertrain == "FCEV":
        inventory.add_hydrogen_to_fuel_cell_vehicles()
    else:
        inventory.add_methane_leakage()
    np.testing.assert_array_equal(inventory.A, before)
    for _ in range(2):
        exports = inventory.export_lci(format="bw2io", directory=tmp_path)
        strings = inventory.export_lci(
            software="simapro", format="string", directory=tmp_path
        )
        for year, importer, content in zip([2025, 2030], exports, strings):
            markets = [
                a
                for a in importer.data
                if a["name"].startswith("electricity supply for fuel preparation")
            ]
            assert len(markets) == 2
            for activity, size in zip(markets, ["Large", "Medium"]):
                expected = inventory.electricity_mix.sel(
                    value=7, combined_dim=f"{size} - {powertrain}", year=year
                )
                for technology, share in zip(
                    inventory.electricity_technologies, expected.values
                ):
                    generator = inventory.elec_map[technology][0]
                    actual = sum(
                        e["amount"]
                        for e in activity["exchanges"]
                        if e["name"].startswith(generator)
                    )
                    assert actual == pytest.approx(share * inventory.electricity_losses)
            # Each new supplier must be referenced by its own exported product,
            # not collapsed to a generic electricity or fuel label in SimaPro.
            rows = list(csv.reader(io.StringIO(content), delimiter=";"))
            new_names = {a["name"] for a in importer.data if " [for " in a["name"]}
            assert new_names
            for activity in importer.data:
                for exchange in activity["exchanges"]:
                    if (
                        exchange["type"] != "technosphere"
                        or exchange["name"] not in new_names
                    ):
                        continue
                    product = f"{exchange['name'].capitalize()} {{{exchange['location']}}} | Cut-off U"
                    assert any(len(row) == 7 and row[0] == product for row in rows), (
                        product,
                        [
                            row
                            for row in rows
                            if row and row[0].startswith(product.split(" {")[0])
                        ],
                    )
    np.testing.assert_array_equal(inventory.A, before)
    assert inventory.inputs == inputs
    xr.testing.assert_identical(inventory.calculate_impacts(), impacts)
