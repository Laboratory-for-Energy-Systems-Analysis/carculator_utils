"""Cost projections must preserve each year and uncertainty-sample identity."""

import math

import numpy as np
import pytest
import xarray as xr

from carculator_utils.model import VehicleModel

ENERGY = "energy battery cost per kWh"
POWER = "power battery cost per kW"
TANK = "fuel tank cost per kg"
STACK = "fuel cell cost per kW"
GAS = "combustion powertrain cost per kW"
PARAMETERS = [ENERGY, POWER, TANK, STACK, GAS, "unrelated cost"]
CURVES = {
    ENERGY: (2.75e86, -0.0961, 50.59),
    POWER: (8.337e40, -0.0449, 11.17),
    TANK: (1.078e58, -0.0632, 343),
    STACK: (3.15e66, -0.0735, 23.9),
    GAS: (5.92e160, -0.1819, 26.76),
}


@pytest.fixture(
    params=[
        "shared",
        pytest.param("carculator", marks=pytest.mark.family),
        pytest.param("carculator_bus", marks=pytest.mark.family),
        pytest.param("carculator_two_wheeler", marks=pytest.mark.family),
    ]
)
def projection(request):
    name = request.param
    if name == "shared":
        # The legacy base FCEV hook has a separate parameter-target defect.
        # Vehicle subclasses use their own correctly targeted FCEV equations.
        return (
            VehicleModel,
            {"BEV": [ENERGY], "HEV-p": [POWER], "ICEV-g": [POWER, GAS]},
            False,
        )
    module = pytest.importorskip(name)
    if name == "carculator":
        return (
            module.CarModel,
            {
                "BEV": [ENERGY],
                "PHEV-e": [ENERGY],
                "PHEV-c-p": [ENERGY, POWER],
                "HEV-p": [POWER],
                "FCEV": [TANK, STACK, POWER],
                "ICEV-g": [POWER, GAS],
            },
            False,
        )
    if name == "carculator_bus":
        return (
            module.BusModel,
            {
                "BEV-depot": [ENERGY],
                "BEV-opp": [ENERGY],
                "BEV-motion": [ENERGY],
                "HEV-d": [POWER],
                "FCEV": [TANK, STACK, POWER],
                "ICEV-g": [POWER, GAS],
            },
            True,
        )
    return (
        module.TwoWheelerModel,
        {"BEV": [ENERGY], "ICEV-p": [POWER], "Human": []},
        False,
    )


@pytest.mark.parametrize("years", [[2020, 2025, 2030], [2030, 2020, 2025], [2025]])
@pytest.mark.parametrize(
    "samples", [["a"], ["b", "reference", "a"], ["d", "b", "a", "c"]]
)
def test_each_projection_keeps_year_sample_and_vehicle_labels(
    projection, years, samples, monkeypatch
):
    Model, affected, bus = projection
    model = Model.__new__(Model)
    coords = dict(
        size=["first", "second"],
        powertrain=list(affected),
        parameter=PARAMETERS,
        year=years,
        value=samples,
    )
    model.array = xr.DataArray(
        np.full(tuple(len(v) for v in coords.values()), 17, dtype=np.float32),
        dims=list(coords),
        coords=coords,
    )
    # Distinct known draws reveal mixing even when there are more samples than
    # years; the factor belongs to a sample and must apply to every year.
    draws = dict(a=0.8, b=1.0, c=1.2, d=0.9)
    fcev_draws = dict(a=3.5, b=5.5, c=4.0, d=5.0)
    calls = []

    def triangular(left, mode, right, shape):
        calls.append((left, mode, right, shape))
        table = fcev_draws if mode == 5 else draws
        return np.array([table[s] for s in samples]).reshape(len(samples), 1)

    monkeypatch.setattr(np.random, "triangular", triangular)
    model.adjust_cost()
    deterministic = len(samples) == 1 or "reference" in samples
    assert len(calls) == (0 if deterministic else (2 if bus else 1))
    expected = xr.full_like(model.array, 17)
    for pwt, parameters in affected.items():
        for parameter in parameters:
            a, b, c = CURVES[parameter]
            for year in years:
                for sample in samples:
                    if bus and parameter in (TANK, STACK):
                        factor = 5 if deterministic else fcev_draws[sample]
                    else:
                        factor = 1 if deterministic else draws[sample]
                    price = (a * math.exp(b * year) + c) * factor
                    if parameter == GAS and not bus:
                        price = min(price, 100)
                    expected.loc[
                        dict(
                            powertrain=pwt, parameter=parameter, year=year, value=sample
                        )
                    ] = price
    xr.testing.assert_allclose(model.array, expected)


@pytest.mark.parametrize("parameter", [ENERGY, POWER])
def test_shared_projection_is_independent_of_sample_axis_order(parameter):
    model = VehicleModel.__new__(VehicleModel)
    coords = dict(
        size=["Medium"],
        powertrain=["BEV", "HEV-p"],
        parameter=[ENERGY, POWER],
        year=[2030, 2020, 2025],
        value=["other", "reference"],
    )
    model.array = xr.DataArray(
        np.zeros(tuple(len(v) for v in coords.values())),
        dims=list(coords),
        coords=coords,
    ).transpose("value", "year", "parameter", "powertrain", "size")
    model.adjust_cost()
    pwt = "BEV" if parameter == ENERGY else "HEV-p"
    a, b, c = CURVES[parameter]
    for year in coords["year"]:
        np.testing.assert_allclose(
            model[parameter].sel(powertrain=pwt, year=year),
            a * math.exp(b * year) + c,
        )


def test_shared_fcev_years_match_separate_runs():
    # Test year alignment independently of the legacy base hook's parameter
    # mapping; correcting that separate mapping must not invalidate this check.
    coords = dict(
        size=["Medium"],
        powertrain=["FCEV"],
        parameter=PARAMETERS,
        year=[2020, 2025, 2030],
        value=["reference", "other"],
    )
    array = xr.DataArray(
        np.zeros(tuple(len(v) for v in coords.values())),
        dims=list(coords),
        coords=coords,
    )
    combined = VehicleModel.__new__(VehicleModel)
    combined.array = array.copy(deep=True)
    combined.adjust_cost()
    for year in array.year.values:
        separate = VehicleModel.__new__(VehicleModel)
        separate.array = array.sel(year=[year]).copy(deep=True)
        separate.adjust_cost()
        xr.testing.assert_identical(combined.array.sel(year=[year]), separate.array)
