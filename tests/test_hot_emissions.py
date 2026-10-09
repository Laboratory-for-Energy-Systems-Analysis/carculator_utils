"""Pollutant identity, mass conservation and lifetime-average deterioration."""

import importlib.util
import os
import runpy
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from carculator_utils import hot_emissions
from carculator_utils.inventory import get_exhaust_emission_flows


def test_deterioration_uses_each_year_size_and_sample(monkeypatch):
    endpoints = xr.DataArray(
        [[[3.0], [5.0]]],
        dims=("powertrain", "euro_class", "component"),
        coords={
            "powertrain": ["ICEV-p"],
            "euro_class": [6, 7],
            "component": ["Nitrogen oxides"],
        },
    )
    monkeypatch.setattr(hot_emissions, "get_emission_factors", lambda **kw: endpoints)
    lifetime = (
        xr.DataArray(
            [0.0, 200000.0, 400000.0], dims="value", coords={"value": [0, 1, 2]}
        )
        .expand_dims(size=["Small", "Large"], powertrain=["ICEV-p"], year=[2020, 2030])
        .copy()
    )
    lifetime.loc[dict(size="Large")] *= 2
    actual = hot_emissions.get_mileage_degradation_factor(
        lifetime, [6, 7], ["ICEV-p"], "car"
    )
    # Mean of a linear trajectory from 1 to the mileage-adjusted endpoint.
    np.testing.assert_allclose(
        actual.sel(size="Small", year=2020).values.ravel(), [1, 2, 3]
    )
    np.testing.assert_allclose(
        actual.sel(size="Small", year=2030).values.ravel(), [1, 3, 5]
    )
    np.testing.assert_allclose(
        actual.sel(size="Large", year=2030).values.ravel(), [1, 5, 9]
    )


def test_ethane_and_ethene_are_retained_without_chemical_misidentification():
    mapping = get_exhaust_emission_flows()
    for environment, compartment in (
        ("urban", "urban air close to ground"),
        ("suburban", "non-urban air or from high stacks"),
        ("rural", "low population density, long-term"),
    ):
        assert (
            mapping[("Ethane", ("air", compartment), "kilogram")]
            == f"Ethane direct emissions, {environment}"
        )
        assert (
            mapping[("Ethylene", ("air", compartment), "kilogram")]
            == f"Ethene direct emissions, {environment}"
        )
        assert (
            mapping[
                (
                    "NMVOC, non-methane volatile organic compounds",
                    ("air", compartment),
                    "kilogram",
                )
            ]
        ) == f"Non-methane hydrocarbon direct emissions, {environment}"


@pytest.mark.family
def test_completed_family_pollutant_audit(tmp_path):
    # Load the audit without adding the checkout to sys.path: artifact tests
    # must keep importing the installed wheel, not source-tree packages.
    namespace = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts" / "audit_hot_emission_inventory.py")
    )
    CASES, audit = namespace["CASES"], namespace["audit"]

    missing = [name for name, *_ in CASES if importlib.util.find_spec(name) is None]
    if missing:
        if os.environ.get("CARCULATOR_REQUIRE_FAMILY") == "1":
            pytest.fail(f"Required family packages missing: {missing}")
        pytest.skip(f"Optional family packages missing: {missing}")
    assert not audit(tmp_path)
