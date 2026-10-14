"""Independent net-power and complete-pack balances for FCEV buffers."""

import numpy as np
import pytest
import xarray as xr

from carculator_utils.energy_consumption import EnergyConsumptionModel
from carculator_utils.model import VehicleModel


def make_model():
    parameters = [
        "power",
        "engine efficiency",
        "electric motor efficiency",
        "auxiliary power demand",
        "fuel cell power",
        "fuel cell power share",
        "fuel cell own consumption",
        "fuel cell stack efficiency",
        "fuel cell system efficiency",
        "fuel cell power density",
        "fuel cell power area density",
        "fuel cell stack mass",
        "fuel cell ancillary BoP mass",
        "fuel cell ancillary BoP mass per power",
        "fuel cell essential BoP mass",
        "fuel cell essential BoP mass per power",
        "battery power",
        "battery cell power density",
        "battery cell mass",
        "battery BoP mass",
        "energy battery mass",
        "battery cell mass share",
        "electric energy stored",
        "battery cell energy density",
        "combustion power",
        "combustion power share",
    ]
    array = xr.DataArray(
        np.zeros((1, 3, len(parameters), 2, 2)),
        dims=("size", "powertrain", "parameter", "year", "value"),
        coords={
            "size": ["Medium"],
            "powertrain": ["FCEV", "ICEV-d", "BEV"],
            "parameter": parameters,
            "year": [2050, 2020],
            "value": ["high", "low"],
        },
    )
    model = VehicleModel(array)
    model["power"] = 180
    model["electric motor efficiency"] = 0.9
    model["auxiliary power demand"] = 4000
    model["fuel cell power share"] = xr.where(model.array.powertrain == "FCEV", 0.75, 0)
    model["fuel cell own consumption"] = xr.DataArray(
        [1.3, 1.1], dims="value", coords={"value": ["high", "low"]}
    )
    model["battery cell power density"] = 2
    model["battery cell energy density"] = 0.24
    model["battery cell mass share"] = 0.5
    model["combustion power"] = xr.where(model.array.powertrain == "ICEV-d", 100, 0)
    model["combustion power share"] = xr.where(model.array.powertrain == "ICEV-d", 1, 0)
    return model


def test_fuel_cell_buffer_closes_electrical_power_and_pack_mass_for_labelled_samples():
    model = make_model()
    model.set_fuel_cell_power()
    model.set_fuel_cell_mass()
    fcev = model.array.sel(powertrain="FCEV")
    # 180 kW shaft / 90% motor conversion + 4 kW auxiliaries = 204 kW DC.
    # A 75/25 split gives 153 kW net stack and 51 kW battery output.
    np.testing.assert_allclose(
        fcev.sel(parameter="fuel cell power"), [[[198.9, 168.3]] * 2]
    )
    for name, expected in {
        "battery power": 51,
        "battery cell mass": 25.5,
        "battery BoP mass": 25.5,
        "energy battery mass": 51,
        "electric energy stored": 6.12,
    }.items():
        np.testing.assert_allclose(fcev.sel(parameter=name), expected)
    before = fcev.copy(deep=True)
    model.set_power_battery_properties()
    xr.testing.assert_identical(model.array.sel(powertrain="FCEV"), before)
    np.testing.assert_allclose(model["battery power"].sel(powertrain="ICEV-d"), 3)
    np.testing.assert_allclose(model["battery cell mass"].sel(powertrain="ICEV-d"), 1.5)
    np.testing.assert_allclose(model["battery power"].sel(powertrain="BEV"), 0)


def test_motor_efficiency_override_keeps_sample_and_year_labels():
    model = make_model()
    model.engine_efficiency = {("FCEV", "Medium", 2050): [0.8, 0.75]}
    before = model.array.copy(deep=True)
    demand = model.get_fuel_cell_electrical_power()
    np.testing.assert_allclose(demand.sel(powertrain="FCEV", year=2050), [[229, 244]])
    np.testing.assert_allclose(demand.sel(powertrain="FCEV", year=2020), 204)
    np.testing.assert_allclose(demand.sel(powertrain=["BEV", "ICEV-d"]), 180)
    xr.testing.assert_identical(model.array, before)


@pytest.mark.parametrize("efficiency", [-0.1, 1.1, float("nan")])
def test_invalid_active_motor_efficiency_is_not_hidden(efficiency):
    model = make_model()
    model["electric motor efficiency"] = efficiency
    with pytest.raises(ValueError, match="motor efficiency"):
        model.get_fuel_cell_electrical_power()


def test_zero_power_fcev_does_not_acquire_an_auxiliary_only_pack():
    model = make_model()
    model["power"] = 0
    np.testing.assert_allclose(model.get_fuel_cell_electrical_power(), 0)


def test_legacy_array_uses_full_load_motor_map_instead_of_unity():
    model = make_model()
    model["electric motor efficiency"] = 0
    model.ecm = EnergyConsumptionModel(
        vehicle_type="car",
        vehicle_size=["Medium"],
        powertrains=list(model.array.powertrain.values),
        cycle="WLTC",
        gradient=None,
    )
    # At rated shaft load the legacy curve's 0.85 reference transmission
    # selects its 0.85 ordinate, giving 0.812374906957686 motor efficiency.
    np.testing.assert_allclose(
        model.get_fuel_cell_electrical_power().sel(powertrain="FCEV"),
        180 / 0.812374906957686 + 4,
    )
