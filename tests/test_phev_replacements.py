"""Car PHEV battery distance/calendar life belongs to one physical pack."""

import numpy as np
import pytest
import xarray as xr


@pytest.mark.parametrize("share", [0, 0.5, 1])
def test_car_phev_distance_and_calendar_life_are_not_usage_weighted(share):
    car = pytest.importorskip("carculator")
    inputs = car.CarInputParameters()
    inputs.static()
    _, array = car.fill_xarray_from_input_parameters(
        inputs,
        scope={"size": ["Medium"], "powertrain": ["PHEV-p", "PHEV-d"], "year": [2020]},
    )
    assert (
        array.sel(powertrain="PHEV-e", parameter="battery lifetime kilometers").item()
        == 200000
    )
    array = array.isel(value=[0, 0]).assign_coords(value=["distance", "calendar"])
    for sample, lifetime, annual in [
        ("distance", 300000, 20000),
        ("calendar", 72000, 2000),
    ]:
        array.loc[dict(parameter="lifetime kilometers", value=sample)] = lifetime
        array.loc[dict(parameter="kilometers per year", value=sample)] = annual
    original = array.copy(deep=True)
    model = car.CarModel(
        array, drop_hybrids=False, electric_utility_factor={2020: share}
    )
    model.set_all()
    # 300000/200000 - 1 = 0.5; 72000/2000/18 - 1 = 1.
    np.testing.assert_allclose(
        model["battery lifetime replacements"].sel(value="distance"), 0.5
    )
    np.testing.assert_allclose(
        model["battery lifetime replacements"].sel(value="calendar"), 1
    )
    for pt in ("PHEV-d", "PHEV-p"):
        np.testing.assert_allclose(
            model["component replacement cost"].sel(powertrain=pt),
            model["energy battery cost"].sel(powertrain=pt)
            * model["battery lifetime replacements"].sel(powertrain=pt),
            rtol=2e-6,
        )
    xr.testing.assert_identical(array, original)
