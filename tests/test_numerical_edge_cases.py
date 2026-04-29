import numpy as np
import pytest
import xarray as xr

from carculator_utils.energy_consumption import EnergyConsumptionModel
from carculator_utils.noise_emissions import NoiseEmissionsModel
from carculator_utils.particulates_emissions import ParticulatesEmissionsModel


def velocity_array(value):
    return xr.DataArray(
        np.full((1, 1, 1, 1, 1), value, dtype=float),
        dims=("second", "value", "year", "powertrain", "size"),
        coords={
            "second": [0],
            "value": [0],
            "year": [2020],
            "powertrain": ["BEV"],
            "size": ["Small"],
        },
    )


def test_energy_model_accepts_all_zero_custom_cycle():
    model = EnergyConsumptionModel(
        vehicle_type="car",
        vehicle_size=["Small"],
        powertrains=["BEV"],
        cycle=np.zeros(5),
        gradient=None,
    )

    assert np.all(model.driving_time == 0)


def test_energy_model_rejects_mismatched_cycle_and_gradient_lengths():
    with pytest.raises(ValueError, match="driving_cycles and the gradient"):
        EnergyConsumptionModel(
            vehicle_type="car",
            vehicle_size=["Small"],
            powertrains=["BEV"],
            cycle=np.zeros(5),
            gradient=np.zeros(4),
        )


def test_noise_model_sums_sources_in_power_space():
    model = NoiseEmissionsModel.__new__(NoiseEmissionsModel)
    model.velocity = velocity_array(36.0)

    source_shape = (1, 1, 1, 1, 1, 8)
    model.rolling_noise = lambda: np.full(source_shape, 60.0)
    model.propulsion_noise = lambda: np.full(source_shape, 60.0)

    result = model.get_sound_power_per_compartment()

    # One second at 36 km/h is 0.01 km; two 60 dB sources are 2e-6 W.
    np.testing.assert_allclose(result[0, 0, :8, 0, 0], 2e-4)
    np.testing.assert_allclose(result[0, 0, 8:, 0, 0], 0)


def test_noise_model_returns_zero_for_zero_distance():
    model = NoiseEmissionsModel.__new__(NoiseEmissionsModel)
    model.velocity = velocity_array(0.0)

    source_shape = (1, 1, 1, 1, 1, 8)
    model.rolling_noise = lambda: np.full(source_shape, 60.0)
    model.propulsion_noise = lambda: np.full(source_shape, 60.0)

    result = model.get_sound_power_per_compartment()

    assert np.all(np.isfinite(result))
    assert np.all(result == 0)


def test_particulates_model_avoids_nan_for_zero_distance():
    mass = xr.DataArray(
        np.full((1, 1, 1, 1), 1000.0),
        dims=("value", "year", "powertrain", "size"),
        coords={
            "value": [0],
            "year": [2020],
            "powertrain": ["BEV"],
            "size": ["Small"],
        },
    )
    model = ParticulatesEmissionsModel(velocity_array(0.0), mass)

    result = model.get_abrasion_emissions()

    assert np.all(np.isfinite(result))
