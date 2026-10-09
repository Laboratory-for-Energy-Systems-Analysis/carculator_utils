"""Missing country climate requires an explicit profile; bus runs retain decimals."""

import csv
import importlib
import os

import numpy as np
import pytest
import xarray as xr

from carculator_utils import energy_consumption
from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.energy_consumption import get_country_temperature

# January--December values from the bundled Swiss row, in degrees Celsius.
SWISS_TEMPERATURES = np.array(
    [1.9, 4.4, 8.3, 12.4, 17.0, 20.4, 23.3, 22.5, 19.2, 13.5, 6.8, 2.7]
)
MISSING_COUNTRIES = ["BR", "US", "CA", "IN", "AU"]
POWERTRAINS = ["ICEV-d", "FCEV", "BEV-depot"]


@pytest.mark.parametrize("country", [*MISSING_COUNTRIES, "XX"])
def test_missing_country_requires_explicit_climate(country):
    with pytest.raises(ValueError, match=f"series for {country}.*ambient_temperature"):
        get_country_temperature(country)


def test_existing_country_preserves_temperatures_without_fallback_notice(capsys):
    np.testing.assert_array_equal(get_country_temperature("CH"), SWISS_TEMPERATURES)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("country", ["CH"])
def test_direct_and_fallback_parsing_preserve_negative_decimals(
    country, tmp_path, monkeypatch
):
    expected = [
        -2.75,
        -1.25,
        3.5,
        8.25,
        12.5,
        17.75,
        20.25,
        19.5,
        15.25,
        9.5,
        4.25,
        -0.5,
    ]
    with (tmp_path / energy_consumption.MONTHLY_AVG_TEMP).open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(["city", "country", "iso_code", *range(1, 13)])
        writer.writerow(["test city", "Switzerland", "CH", *expected])
    monkeypatch.setattr(energy_consumption, "DATA_DIR", tmp_path)
    np.testing.assert_array_equal(get_country_temperature(country), expected)


@pytest.fixture(scope="module")
def bus_inputs():
    name = "carculator_bus"
    if importlib.util.find_spec(name) is None:
        if os.environ.get("CARCULATOR_REQUIRE_FAMILY") == "1":
            pytest.fail(f"Required family package {name} missing")
        pytest.skip(f"Optional family package {name} missing")
    package = importlib.import_module(name)
    inputs = package.BusInputParameters()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={"size": ["13m-city"], "powertrain": POWERTRAINS, "year": [2025, 2030]},
    )
    array = array.sel(year=[2030, 2025]).isel(value=[0, 0]).assign_coords(value=[9, 2])
    array.loc[dict(parameter="average passengers", value=2)] *= 1.1
    return package, array


@pytest.mark.family
@pytest.mark.parametrize("country", MISSING_COUNTRIES)
def test_completed_bus_requires_explicit_temperature_for_missing_country(
    bus_inputs, country, capsys
):
    package, source = bus_inputs
    before = source.copy(deep=True)
    missing = package.BusModel(source, country=country)
    initialized = missing.array.copy(deep=True)
    with pytest.raises(ValueError, match=f"series for {country}.*ambient_temperature"):
        missing.set_all()
    xr.testing.assert_identical(missing.array, initialized)
    xr.testing.assert_identical(source, before)
    # Explicit profile is a user-selected scenario, not a measured local climate.
    requested = SWISS_TEMPERATURES.copy()
    explicit = package.BusModel(source, country=country, ambient_temperature=requested)
    explicit.set_all()
    assert "Uses those for CH instead" not in capsys.readouterr().out
    np.testing.assert_array_equal(requested, SWISS_TEMPERATURES)
    xr.testing.assert_identical(source, before)
    for parameter in ("TtW energy", "driving mass"):
        assert np.isfinite(explicit[parameter]).all()
        assert (explicit[parameter] > 0).all()
    assert (explicit["electricity consumption"].sel(powertrain="BEV-depot") > 0).all()

    inventory = package.InventoryBus(explicit, scenario="static", functional_unit="vkm")
    impacts = inventory.calculate_impacts()
    assert np.isfinite(impacts).all()

    for powertrain, fuel in (("ICEV-d", "diesel"), ("FCEV", "hydrogen")):
        (market,) = inventory.find_input_indices((f"fuel supply for {fuel} vehicles",))
        (transport,) = inventory.find_input_indices((f"transport, bus, {powertrain},",))
        energy = (
            explicit["TtW energy"]
            .sel(powertrain=powertrain)
            .isel(size=0)
            .transpose("value", "year")
            .values
        )
        lhv = sum(
            component["share"] * explicit.bs.fuel_specs[component["type"]]["lhv"]
            for component in explicit.fuel_blend[fuel].values()
        )
        np.testing.assert_allclose(
            -inventory.A[:, market, transport, :], energy / (1000 * lhv), rtol=2e-5
        )
    (market,) = inventory.find_input_indices(
        ("electricity supply for electric vehicles",)
    )
    (transport,) = inventory.find_input_indices(("transport, bus, BEV-depot,",))
    charging = (
        explicit["electricity consumption"]
        .sel(powertrain="BEV-depot")
        .isel(size=0)
        .transpose("value", "year")
        .values
    )
    np.testing.assert_allclose(-inventory.A[:, market, transport, :], charging)


@pytest.mark.family
@pytest.mark.parametrize("temperature", [30.5, np.linspace(-4.5, 28.5, 12)])
def test_explicit_bus_temperature_bypasses_country_lookup(
    bus_inputs, temperature, monkeypatch
):
    def unexpected_lookup(country):
        pytest.fail(f"Explicit temperature must bypass country lookup for {country}")

    package, source = bus_inputs
    requested = (
        np.copy(temperature) if isinstance(temperature, np.ndarray) else temperature
    )
    monkeypatch.setattr(
        energy_consumption, "get_country_temperature", unexpected_lookup
    )
    model = package.BusModel(source, country="BR", ambient_temperature=requested)
    model.set_all()
    np.testing.assert_array_equal(
        model.ecm.ambient_temperature, np.broadcast_to(temperature, (12,))
    )
    np.testing.assert_array_equal(requested, temperature)
    assert np.isfinite(model["TtW energy"]).all()
    assert (model["TtW energy"] > 0).all()


@pytest.mark.parametrize("temperature", [np.nan, np.inf, -273.15, [[20] * 12], [20]])
def test_direct_hvac_rejects_invalid_ambient_profile(temperature):
    model = energy_consumption.EnergyConsumptionModel(
        "bus",
        ["13m-city"],
        ["BEV-depot"],
        np.array([0, 10, 0]),
        None,
        ambient_temperature=temperature,
    )
    with pytest.raises(ValueError, match="Ambient temperature"):
        model.calculate_hvac_energy(
            xr.DataArray(18000.0), xr.DataArray(2750.0), xr.DataArray(500.0)
        )
