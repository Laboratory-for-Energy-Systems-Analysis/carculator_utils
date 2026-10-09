"""Missing declared inputs must not quietly become physical zeros."""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.input_completeness import (
    DERIVED,
    MISSING,
    PROVIDED,
    STATUS,
    mark_inputs_provided,
    validate_input_completeness,
)

CASES = [
    ("carculator", "Car", "Medium", "ICEV-p", {}),
    ("carculator_truck", "Truck", "40t", "ICEV-d", {"cycle": "Long haul"}),
    ("carculator_bus", "Bus", "13m-city", "ICEV-d", {}),
    ("carculator_two_wheeler", "TwoWheeler", "Scooter <4kW", "ICEV-p", {}),
]


@pytest.mark.family
@pytest.mark.parametrize("package,prefix,size,powertrain,options", CASES)
def test_missing_record_fails_before_sizing_and_can_be_repaired(
    package, prefix, size, powertrain, options
):
    module = pytest.importorskip(package)
    Inputs = getattr(module, prefix + "InputParameters")
    records = json.loads(Inputs.DEFAULT.read_text())
    records = {
        key: record
        for key, record in records.items()
        if not (record["name"] == "glider base mass" and record["year"] == 2025)
    }
    inputs = Inputs(parameters=records)
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs, scope={"size": [size], "powertrain": [powertrain], "year": [2025]}
    )
    assert array.coords[STATUS].sel(parameter="glider base mass").item() == MISSING
    assert array.coords[STATUS].sel(parameter="TtW energy").item() == DERIVED
    model = getattr(module, prefix + "Model")(array, **options)
    with pytest.raises(ValueError) as error:
        model.set_all()
    for label in [size, powertrain, "2025", "glider base mass", "Missing required"]:
        assert label in str(error.value)
    # A nonzero explicitly supplied input is accepted without altering coverage
    # on the caller's original array.
    model["glider base mass"] = (
        500 if prefix == "Car" else 2000 if prefix in ("Truck", "Bus") else 75
    )
    model.set_all()
    assert np.isfinite(model["TtW energy"]).all()
    assert array.sel(parameter="glider base mass").item() == 0


@pytest.mark.family
def test_missing_bracketing_inputs_are_detected_after_interpolation():
    module = pytest.importorskip("carculator")
    Inputs = module.CarInputParameters
    records = json.loads(Inputs.DEFAULT.read_text())
    records = {
        k: r
        for k, r in records.items()
        if not (r["name"] == "glider base mass" and r["year"] == 2020)
    }
    inputs = Inputs(parameters=records)
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={"size": ["Medium"], "powertrain": ["ICEV-p"], "year": [2020, 2030]},
    )
    array = array.interp(year=[2025])
    with pytest.raises(ValueError, match="Missing required.*glider base mass"):
        module.CarModel(array).set_all()


@pytest.mark.family
def test_explicit_zero_and_unavailable_cells_have_distinct_meanings():
    module = pytest.importorskip("carculator_two_wheeler")
    Inputs = module.TwoWheelerInputParameters
    records = json.loads(Inputs.DEFAULT.read_text())
    records = {
        k: r
        for k, r in records.items()
        if r["name"] != "maintenance cost per glider cost"
    }
    inputs = Inputs(parameters=records)
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={
            "size": ["Bicycle <25"],
            "powertrain": ["Human", "ICEV-p"],
            "year": [2025],
        },
    )
    context = SimpleNamespace(array=array, vehicle_type="two-wheeler")
    with pytest.raises(ValueError, match="maintenance cost per glider cost"):
        validate_input_completeness(context)
    repaired = mark_inputs_provided(
        array, "maintenance cost per glider cost", powertrain="Human"
    )
    assert (
        repaired.coords[STATUS]
        .sel(parameter="maintenance cost per glider cost", powertrain="Human")
        .item()
        == PROVIDED
    )
    assert (
        array.coords[STATUS]
        .sel(parameter="maintenance cost per glider cost", powertrain="Human")
        .item()
        == MISSING
    )
    # The unavailable ICE bicycle does not require those missing records.
    validate_input_completeness(
        SimpleNamespace(array=repaired, vehicle_type="two-wheeler")
    )
