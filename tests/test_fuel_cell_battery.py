"""Independent net-power and complete-pack balances for FCEV buffers."""

import numpy as np
import xarray as xr

from carculator_utils.model import VehicleModel


def test_fuel_cell_buffer_closes_net_power_and_pack_mass_for_labelled_samples():
    parameters = [
        "power",
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
    model["power"] = 200
    model["fuel cell power share"] = xr.where(model.array.powertrain == "FCEV", 0.75, 0)
    model["fuel cell own consumption"] = xr.DataArray(
        [1.3, 1.1], dims="value", coords={"value": ["high", "low"]}
    )
    model["battery cell power density"] = 2
    model["battery cell energy density"] = 0.24
    model["battery cell mass share"] = 0.5
    model["combustion power"] = xr.where(model.array.powertrain == "ICEV-d", 100, 0)
    model["combustion power share"] = xr.where(model.array.powertrain == "ICEV-d", 1, 0)
    model.set_fuel_cell_power()
    model.set_fuel_cell_mass()
    fcev = model.array.sel(powertrain="FCEV")
    # 150 kW net from the stack and 50 kW from the buffer supply 200 kW.
    np.testing.assert_allclose(
        fcev.sel(parameter="fuel cell power"), [[[195, 165]] * 2]
    )
    for name, expected in {
        "battery power": 50,
        "battery cell mass": 25,
        "battery BoP mass": 25,
        "energy battery mass": 50,
        "electric energy stored": 6,
    }.items():
        np.testing.assert_allclose(fcev.sel(parameter=name), expected)
    before = fcev.copy(deep=True)
    model.set_power_battery_properties()
    xr.testing.assert_identical(model.array.sel(powertrain="FCEV"), before)
    np.testing.assert_allclose(model["battery power"].sel(powertrain="ICEV-d"), 3)
    np.testing.assert_allclose(model["battery cell mass"].sel(powertrain="ICEV-d"), 1.5)
    np.testing.assert_allclose(model["battery power"].sel(powertrain="BEV"), 0)
