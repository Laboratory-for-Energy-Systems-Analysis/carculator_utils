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
