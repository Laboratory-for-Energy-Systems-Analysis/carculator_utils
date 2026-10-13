"""Pollutant identity, mass conservation and lifetime-average deterioration."""

import importlib.util
import os
import runpy
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from carculator_utils import hot_emissions
from carculator_utils.inventory import Inventory, get_exhaust_emission_flows


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


def test_aggregate_hydrocarbons_cannot_change_pah_inventory():
    """A large THC diagnostic must not be routed to the much smaller PAH flow."""
    from types import SimpleNamespace

    inventory = Inventory.__new__(Inventory)
    inventory.vm = SimpleNamespace(vehicle_type="car")
    inventory.exhaust_emissions = get_exhaust_emission_flows()
    labels = [
        *inventory.exhaust_emissions,
        ("transport, car, ICEV-p, Medium", "CH", "kilometer", "transport"),
    ]
    inventory.inputs = {key: i for i, key in enumerate(labels)}
    inventory.rev_inputs = dict(enumerate(labels))
    parameters = [
        p
        for names in inventory.exhaust_emissions.values()
        for p in ((names,) if isinstance(names, str) else names)
    ]
    aggregates = [
        f"Hydrocarbons direct emissions, {c}" for c in ("urban", "suburban", "rural")
    ]
    inventory.array = xr.DataArray(
        np.zeros((1, len(parameters) + 3, 1, 1)),
        dims=("value", "parameter", "combined_dim", "year"),
        coords={
            "value": [0],
            "parameter": parameters + aggregates,
            "combined_dim": ["Medium - ICEV-p"],
            "year": [2020],
        },
    )
    inventory.A = np.zeros((1, len(labels), len(labels), 1))
    for compartment, mass in (("urban", 1e-9), ("suburban", 2e-9), ("rural", 3e-9)):
        inventory.array.loc[
            dict(
                parameter=f"PAH, polycyclic aromatic hydrocarbons direct emissions, {compartment}"
            )
        ] = mass
    inventory.add_exhaust_emissions()
    before = inventory.A.copy()
    inventory.array.loc[dict(parameter=aggregates)] = 1.0
    inventory.add_exhaust_emissions()
    np.testing.assert_array_equal(inventory.A, before)
    for compartment, expected in (
        ("urban air close to ground", 1e-9),
        ("non-urban air or from high stacks", 5e-9),
    ):
        row = inventory.inputs[
            ("PAH, polycyclic aromatic hydrocarbons", ("air", compartment), "kilogram")
        ]
        assert -inventory.A[0, row, -1, 0] == pytest.approx(expected, rel=1e-12, abs=0)


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


@pytest.fixture
def isolated_car_emissions():
    """Known process masses on a labelled trace spanning all air compartments."""
    velocity = (
        xr.DataArray([0.0, 20.0, 35.0, 0.0], dims="second", coords={"second": range(4)})
        .expand_dims(
            value=[0, 1],
            year=[2020, 2030],
            powertrain=["ICEV-p", "HEV-p", "PHEV-c-p"],
            size=["Mini", "Medium"],
        )
        .transpose("second", "value", "year", "powertrain", "size")
    )
    hem = hot_emissions.HotEmissionsModel(
        velocity.powertrain.values,
        velocity.coords["size"].values,
        velocity,
        "WLTC",
        "car",
    )
    hem.exhaust[:] = 0
    hem.non_exhaust[:] = 0
    hem.engine_wear[:] = 0
    lifetime = xr.full_like(velocity.isel(second=0, drop=True), 200000)
    annual = xr.full_like(lifetime, 10000)
    annual.loc[dict(value=1)] = 20000
    annual.loc[dict(year=2030)] *= 2
    energy = xr.zeros_like(velocity)
    return hem, lifetime, annual, energy


@pytest.mark.parametrize("process", ["soak", "diurnal", "running losses"])
def test_evaporation_retains_benzene_and_residual_without_exhaust_species(
    isolated_car_emissions, process
):
    hem, lifetime, annual, energy = isolated_car_emissions
    hem.non_exhaust.loc[
        dict(powertrain="ICEV-p", type=process, component="Non-methane hydrocarbon")
    ] = 10
    hem.non_exhaust.loc[
        dict(powertrain="ICEV-p", type=process, component="Benzene")
    ] = 1
    original = hem.non_exhaust.copy(deep=True)
    result = hem.get_hot_emissions([6.2, 6.3], lifetime, energy, annual)
    factor = {
        "soak": 2.3 * 365 / annual,
        "diurnal": 365 / annual,
        "running losses": xr.ones_like(annual),
    }[process]

    def total(component):
        return sum(
            result.sel(component=f"{component}, {env}", drop=True)
            for env in ("urban", "suburban", "rural")
        )

    # Independently specified mixture: 10% benzene, 90% unspecified NMHC.
    xr.testing.assert_allclose(
        total("Benzene"), (factor / 1000).transpose(*total("Benzene").dims)
    )
    xr.testing.assert_allclose(
        total("Non-methane hydrocarbon"),
        (9 * factor / 1000).transpose(*total("Benzene").dims),
    )
    for component in hem.nmhc_species.component.values:
        assert bool((total(component) == 0).all()), component
    xr.testing.assert_identical(hem.non_exhaust, original)
    xr.testing.assert_identical(
        result, hem.get_hot_emissions([6.2, 6.3], lifetime, energy, annual)
    )


def test_evaporation_does_not_change_cold_start_or_hot_exhaust_speciation(
    isolated_car_emissions,
):
    hem, lifetime, annual, energy = isolated_car_emissions
    energy[:] = 1000  # 4 MJ total on a 0.055 km trace.
    hem.exhaust.loc[dict(powertrain="ICEV-p", component="Non-methane hydrocarbon")] = 2
    hem.non_exhaust.loc[
        dict(
            powertrain="ICEV-p", type="cold start", component="Non-methane hydrocarbon"
        )
    ] = 3
    reference = hem.get_hot_emissions([6.2, 6.3], lifetime, energy, annual)
    # No NMHC deterioration is defined in the shipped car degradation table.
    expected = (8 / 0.055 + 3 * 2.3 * 365 / annual) * 0.017 / 1000
    actual = sum(
        reference.sel(component=f"Formaldehyde, {env}", drop=True)
        for env in ("urban", "suburban", "rural")
    )
    xr.testing.assert_allclose(actual, expected.transpose(*actual.dims))
    hem.non_exhaust.loc[
        dict(powertrain="ICEV-p", type="diurnal", component="Non-methane hydrocarbon")
    ] = 10
    updated = hem.get_hot_emissions([6.2, 6.3], lifetime, energy, annual)
    components = [
        f"{c}, {env}"
        for c in hem.nmhc_species.component.values
        for env in ("urban", "suburban", "rural")
    ]
    xr.testing.assert_identical(
        reference.sel(component=components), updated.sel(component=components)
    )


def test_invalid_evaporative_mass_balance_is_rejected(isolated_car_emissions):
    hem, lifetime, annual, energy = isolated_car_emissions
    hem.non_exhaust.loc[
        dict(powertrain="ICEV-p", type="diurnal", component="Non-methane hydrocarbon")
    ] = 1
    hem.non_exhaust.loc[
        dict(powertrain="ICEV-p", type="diurnal", component="Benzene")
    ] = 2
    with pytest.raises(ValueError, match="Evaporative benzene"):
        hem.get_hot_emissions([6.2, 6.3], lifetime, energy, annual)


@pytest.mark.parametrize("starts", [0, 1.8])
def test_daily_starts_scale_only_cold_start_and_soak(isolated_car_emissions, starts):
    hem, lifetime, annual, energy = isolated_car_emissions
    for process, grams in (("cold start", 3), ("soak", 4), ("diurnal", 5)):
        hem.non_exhaust.loc[
            dict(powertrain="ICEV-p", type=process, component="Non-methane hydrocarbon")
        ] = grams
    result = hem.get_hot_emissions(
        [6.2, 6.3], lifetime, energy, annual, starts_per_day=starts
    )
    total = lambda name: sum(
        result.sel(component=f"{name}, {env}", drop=True)
        for env in ("urban", "suburban", "rural")
    )
    expected_formaldehyde = 3 * starts * 365 / annual * 0.017 / 1000
    xr.testing.assert_allclose(
        total("Formaldehyde"),
        expected_formaldehyde.transpose(*total("Formaldehyde").dims),
    )
    # Named exhaust fractions sum to 0.492; soak and diurnal are unspeciated.
    expected_nmvoc = ((3 * 0.508 + 4) * starts + 5) * 365 / annual / 1000
    xr.testing.assert_allclose(
        total("Non-methane hydrocarbon"),
        expected_nmvoc.transpose(*total("Non-methane hydrocarbon").dims),
    )


@pytest.mark.parametrize(
    "value", [-1, float("nan"), float("inf"), True, "1.8", [1.8], None]
)
def test_invalid_daily_starts_are_rejected(value):
    with pytest.raises(ValueError, match="starts_per_day"):
        hot_emissions.validate_starts_per_day(value)


def test_zero_mileage_aggregate_phev_placeholder(isolated_car_emissions):
    hem, lifetime, annual, energy = isolated_car_emissions
    labels = ["ICEV-p", "HEV-p", "PHEV-p"]
    hem.velocity = hem.velocity.assign_coords(powertrain=labels)
    lifetime = lifetime.assign_coords(powertrain=labels)
    annual = annual.assign_coords(powertrain=labels)
    energy = energy.assign_coords(powertrain=labels)
    annual.loc[dict(powertrain="PHEV-p")] = 0
    hem.non_exhaust.loc[
        dict(powertrain="ICEV-p", type="diurnal", component="Non-methane hydrocarbon")
    ] = 10
    hem.non_exhaust.loc[
        dict(powertrain="ICEV-p", type="diurnal", component="Benzene")
    ] = 1
    result = hem.get_hot_emissions([6.2, 6.3], lifetime, energy, annual)
    assert bool(np.isfinite(result).all())
    assert bool((result.sel(powertrain="PHEV-p") == 0).all())
    assert bool((annual.sel(powertrain="PHEV-p") == 0).all())


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
