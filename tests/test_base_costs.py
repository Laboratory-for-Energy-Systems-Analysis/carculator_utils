"""The public base cost method must repay capital on an annual time basis."""

import numpy as np
import pytest
import xarray as xr
import yaml

from carculator_utils.model import VehicleModel


@pytest.fixture
def model():
    m = VehicleModel.__new__(VehicleModel)
    with (m.DATA_DIR / "purchase_cost_params.yaml").open() as stream:
        groups = yaml.safe_load(stream)
    parameters = set(groups["purchase"] + groups["markup"])
    parameters.update(
        "glider base mass;glider cost slope;glider cost intercept;lightweighting;"
        "glider lightweighting cost per kg;electric powertrain cost per kW;"
        "electric power;combustion power;combustion powertrain cost per kW;"
        "fuel cell power;fuel cell cost per kW;battery power;power battery cost per kW;"
        "energy battery cost per kWh;electric energy stored;fuel tank cost per kg;"
        "fuel mass;energy cost;energy cost per kWh;TtW energy;battery charge efficiency;"
        "battery lifetime replacements;fuel cell lifetime replacements;markup factor;"
        "lifetime;lifetime kilometers;kilometers per year;purchase cost;interest rate;"
        "amortised purchase cost;maintenance cost;maintenance cost per glider cost;"
        "amortised component replacement cost;total cost per km".split(";")
    )
    coords = dict(
        size=["Small"],
        powertrain=["ICEV-p"],
        parameter=sorted(parameters),
        year=[2030, 2025],
        value=["specified", "computed"],
    )
    m.array = xr.DataArray(
        np.zeros(tuple(map(len, coords.values()))), dims=list(coords), coords=coords
    )
    for key, amount in {
        "glider base mass": 1000,
        "glider cost slope": 10,
        "energy battery cost per kWh": 100,
        "electric energy stored": 20,
        "battery lifetime replacements": 0.5,
        "markup factor": 1,
        "kilometers per year": 10000,
        "lifetime kilometers": 100000,
        "battery charge efficiency": 1,
    }.items():
        m[key] = amount
    m.array.loc[dict(parameter="purchase cost", value="specified")] = 15000
    m.array.loc[dict(parameter="lifetime kilometers", year=2030)] = 50000
    return m


@pytest.mark.parametrize("rate", [0, 1e-15, 0.05, -0.01])
def test_base_annuity_and_midlife_replacement_match_cash_flows(model, rate):
    model["interest rate"] = rate
    model.set_costs()
    for year, years in [(2030, 5), (2025, 10)]:
        annuity = 1 / sum((1 + rate) ** -k for k in range(1, years + 1))
        for sample, purchase in [("specified", 15000), ("computed", 12000)]:
            cell = model.array.sel(year=year, value=sample)
            assert cell.sel(parameter="purchase cost").item() == purchase
            assert cell.sel(
                parameter="amortised purchase cost"
            ).item() == pytest.approx(purchase * annuity / 10000)
            assert cell.sel(
                parameter="amortised component replacement cost"
            ).item() == pytest.approx(
                1000 / (1 + rate) ** (years / 2) * annuity / 10000
            )


def test_base_inactive_lifetimes_have_finite_zero_capital_costs(model):
    model["kilometers per year"] = 0
    model["lifetime kilometers"] = 0
    model.set_costs()
    for name in [
        "amortised purchase cost",
        "amortised component replacement cost",
        "maintenance cost",
    ]:
        np.testing.assert_array_equal(model[name], 0)
