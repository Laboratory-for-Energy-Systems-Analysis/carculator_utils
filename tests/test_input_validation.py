"""Malformed inputs fail at the public boundary with useful context."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.background_systems import BackgroundSystemModel
from carculator_utils.model import VehicleModel
from carculator_utils.vehicle_input_parameters import (
    VehicleInputParameters,
    validate_parameters,
)


def records():
    return {
        "mass-2020": {
            "name": "mass",
            "amount": 10.0,
            "loc": 10.0,
            "minimum": 5.0,
            "maximum": 15.0,
            "uncertainty_type": 5,
            "sizes": ["Small"],
            "powertrain": ["BEV"],
            "year": 2020,
        }
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("sizes", "Small"),
        ("sizes", []),
        ("powertrain", ["BEV", "BEV"]),
        ("powertrain", [None]),
        ("year", True),
        ("year", 2020.5),
        ("amount", np.nan),
        ("amount", True),
        ("minimum", np.inf),
        ("loc", "10"),
    ],
)
def test_invalid_records_identify_record_and_field(field, value):
    data = records()
    data["mass-2020"][field] = value
    with pytest.raises(ValueError, match=f"mass-2020.*{field}"):
        VehicleInputParameters(data, extra=[])


def test_missing_amount_and_reversed_bounds_are_rejected():
    data = records()
    del data["mass-2020"]["amount"]
    with pytest.raises(ValueError, match="mass-2020.*amount"):
        VehicleInputParameters(data, extra=[])
    data = records()
    data["mass-2020"]["minimum"] = 20
    with pytest.raises(ValueError, match="mass-2020.*minimum"):
        VehicleInputParameters(data, extra=[])


def test_non_record_input_is_rejected():
    with pytest.raises(ValueError, match="dictionary"):
        VehicleInputParameters([], extra=[])
    with pytest.raises(ValueError, match="broken.*dictionary"):
        VehicleInputParameters({"broken": None}, extra=[])


def test_duplicate_audit_is_explicit_and_preserves_legacy_precedence():
    data = records()
    data["duplicate"] = deepcopy(data["mass-2020"])
    data["duplicate"]["amount"] = 12
    before = deepcopy(data)
    ip = VehicleInputParameters(data, extra=[])
    ip.static()
    _, array = fill_xarray_from_input_parameters(ip)
    assert array.item() == 10
    assert data == before
    with pytest.raises(ValueError, match="duplicate cell.*Small.*BEV.*2020"):
        validate_parameters(data, check_duplicates=True)


@pytest.fixture
def fuel_model():
    return SimpleNamespace(
        array=xr.DataArray([0, 0], dims="year", coords={"year": [2020, 2030]}),
        bs=BackgroundSystemModel(),
    )


def blend(share=0.8, secondary=None):
    result = {"diesel": {"primary": {"type": "diesel", "share": share}}}
    if secondary is not None:
        result["diesel"]["secondary"] = {
            "type": "diesel - biodiesel - cooking oil",
            "share": secondary,
        }
    return result


@pytest.mark.parametrize(
    "share", [-0.1, 1.1, np.nan, np.inf, True, "0.8", [], [0.1, 0.2, 0.3], [[0.8, 0.8]]]
)
def test_invalid_shares_fail_with_fuel_context(fuel_model, share):
    with pytest.raises(ValueError, match="diesel.*primary.*share"):
        VehicleModel.check_fuel_blend(fuel_model, blend(share))


def test_fuel_shares_sum_to_one_for_each_year(fuel_model):
    with pytest.raises(ValueError, match="diesel.*sum to one"):
        VehicleModel.check_fuel_blend(fuel_model, blend([0.8, 0.7], [0.2, 0.2]))


@pytest.mark.parametrize("share", [0.8, [0.8], [0.8, 0.7]])
def test_missing_secondary_is_completed_without_mutating_inputs(fuel_model, share):
    source = blend(share)
    before = deepcopy(source)
    result = VehicleModel.check_fuel_blend(fuel_model, source)
    assert source == before
    assert result["diesel"]["primary"]["share"].shape == (2,)
    assert result["diesel"]["secondary"]["share"].shape == (2,)
    np.testing.assert_allclose(
        result["diesel"]["primary"]["share"] + result["diesel"]["secondary"]["share"], 1
    )


def test_scalar_and_year_specific_shares_broadcast(fuel_model):
    result = VehicleModel.check_fuel_blend(fuel_model, blend(0.8, [0.2, 0.2]))
    assert result["diesel"]["secondary"]["share"].shape == (2,)


@pytest.mark.parametrize(
    "source,match",
    [
        ({"unknown": {}}, "category"),
        ({"diesel": {"primary": {"type": "unknown", "share": 1}}}, "unknown fuel"),
        ({"diesel": {"primary": None}}, "primary.*dictionary"),
        ({"diesel": {"primary": {"type": "diesel"}}}, "share"),
        ({"diesel": {}}, "Primary fuel"),
        ([1], "dictionary"),
    ],
)
def test_invalid_fuel_definitions_have_context(fuel_model, source, match):
    with pytest.raises(ValueError, match=match):
        VehicleModel.check_fuel_blend(fuel_model, source)
