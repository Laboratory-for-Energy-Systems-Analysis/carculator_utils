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


def test_total_hydrocarbons_remain_a_diagnostic_aggregate():
    mapping = get_exhaust_emission_flows()
    assert not any(flow[0] == "Hydrocarbons, chlorinated" for flow in mapping)
    parameters = [
        p
        for names in mapping.values()
        for p in ((names,) if isinstance(names, str) else names)
    ]
    assert not any(p.startswith("Hydrocarbons direct emissions,") for p in parameters)
    for environment in ("urban", "suburban", "rural"):
        assert f"Methane direct emissions, {environment}" in parameters
        assert f"Non-methane hydrocarbon direct emissions, {environment}" in parameters


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
    for environments, compartment in (
        (("urban",), "urban air close to ground"),
        (("suburban", "rural"), "non-urban air or from high stacks"),
    ):

        def expected(pollutant):
            names = tuple(
                f"{pollutant} direct emissions, {env}" for env in environments
            )
            return names[0] if len(names) == 1 else names

        assert mapping[("Ethane", ("air", compartment), "kilogram")] == expected(
            "Ethane"
        )
        assert mapping[("Ethylene", ("air", compartment), "kilogram")] == expected(
            "Ethene"
        )
        assert (
            mapping[
                (
                    "NMVOC, non-methane volatile organic compounds",
                    ("air", compartment),
                    "kilogram",
                )
            ]
        ) == expected("Non-methane hydrocarbon")
    assert not any(
        "long-term" in compartment for flow in mapping for compartment in flow[1]
    )


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
