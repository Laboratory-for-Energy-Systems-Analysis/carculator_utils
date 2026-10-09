"""Fuel shares and properties retain constructor-year provenance."""

import pickle
from copy import deepcopy

import numpy as np
import pytest
import xarray as xr

from carculator_utils.fuel_blends import YEAR_FIELDS, select_fuel_blend
from carculator_utils.inventory import Inventory
from carculator_utils.model import VehicleModel


@pytest.fixture
def model():
    coords = {
        "size": ["Medium"],
        "powertrain": ["ICEV-p"],
        "parameter": ["LHV fuel MJ per kg", "fuel density per kg"],
        "year": [2030, 2020, 2025],
        "value": ["reference", "sample"],
    }
    array = xr.DataArray(np.zeros((1, 1, 2, 3, 2)), coords=coords, dims=list(coords))
    source = {
        "petrol": {
            "primary": {
                "type": "petrol",
                "share": [0.2, 0.4, 0.6],
                "lhv": [20, 30, 40],
                "density": [0.8, 0.82, 0.84],
                "CO2": [3, 2, 1],
                "biogenic share": [0, 0.1, 0.2],
            },
            "secondary": {
                "type": "petrol - bioethanol - sugarbeet",
                "share": [0.8, 0.6, 0.4],
                "lhv": 10,
                "density": 0.7,
                "CO2": 1.8,
                "biogenic share": [1, 0.9, 0.8],
            },
        }
    }
    before = deepcopy(source)
    result = VehicleModel(array, fuel_blend=source)
    assert source == before
    return result


@pytest.mark.parametrize("years", [[2025], [2025, 2030], [2020, 2025, 2030]])
@pytest.mark.parametrize("serialized", [False, True])
def test_selected_properties_and_recomputed_lhv_follow_year_labels(
    model, years, serialized
):
    model.set_average_lhv()
    expected = model.array.copy(deep=True)
    original_blend = deepcopy(model.fuel_blend)
    selected = pickle.loads(pickle.dumps(model)) if serialized else deepcopy(model)
    selected.array = selected.array.sel(year=years)
    scoped = selected.get_fuel_blend()
    indices = [list(model.array.year.values).index(year) for year in years]
    for role, component in original_blend["petrol"].items():
        for field in YEAR_FIELDS:
            source = np.asarray(component[field])
            np.testing.assert_array_equal(
                scoped["petrol"][role][field],
                source[indices] if source.ndim else source,
            )
        assert scoped["petrol"][role]["name"] == component["name"]
    selected.array[:] = 0
    selected.set_average_lhv()
    xr.testing.assert_identical(selected.array, expected.sel(year=years))
    np.testing.assert_equal(selected.fuel_blend, original_blend)
    np.testing.assert_equal(model.fuel_blend, original_blend)
    scoped["petrol"]["primary"]["share"][:] = 99
    np.testing.assert_equal(selected.fuel_blend, original_blend)


def test_subsets_can_be_reselected_from_original_fuel_years(model):
    model.array = model.array.sel(year=[2025])
    np.testing.assert_array_equal(
        model.get_fuel_blend()["petrol"]["primary"]["share"], [0.6]
    )
    np.testing.assert_array_equal(
        model.get_fuel_blend([2020, 2030])["petrol"]["primary"]["share"], [0.4, 0.2]
    )


@pytest.mark.parametrize(
    "years,match",
    [
        ([2040], "no source-year values.*2040"),
        ([2025, 2025], "unique"),
        ([], "nonempty"),
    ],
)
def test_invalid_year_requests_fail_without_mutating_blend(model, years, match):
    before = deepcopy(model.fuel_blend)
    with pytest.raises(ValueError, match=match):
        model.get_fuel_blend(years)
    np.testing.assert_equal(model.fuel_blend, before)


@pytest.mark.parametrize("field", YEAR_FIELDS)
def test_manually_truncated_vectors_are_not_guessed(model, field):
    model.array = model.array.sel(year=[2025])
    model.fuel_blend["petrol"]["primary"][field] = [0.5]
    with pytest.raises(ValueError, match=f"petrol.*primary.*{field}.*source year"):
        model.get_fuel_blend()


def test_legacy_models_missing_year_provenance_fail_before_inventory_allocation(
    model, monkeypatch
):
    del model._fuel_blend_years
    with pytest.raises(ValueError, match="source-year labels are missing.*Rebuild"):
        model.get_fuel_blend()
    model.array = model.array.reindex(
        parameter=[*model.array.parameter.values, "TtW energy"], fill_value=1
    )

    def unexpected_allocation(*args):
        pytest.fail("Missing fuel-year provenance must fail before matrix allocation")

    monkeypatch.setattr(Inventory, "get_A_matrix", unexpected_allocation)
    with pytest.raises(ValueError, match="source-year labels are missing"):
        Inventory(model)


def test_inventory_blend_selection_does_not_follow_later_model_scope_changes(model):
    inventory = Inventory.__new__(Inventory)
    inventory.vm, inventory.scope = model, {"year": [2025, 2030]}
    model.array = model.array.sel(year=[2020])
    np.testing.assert_array_equal(
        inventory.fuel_blend["petrol"]["primary"]["share"], [0.6, 0.2]
    )


def test_empty_blend_keeps_partial_electric_models_permissive():
    assert select_fuel_blend({}, None, [2025]) == {}
