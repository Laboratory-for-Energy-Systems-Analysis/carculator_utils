from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from carculator_utils.model import VehicleModel
from carculator_utils.vehicle_input_parameters import (
    VehicleInputParameters,
    load_parameters,
)


def minimal_vehicle_array():
    return xr.DataArray(
        np.zeros((1, 1, 1, 1, 1)),
        coords={
            "size": ["Small"],
            "powertrain": ["BEV"],
            "parameter": ["battery cell energy density"],
            "year": [2020],
            "value": [0],
        },
        dims=("size", "powertrain", "parameter", "year", "value"),
    )


def test_vehicle_model_accepts_missing_energy_storage():
    model = VehicleModel(minimal_vehicle_array())

    assert model.energy_storage == {}


def test_vehicle_model_rejects_arrays_missing_required_dimensions():
    array = minimal_vehicle_array().squeeze("value", drop=True)

    with pytest.raises(ValueError, match="missing required dimensions"):
        VehicleModel(array)


def test_base_vehicle_input_parameters_requires_explicit_defaults():
    with pytest.raises(FileNotFoundError, match="Pass `parameters` explicitly"):
        VehicleInputParameters()


def test_load_parameters_raises_file_not_found_error():
    with pytest.raises(FileNotFoundError):
        load_parameters(Path("does-not-exist.json"))


@pytest.mark.parametrize("method", ["override_range", "override_battery_capacity"])
def test_battery_sizing_updates_only_selected_battery_cells(method):
    parameters = [
        "TtW energy",
        "battery DoD",
        "battery cell energy density",
        "battery cell mass share",
        "energy battery mass",
        "battery cell mass",
        "battery BoP mass",
        "electric energy stored",
        "range",
    ]
    array = minimal_vehicle_array().reindex(
        parameter=parameters,
        powertrain=["BEV", "FCEV"],
        year=[2020, 2025],
        value=[0, 1],
        fill_value=1.0,
    )
    model = VehicleModel(
        array,
        energy_storage={"capacity": {("BEV", "Small", 2025): 100}},
        target_range={
            ("BEV", "Small", 2025): 400,
            ("BEV", "Small", 2020): None,
        },
    )
    model["TtW energy"] = xr.DataArray(
        [720, 900], dims="value", coords={"value": [0, 1]}
    )
    model["battery DoD"] = 0.8
    model["battery cell energy density"] = 0.25
    model["battery cell mass share"] = 0.8
    before = model.array.copy(deep=True)
    getattr(model, method)()
    selected = model.array.sel(powertrain="BEV", size="Small", year=2025)
    # 400 km at 0.2/0.25 kWh/km uses 80/100 kWh; 80% usable gives
    # 100/125 kWh nominal, 400/500 kg cells and 500/625 kg packs.
    expected_values = {
        "electric energy stored": [100, 125],
        "battery cell mass": [400, 500],
        "energy battery mass": [500, 625],
        "battery BoP mass": [100, 125],
        "range": [400, 400],
    }
    if method == "override_battery_capacity":
        # Capacity is fixed at 100 kWh for both samples. Range is calculated
        # later in the completed pipeline, after energy demand is available.
        expected_values = {
            "electric energy stored": [100, 100],
            "battery cell mass": [400, 400],
            "energy battery mass": [500, 500],
            "battery BoP mass": [100, 100],
            "range": [1, 1],
        }
    for parameter, expected in expected_values.items():
        np.testing.assert_allclose(selected.sel(parameter=parameter), expected)
    xr.testing.assert_identical(
        model.array.sel(powertrain="FCEV"), before.sel(powertrain="FCEV")
    )
    xr.testing.assert_identical(model.array.sel(year=2020), before.sel(year=2020))
