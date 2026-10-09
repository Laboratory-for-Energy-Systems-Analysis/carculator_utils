"""Malformed inputs fail at the public boundary with useful context."""

import json
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


@pytest.mark.parametrize("mode", [4.0, 16.0])
@pytest.mark.parametrize("from_file", [False, True])
def test_triangular_mode_outside_bounds_has_vehicle_context(tmp_path, mode, from_file):
    data = records()
    data["mass-2020"]["loc"] = mode
    before = deepcopy(data)
    source = data
    if from_file:
        source = tmp_path / "invalid.json"
        source.write_text(json.dumps(data))
    with pytest.raises(ValueError) as error:
        VehicleInputParameters(source, extra=[])
    message = str(error.value)
    for expected in ["mass-2020", "mass", "2020", "Small", "BEV", "loc", "5.0", "15.0"]:
        assert expected in message
    assert data == before


@pytest.mark.parametrize("missing", ["minimum", "loc", "maximum"])
def test_triangular_distribution_requires_explicit_mode_and_bounds(missing):
    data = records()
    del data["mass-2020"][missing]
    with pytest.raises(ValueError, match=f"mass-2020.*2020.*requires {missing}"):
        VehicleInputParameters(data, extra=[])


def test_degenerate_triangular_distribution_is_rejected():
    data = records()
    data["mass-2020"].update(minimum=10, maximum=10)
    with pytest.raises(ValueError, match="mass-2020.*minimum must be less"):
        VehicleInputParameters(data, extra=[])


@pytest.mark.parametrize("mode", [5.0, 10.0, 15.0])
def test_triangular_boundary_modes_are_valid_and_amount_is_distinct(mode):
    data = records()
    # amount is the static input, while loc is the distribution's mode.
    data["mass-2020"].update(loc=mode, amount=100)
    before = deepcopy(data)
    ip = VehicleInputParameters(data, extra=[])
    ip.static()
    assert ip.values["mass-2020"] == 100
    ip.stochastic(16, seed=42)
    assert np.isfinite(ip.values["mass-2020"]).all()
    assert ((ip.values["mass-2020"] >= 5) & (ip.values["mass-2020"] <= 15)).all()
    assert data == before


@pytest.mark.family
@pytest.mark.parametrize(
    "package,prefix",
    [
        ("carculator", "Car"),
        ("carculator_bus", "Bus"),
        ("carculator_truck", "Truck"),
        ("carculator_two_wheeler", "TwoWheeler"),
    ],
)
def test_complete_packaged_defaults_can_be_sampled(package, prefix):
    module = pytest.importorskip(package)
    inputs = getattr(module, prefix + "InputParameters")()
    # Sample before scope selection, as in the public workflow: invalid future
    # records must not be hidden by restricting the input dictionary to 2025.
    inputs.stochastic(3, seed=42)
    assert inputs.values.keys() == inputs.data.keys()
    for key, values in inputs.values.items():
        assert np.isfinite(values).all(), (package, key)


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


@pytest.mark.parametrize(
    "fuel,fuel_type",
    [
        ("diesel", "hydrogen - electrolysis - PEM"),
        ("diesel", "kerosene"),
        ("petrol", "diesel"),
        ("petrol", "hydrogen - electrolysis - PEM"),
        ("methane", "hydrogen - electrolysis - PEM"),
        ("hydrogen", "methane"),
    ],
)
@pytest.mark.parametrize("role", ["primary", "secondary"])
@pytest.mark.parametrize("share", [0, 0.25])
def test_wrong_category_fuels_fail_even_at_zero_share(
    fuel_model, fuel, fuel_type, role, share
):
    default = fuel_model.bs.default_fuels[fuel]["primary"]
    source = {
        fuel: {
            "primary": {"type": default, "share": 1 - share},
            "secondary": {"type": default, "share": 1 - share},
        }
    }
    source[fuel][role] = {"type": fuel_type, "share": share}
    before = deepcopy(source)

    with pytest.raises(ValueError) as error:
        VehicleModel.check_fuel_blend(fuel_model, source)
    for detail in (repr(fuel), role, repr(fuel_type), "category"):
        assert detail in str(error.value)
    assert source == before


@pytest.mark.parametrize(
    "fuel,fuel_type",
    [
        ("diesel", "diesel"),
        ("diesel", "diesel - biodiesel - cooking oil"),
        ("diesel", "diesel - synthetic - FT - wood - economic allocation"),
        ("petrol", "petrol"),
        ("petrol", "petrol - bioethanol - sugarbeet"),
        (
            "petrol",
            "petrol - synthetic - methanol - cement - economic allocation",
        ),
        ("methane", "methane"),
        ("methane", "methane - biomethane - sewage sludge"),
        ("methane", "methane - synthetic - biological"),
        ("hydrogen", "hydrogen - smr - natural gas"),
        ("hydrogen", "hydrogen - atr - biogas"),
        ("hydrogen", "hydrogen - electrolysis - PEM"),
    ],
)
@pytest.mark.parametrize("role", ["primary", "secondary"])
def test_valid_category_fuels_keep_shares_and_caller_data(
    fuel_model, fuel, fuel_type, role
):
    default = fuel_model.bs.default_fuels[fuel]["primary"]
    source = {
        fuel: {
            "primary": {"type": default, "share": [0.8, 0.2]},
            "secondary": {"type": default, "share": [0.2, 0.8]},
        }
    }
    source[fuel][role]["type"] = fuel_type
    before = deepcopy(source)
    result = VehicleModel.check_fuel_blend(fuel_model, source)

    assert source == before
    assert result[fuel][role]["type"] == fuel_type
    for component in ("primary", "secondary"):
        np.testing.assert_array_equal(
            result[fuel][component]["share"], source[fuel][component]["share"]
        )


@pytest.mark.parametrize("field", ["lhv", "density", "CO2", "biogenic share"])
@pytest.mark.parametrize("role", ["primary", "secondary"])
@pytest.mark.parametrize(
    "value", [None, True, "1", np.nan, np.inf, [], [1, 1, 1], [[1, 1]], [1, np.nan]]
)
def test_invalid_fuel_property_types_and_shapes(fuel_model, field, role, value):
    source = blend(1, 0)
    source["diesel"][role][field] = value
    before = deepcopy(source)
    with pytest.raises(ValueError) as error:
        VehicleModel.check_fuel_blend(fuel_model, source)
    for detail in ("diesel", role, field):
        assert detail in str(error.value)
    np.testing.assert_equal(source, before)


@pytest.mark.parametrize(
    "field,value",
    [
        ("lhv", 0),
        ("lhv", -1),
        ("density", 0),
        ("density", -1),
        ("CO2", -3),
        ("biogenic share", -0.1),
        ("biogenic share", 1.5),
    ],
)
@pytest.mark.parametrize("role", ["primary", "secondary"])
def test_invalid_fuel_property_bounds_even_at_zero_share(
    fuel_model, field, role, value
):
    source = blend(1, 0)
    source["diesel"][role][field] = value
    with pytest.raises(ValueError) as error:
        VehicleModel.check_fuel_blend(fuel_model, source)
    for detail in ("diesel", role, field):
        assert detail in str(error.value)


@pytest.mark.parametrize(
    "field,values",
    [
        ("lhv", [40, 44]),
        ("density", [0.75, 0.85]),
        ("CO2", [0, 3.15]),
        ("biogenic share", [0, 1]),
    ],
)
@pytest.mark.parametrize("role", ["primary", "secondary"])
@pytest.mark.parametrize("shape", ["scalar", "one-element", "per-year"])
def test_fuel_properties_normalize_without_mutation(
    fuel_model, field, values, role, shape
):
    fuel_model.array = fuel_model.array.assign_coords(year=[2030, 2025])
    source = blend(0.8, 0.2)
    value = (
        values[0]
        if shape == "scalar"
        else values[:1] if shape == "one-element" else values
    )
    source["diesel"][role][field] = value
    before = deepcopy(source)
    result = VehicleModel.check_fuel_blend(fuel_model, source)
    assert source == before
    expected = values if shape == "per-year" else [values[0]] * 2
    np.testing.assert_array_equal(
        np.broadcast_to(result["diesel"][role][field], (2,)), expected
    )
    # Carbon arithmetic must work with normalized year sequences as well.
    if field == "biogenic share":
        np.testing.assert_array_equal(
            np.broadcast_to(1 - result["diesel"][role][field], (2,)),
            1 - np.asarray(expected),
        )
