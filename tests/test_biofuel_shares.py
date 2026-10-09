"""Bundled biofuel shares must survive interpolation and inventory assembly."""

import importlib
import itertools
import os
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.background_systems import BackgroundSystemModel

# Values supplied for both 2018 and 2050 in share_bio_cng.csv.
BIOMETHANE_SHARES = {"SE": 0.91211681, "NO": 0.382813676, "IS": 1.0}
CASES = [
    ("carculator", "Car", "Medium", {}),
    ("carculator_bus", "Bus", "13m-city", {}),
    ("carculator_truck", "Truck", "40t", {"cycle": "Long haul"}),
]


@pytest.fixture(scope="module")
def background():
    return BackgroundSystemModel()


@pytest.mark.parametrize("country,expected", BIOMETHANE_SHARES.items())
def test_supplied_and_interpolated_shares_above_thirty_percent(
    background, country, expected
):
    result = background.get_share_biofuel("biomethane", country, [2050, 2018, 2025])
    np.testing.assert_allclose(result, [expected] * 3, rtol=0, atol=1e-12)
    scalar = background.get_share_biofuel("biomethane", country, [2018])
    assert np.ndim(scalar) == 0
    assert scalar == pytest.approx(expected)


@pytest.mark.parametrize("fuel", ["biomethane", "bioethanol", "biodiesel"])
def test_interpolation_and_extrapolation_use_fraction_bounds_without_mutation(fuel):
    source = xr.DataArray(
        [[[0.2, 0.8]]],
        dims=("variable", "country", "year"),
        coords={"variable": ["value"], "country": ["XX"], "year": [2010, 2020]},
    )
    before = source.copy(deep=True)
    background = SimpleNamespace(biomethane=source, bioethanol=source, biodiesel=source)
    result = BackgroundSystemModel.get_share_biofuel(
        background, fuel, "XX", [2015, 2022, 2025, 2000, 2010, 2020]
    )
    # Linear slope 0.06/year; only extrapolations beyond [0, 1] are clipped.
    np.testing.assert_allclose(result, [0.5, 0.92, 1, 0, 0.2, 0.8])
    xr.testing.assert_identical(source, before)


@pytest.mark.parametrize(
    "fuel,expected",
    [("biomethane", 0.09), ("bioethanol", 0.04), ("biodiesel", 0.06)],
)
def test_existing_low_shares_are_preserved(background, fuel, expected):
    assert background.get_share_biofuel(fuel, "RER", [2018]) == pytest.approx(expected)


def test_unknown_country_keeps_regional_default(background):
    blend = background.define_fuel_blends(["ICEV-g"], "XX", [2018])["methane"]
    np.testing.assert_allclose(blend["primary"]["share"], [0.91])
    np.testing.assert_allclose(blend["secondary"]["share"], [0.09])


@pytest.fixture(
    scope="module",
    params=list(itertools.product(CASES, BIOMETHANE_SHARES)),
    ids=lambda case: f"{case[0][0]}-{case[1]}",
)
def completed_inventory(request):
    (name, prefix, size, kwargs), country = request.param
    if importlib.util.find_spec(name) is None:
        if os.environ.get("CARCULATOR_REQUIRE_FAMILY") == "1":
            pytest.fail(f"Required family package {name} missing")
        pytest.skip(f"Optional family package {name} missing")
    package = importlib.import_module(name)
    inputs = getattr(package, prefix + "InputParameters")()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={"size": [size], "powertrain": ["ICEV-g"], "year": [2020, 2025, 2030]},
    )
    array = (
        array.sel(year=[2030, 2025, 2020])
        .isel(value=[0, 0])
        .assign_coords(value=[9, 2])
    )
    array.loc[dict(parameter="average passengers", value=2)] *= 1.1
    model = getattr(package, prefix + "Model")(array, country=country, **kwargs)
    model.set_all()
    inventory_type = getattr(package, "Inventory" + prefix)
    inventory = inventory_type(model, scenario="static", functional_unit="vkm")
    assert np.isfinite(inventory.calculate_impacts()).all()
    return model, inventory, inventory_type, BIOMETHANE_SHARES[country]


@pytest.mark.family
def test_completed_default_supply_combustion_and_leakage(completed_inventory):
    model, inventory, _, bio = completed_inventory
    blend = model.fuel_blend["methane"]
    for role, expected in (("primary", 1 - bio), ("secondary", bio)):
        np.testing.assert_allclose(blend[role]["share"], [expected] * 3)
    (market,) = inventory.find_input_indices(("fuel supply for methane vehicles",))
    (transport,) = inventory.find_input_indices(
        (f"transport, {model.vehicle_type}, ICEV-g,",)
    )
    specs = model.bs.fuel_specs
    fossil = specs["methane"]
    nonfossil = specs["methane - biomethane - sewage sludge"]
    lhv = (1 - bio) * fossil["lhv"] + bio * nonfossil["lhv"]
    energy = (
        model["TtW energy"].isel(size=0, powertrain=0).transpose("value", "year").values
    )
    assert (energy > 0).all()
    mass = energy / (1000 * lhv)
    loss_rate = (
        model["CNG pump-to-tank leakage"]
        .isel(size=0, powertrain=0)
        .transpose("value", "year")
        .values
    )
    np.testing.assert_allclose(
        -inventory.A[:, market, transport, :], mass * (1 + loss_rate), rtol=2e-5
    )
    for origin, specification, share in (
        ("fossil", fossil, 1 - bio),
        ("non-fossil", nonfossil, bio),
    ):
        supplier = inventory.inputs[tuple(specification["name"])]
        np.testing.assert_allclose(
            -inventory.A[:, supplier, market, :], np.full((2, 3), share)
        )
        for substance, expected in (
            ("Carbon dioxide", mass * share * specification["co2"]),
            ("Methane", mass * loss_rate * share),
        ):
            flow = inventory.inputs[(f"{substance}, {origin}", ("air",), "kilogram")]
            np.testing.assert_allclose(
                -inventory.A[:, flow, transport, :], expected, rtol=2e-5, atol=1e-12
            )


@pytest.mark.family
@pytest.mark.export
def test_default_shares_and_carbon_survive_export(completed_inventory, tmp_path):
    pytest.importorskip("bw2io")
    model, _, inventory_type, bio = completed_inventory
    selected = deepcopy(model)
    selected.array = selected.array.sel(value=[2])
    inventory = inventory_type(selected, scenario="static", functional_unit="vkm")
    before = inventory.A.copy()
    exports = inventory.export_lci(
        ecoinvent_version="3.10", format="bw2io", directory=tmp_path
    )
    assert len(exports) == 3
    (transport,) = inventory.find_input_indices(
        (f"transport, {model.vehicle_type}, ICEV-g,",)
    )
    for year_index, (year, importer) in enumerate(
        zip(selected.array.year.values, exports)
    ):
        assert importer.db_name.endswith(str(year))
        (market,) = [
            d
            for d in importer.data
            if d["name"].startswith("fuel supply for methane vehicles")
        ]
        suppliers = {
            e["name"]: e["amount"]
            for e in market["exchanges"]
            if e["type"] == "technosphere"
        }
        for role, expected in (("primary", 1 - bio), ("secondary", bio)):
            name = selected.fuel_blend["methane"][role]["name"][0]
            assert suppliers.get(name, 0) == pytest.approx(expected)
        assert sum(suppliers.values()) == pytest.approx(1)
        (vehicle,) = [
            d
            for d in importer.data
            if d["name"].startswith(f"transport, {model.vehicle_type}, ")
        ]
        for substance in ("Carbon dioxide", "Methane"):
            for origin in ("fossil", "non-fossil"):
                flow = (f"{substance}, {origin}", ("air",), "kilogram")
                amount = sum(
                    e["amount"]
                    for e in vehicle["exchanges"]
                    if e["type"] == "biosphere"
                    and e["name"] == flow[0]
                    and tuple(e["categories"]) == flow[1]
                )
                assert amount == pytest.approx(
                    -before[0, inventory.inputs[flow], transport, year_index], abs=1e-12
                )
    np.testing.assert_array_equal(inventory.A, before)
