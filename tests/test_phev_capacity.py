"""A PHEV carries one full pack, irrespective of its electric driving share."""

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters


@pytest.fixture(
    params=[("carculator", "Car", "Medium"), ("carculator_truck", "Truck", "40t")]
)
def phev(request):
    name, prefix, size = request.param
    package = pytest.importorskip(name)
    inputs = getattr(package, prefix + "InputParameters")()
    inputs.static()
    powertrains = ["PHEV-d", "PHEV-p"] if prefix == "Car" else ["PHEV-d"]
    _, array = fill_xarray_from_input_parameters(
        inputs, scope={"size": [size], "powertrain": powertrains, "year": [2020, 2030]}
    )
    array = array.sel(year=[2030, 2020]).isel(value=[0, 0])
    array = array.assign_coords(value=["changed", "reference"])
    array.loc[dict(parameter="energy battery mass", value="changed")] *= 1.2
    original = array.copy(deep=True)
    model = getattr(package, prefix + "Model")(
        array,
        drop_hybrids=False,
        **({"cycle": "Regional delivery"} if prefix == "Truck" else {}),
    )
    model.set_all()
    xr.testing.assert_identical(array, original)
    return model, powertrains


@pytest.mark.parametrize("share", [0, 0.5, 1])
def test_pack_capacity_and_usable_range_do_not_depend_on_driving_share(phev, share):
    model, powertrains = phev
    # Vary usage after sizing: changing usage cannot remove installed hardware.
    model.array.loc[dict(powertrain="PHEV-e", parameter="electric utility factor")] = (
        share
    )
    # The combustion-mode intermediate can have a different battery design.
    for pt in powertrains:
        model.array.loc[
            dict(
                powertrain=pt.replace("PHEV-", "PHEV-c-"),
                parameter="battery cell mass share",
            )
        ] = 0.4
    model.create_PHEV()
    electric = model.array.sel(powertrain="PHEV-e", drop=True)
    for pt in powertrains:
        combined = model.array.sel(powertrain=pt, drop=True)
        combustion = model.array.sel(
            powertrain=pt.replace("PHEV-", "PHEV-c-"), drop=True
        )
        get = lambda a, p: a.sel(parameter=p, drop=True)
        capacity = get(combined, "electric energy stored")
        np.testing.assert_allclose(capacity, get(electric, "electric energy stored"))
        # Unit prices/markup retain their mode-specific input convention, but
        # both modes must price the same physical installed capacity.
        expected_battery_cost = capacity * (
            share
            * get(electric, "energy battery cost per kWh")
            * get(electric, "markup factor")
            + (1 - share)
            * get(combustion, "energy battery cost per kWh")
            * get(combustion, "markup factor")
        )
        np.testing.assert_allclose(
            get(combined, "energy battery cost"), expected_battery_cost, rtol=2e-6
        )
        np.testing.assert_allclose(
            capacity,
            get(combined, "battery cell mass")
            * get(combined, "battery cell energy density"),
            rtol=2e-6,
        )
        np.testing.assert_allclose(
            get(combined, "battery cell mass"),
            get(combined, "energy battery mass")
            * get(combined, "battery cell mass share"),
            rtol=2e-6,
        )
        np.testing.assert_allclose(
            get(combined, "energy battery mass"),
            get(combined, "battery cell mass") + get(combined, "battery BoP mass"),
            rtol=2e-6,
        )
        for parameter in ("TtW energy", "electricity consumption", "fuel consumption"):
            np.testing.assert_allclose(
                get(combined, parameter),
                share * get(electric, parameter)
                + (1 - share) * get(combustion, parameter),
                rtol=2e-6,
            )
        # Full-tank plus usable-battery range; neither term is usage-weighted.
        expected_range = get(combustion, "oxidation energy stored") * 3600 / get(
            combustion, "TtW energy"
        ) + capacity * get(electric, "battery DoD") * 3600 / get(electric, "TtW energy")
        np.testing.assert_allclose(
            get(combined, "range" if model.vehicle_type == "car" else "target range"),
            expected_range,
            rtol=2e-6,
        )
