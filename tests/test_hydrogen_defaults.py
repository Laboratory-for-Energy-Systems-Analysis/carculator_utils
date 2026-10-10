"""Hydrogen supply assumptions must be independent of petrol biofuel data."""

import importlib
import os
from copy import deepcopy

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.background_systems import BackgroundSystemModel

SMR = "hydrogen - smr - natural gas"
PEM = "hydrogen - electrolysis - PEM"
YEARS = [2030, 2020, 2025]
CASES = [
    ("carculator", "Car", "Medium", "BR", {}),
    ("carculator_bus", "Bus", "13m-city", "CH", {}),
    ("carculator_truck", "Truck", "40t", "DE", {"cycle": "Long haul"}),
]


@pytest.fixture(scope="module")
def background():
    return BackgroundSystemModel()


@pytest.mark.parametrize("country", ["CH", "DE", "BR", "RER", "XX"])
@pytest.mark.parametrize("years", [[2025], YEARS, [2000, 2050]])
def test_default_hydrogen_is_all_natural_gas_smr(background, country, years):
    blend = background.define_fuel_blends(["FCEV"], country, years)["hydrogen"]
    assert blend["primary"]["type"] == SMR
    assert blend["secondary"]["type"] == PEM
    np.testing.assert_array_equal(blend["primary"]["share"], np.ones(len(years)))
    np.testing.assert_array_equal(blend["secondary"]["share"], np.zeros(len(years)))


def test_hydrogen_never_reads_biofuel_shares(background, monkeypatch):
    def unrelated_input(*args, **kwargs):
        pytest.fail("Hydrogen defaults must not read biofuel shares")

    monkeypatch.setattr(background, "get_share_biofuel", unrelated_input)
    background.define_fuel_blends(["FCEV"], "CH", YEARS)


@pytest.fixture(scope="module", params=CASES, ids=lambda case: case[0])
def family_case(request):
    name, prefix, size, country, kwargs = request.param
    if importlib.util.find_spec(name) is None:
        if os.environ.get("CARCULATOR_REQUIRE_FAMILY") == "1":
            pytest.fail(f"Required family package {name} missing")
        pytest.skip(f"Optional family package {name} missing")
    package = importlib.import_module(name)
    inputs = getattr(package, prefix + "InputParameters")()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={"size": [size], "powertrain": ["FCEV"], "year": sorted(YEARS)},
    )
    array = array.sel(year=YEARS).isel(value=[0, 0]).assign_coords(value=[9, 2])
    array.loc[dict(parameter="average passengers", value=2)] *= 1.1
    model_type = getattr(package, prefix + "Model")
    baseline = model_type(array, country=country, **kwargs)
    baseline.set_all()
    return array, baseline, model_type, getattr(package, "Inventory" + prefix), kwargs


@pytest.fixture(scope="module", params=["default", "electrolysis", "yearly"])
def completed_inventory(request, family_case):
    array, baseline, model_type, inventory_type, kwargs = family_case
    mode = request.param
    overrides = None
    smr_shares = np.ones(3)
    if mode == "electrolysis":
        overrides = {"hydrogen": {"primary": {"type": PEM, "share": 1.0}}}
        smr_shares = np.zeros(3)
    elif mode == "yearly":
        smr_shares = np.array([0, 0.65, 1])
        overrides = {
            "hydrogen": {
                "primary": {"type": SMR, "share": smr_shares.tolist()},
                "secondary": {"type": PEM, "share": [1, 0.35, 0]},
            }
        }
    before = array.copy(deep=True)
    requested = deepcopy(overrides)
    model = model_type(array, country=baseline.country, fuel_blend=overrides, **kwargs)
    model.set_all()
    assert overrides == requested
    xr.testing.assert_identical(array, before)
    # The supply route changes upstream impacts, not hydrogen use on the road.
    for parameter in ("TtW energy", "fuel consumption", "fuel mass"):
        xr.testing.assert_allclose(model[parameter], baseline[parameter])
    inventory = inventory_type(model, scenario="static", functional_unit="vkm")
    impacts = inventory.calculate_impacts()
    assert np.isfinite(impacts).all()
    assert (impacts.sel(impact_category="climate change").sum("impact") > 0).all()
    return model, inventory, inventory_type, smr_shares


@pytest.mark.family
def test_completed_hydrogen_suppliers_and_vehicle_exchanges(completed_inventory):
    model, inventory, _, smr_shares = completed_inventory
    (market,) = inventory.find_input_indices(("fuel supply for hydrogen vehicles",))
    (transport,) = inventory.find_input_indices(
        (f"transport, {model.vehicle_type}, FCEV,",)
    )
    for fuel, share in ((SMR, smr_shares), (PEM, 1 - smr_shares)):
        supplier = inventory.inputs[tuple(model.bs.fuel_specs[fuel]["name"])]
        np.testing.assert_allclose(
            -inventory.A[:, supplier, market, :], np.broadcast_to(share, (2, 3))
        )
    energy = (
        model["TtW energy"].isel(size=0, powertrain=0).transpose("value", "year").values
    )
    # Both routes supply the same molecule, with a catalog LHV of 120 MJ/kg.
    assert model.bs.fuel_specs[SMR]["lhv"] == 120
    assert model.bs.fuel_specs[PEM]["lhv"] == 120
    assert (energy > 0).all()
    np.testing.assert_allclose(
        -inventory.A[:, market, transport, :], energy / 120_000, rtol=2e-5
    )
    for origin in ("fossil", "non-fossil"):
        flow = inventory.inputs[(f"Carbon dioxide, {origin}", ("air",), "kilogram")]
        np.testing.assert_array_equal(inventory.A[:, flow, transport, :], 0)


@pytest.mark.family
@pytest.mark.export
def test_hydrogen_shares_and_vehicle_exchanges_survive_export(
    completed_inventory, tmp_path
):
    pytest.importorskip("bw2io")
    model, _, inventory_type, smr_shares = completed_inventory
    selected = deepcopy(model)
    selected.array = selected.array.sel(value=[2])
    inventory = inventory_type(selected, scenario="static", functional_unit="vkm")
    before = inventory.A.copy()
    indices_before = inventory.inputs.copy()
    exports = inventory.export_lci(
        ecoinvent_version="3.12", format="bw2io", directory=tmp_path
    )
    assert len(exports) == 3
    for yi, (year, importer) in enumerate(zip(YEARS, exports)):
        assert importer.db_name.endswith(str(year))
        (market,) = [
            d
            for d in importer.data
            if d["name"].startswith("fuel supply for hydrogen vehicles")
        ]
        suppliers = {
            e["name"]: e["amount"]
            for e in market["exchanges"]
            # Blend shares are kg hydrogen/kg delivered hydrogen. Compression
            # electricity is a separate input, measured in kWh/kg hydrogen.
            if e["type"] == "technosphere" and e["unit"] == "kilogram"
        }
        expected = {
            model.bs.fuel_specs[fuel]["name"][0]: share
            for fuel, share in ((SMR, smr_shares[yi]), (PEM, 1 - smr_shares[yi]))
            if share > 0
        }
        assert suppliers == pytest.approx(expected)
        (compression,) = [
            e
            for e in market["exchanges"]
            if e["type"] == "technosphere" and e["unit"] != "kilogram"
        ]
        assert compression["unit"] == "kilowatt hour"
        assert compression["name"].startswith("electricity supply for fuel preparation")
        assert compression["amount"] > 0
        assert compression["amount"] == pytest.approx(
            inventory.hydrogen_compression["electricity kWh/kg"][yi]
        )
        (vehicle,) = [
            d
            for d in importer.data
            if d["name"].startswith(f"transport, {model.vehicle_type}, ")
        ]
        (purchase,) = [
            e
            for e in vehicle["exchanges"]
            if e["type"] == "technosphere" and e["name"] == market["name"]
        ]
        energy = selected["TtW energy"].sel(year=year).item()
        assert purchase["amount"] == pytest.approx(energy / 120_000, rel=2e-5)
        carbon = sum(
            abs(e["amount"])
            for e in vehicle["exchanges"]
            if e["type"] == "biosphere"
            and e["name"] in ("Carbon dioxide, fossil", "Carbon dioxide, non-fossil")
        )
        assert carbon == 0
    np.testing.assert_array_equal(inventory.A, before)
    assert inventory.inputs == indices_before
