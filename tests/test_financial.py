"""Independent present-value oracles for annualized costs."""

import numpy as np
import pytest
import xarray as xr
from hypothesis import given, settings
from hypothesis import strategies as st

from carculator_utils.numerical import capital_recovery_factor


@settings(max_examples=50, derandomize=True, deadline=None, database=None)
@given(rate=st.floats(min_value=-0.05, max_value=0.25), years=st.integers(1, 100))
def test_annual_payments_repay_one_unit_of_capital(rate, years):
    present_value = sum((1 + rate) ** (-year) for year in range(1, years + 1))
    assert float(capital_recovery_factor(rate, years)) * present_value == pytest.approx(
        1, rel=1e-12
    )


@pytest.mark.parametrize("rate", [0.0, 1e-15, -1e-15, 0.05])
def test_zero_and_near_zero_interest_are_stable(rate):
    with np.errstate(all="raise"):
        result = capital_recovery_factor(rate, 10)
    expected = 1 / sum((1 + rate) ** (-year) for year in range(1, 11))
    assert float(result) == pytest.approx(expected, rel=1e-12)


def test_rates_and_lifetimes_broadcast_without_losing_labels():
    rates = xr.DataArray([0.0, 0.05], dims="value", coords={"value": ["a", "b"]})
    years = xr.DataArray([5.0, 10.0], dims="year", coords={"year": [2020, 2030]})
    result = capital_recovery_factor(rates, years)
    assert set(result.dims) == {"value", "year"}
    for sample, rate in [("a", 0), ("b", 0.05)]:
        for year, duration in [(2020, 5), (2030, 10)]:
            expected = 1 / sum((1 + rate) ** (-k) for k in range(1, duration + 1))
            assert result.sel(value=sample, year=year).item() == pytest.approx(expected)


@pytest.mark.parametrize(
    "rate, years",
    [
        (-1, 10),
        (-2, 10),
        (np.nan, 10),
        (np.inf, 10),
        (0.05, 0),
        (0.05, -1),
        (0.05, np.nan),
        (0.05, np.inf),
    ],
)
def test_invalid_financial_inputs_raise(rate, years):
    with pytest.raises(ValueError, match="rate|years"):
        capital_recovery_factor(rate, years)
