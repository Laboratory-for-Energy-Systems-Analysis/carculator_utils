"""Small real-model contracts shared by the four downstream packages."""

import importlib
import importlib.util
import os
from copy import deepcopy
from dataclasses import dataclass

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters

pytestmark = pytest.mark.family


@dataclass(frozen=True)
class VehicleCase:
    package: str
    prefix: str
    size: str
    powertrain: str
    unit: str = "pkm"
    cycle: str | None = None


CASES = [
    VehicleCase("carculator", "Car", "Medium", "BEV"),
    VehicleCase("carculator_truck", "Truck", "40t", "BEV", "tkm", "Long haul"),
    VehicleCase("carculator_bus", "Bus", "13m-city", "BEV-depot"),
    VehicleCase("carculator_two_wheeler", "TwoWheeler", "Bicycle <25", "BEV"),
]


def load_vehicle_package(name):
    if importlib.util.find_spec(name) is None:
        if os.environ.get("CARCULATOR_REQUIRE_FAMILY") == "1":
            pytest.fail(f"Family verification requires installed package {name!r}.")
        pytest.skip(f"Optional downstream package {name!r} is not installed.")
    # An installed package with a broken import must fail, not be skipped.
    return importlib.import_module(name)


@pytest.fixture(scope="module", params=CASES, ids=lambda case: case.package)
def vehicle(request):
    case = request.param
    package = load_vehicle_package(case.package)
    inputs = getattr(package, case.prefix + "InputParameters")()
    inputs.static()
    scope = {"size": [case.size], "powertrain": [case.powertrain], "year": [2020, 2030]}
    scope_before = deepcopy(scope)
    mappings, source = fill_xarray_from_input_parameters(inputs, scope=scope)
    assert scope == scope_before
    for mapping, dimension in zip(
        mappings, ("size", "powertrain", "parameter", "year")
    ):
        assert mapping == dict(
            (value, index)
            for index, value in enumerate(source[dimension].values.tolist())
        )
    source = source.isel(value=[0, 0]).assign_coords(value=[0, 1])
    before = source.copy(deep=True)
    storage = {"origin": "CH"}
    kwargs = {"cycle": case.cycle} if case.cycle else {}
    model = getattr(package, case.prefix + "Model")(
        source.transpose("value", "year", "parameter", "size", "powertrain"),
        energy_storage=storage,
        **kwargs,
    )
    model.set_all()
    xr.testing.assert_identical(source, before)
    assert storage == {"origin": "CH"}
    return case, package, model


def test_sizing_preserves_coordinates_and_mass_balance(vehicle):
    case, package, model = vehicle
    assert model.array.dims == ("size", "powertrain", "parameter", "year", "value")
    assert model.array.value.values.tolist() == [0, 1]
    assert model.array.year.values.tolist() == [2020, 2030]
    for parameter in ("curb mass", "driving mass", "TtW energy"):
        assert np.isfinite(model[parameter]).all()
        assert (model[parameter] > 0).all()
    xr.testing.assert_allclose(
        model["driving mass"].drop_vars("parameter"),
        (model["curb mass"] + model["total cargo mass"]),
        rtol=1e-5,
    )
    assert model.energy_storage["origin"] == "CH"


def test_impacts_normalize_each_sample(vehicle):
    case, package, original = vehicle
    model = deepcopy(original)
    # Vary only the normalization input to isolate the per-sample algebra.
    parameter = "cargo mass" if case.unit == "tkm" else "average passengers"
    divisor = xr.DataArray([2.0, 4.0], dims="value", coords={"value": [0, 1]})
    model[parameter] = divisor * (1000 if case.unit == "tkm" else 1)
    inventory_class = getattr(package, "Inventory" + case.prefix)
    base = inventory_class(model)
    vkm = base.calculate_impacts()
    assert np.isfinite(vkm).all()
    del base
    inventory = inventory_class(model, functional_unit=case.unit)
    normalized = inventory.calculate_impacts()
    xr.testing.assert_allclose(normalized, vkm / divisor, rtol=1e-5)


def test_static_exports_preserve_inventory_for_all_years(vehicle, tmp_path):
    case, package, original = vehicle
    model = deepcopy(original)
    # The exporter supports static inventories with exactly one value sample.
    model.array = model.array.isel(value=[0])
    inventory = getattr(package, "Inventory" + case.prefix)(
        model, functional_unit=case.unit
    )
    normalized = inventory.calculate_impacts()
    before = inventory.A.copy()
    inputs = inventory.inputs.copy()
    reverse = inventory.rev_inputs.copy()
    unit = "tkm" if case.unit == "tkm" else "personkm"
    for _ in range(2):
        exports = inventory.export_lci(
            software="simapro", format="string", directory=tmp_path
        )
        assert len(exports) == 2
        for year, content in zip([2020, 2030], exports):
            assert str(year) in content
            assert unit in content
    np.testing.assert_array_equal(inventory.A, before)
    assert inventory.inputs == inputs
    assert inventory.rev_inputs == reverse
    xr.testing.assert_allclose(inventory.calculate_impacts(), normalized)


@pytest.mark.parametrize(
    "case,powertrains",
    [
        (CASES[0], ["PHEV-p"]),
        (CASES[2], ["BEV-depot", "BEV-opp", "BEV-motion"]),
        (CASES[3], ["Human", "BEV"]),
    ],
    ids=["car-phev", "bus-charging", "two-wheeler-human-electric"],
)
def test_vehicle_specific_modes_remain_supported(case, powertrains):
    package = load_vehicle_package(case.package)
    inputs = getattr(package, case.prefix + "InputParameters")()
    inputs.static()
    scope = {"size": [case.size], "powertrain": powertrains, "year": [2020]}
    before = deepcopy(scope)
    _, array = fill_xarray_from_input_parameters(inputs, scope=scope)
    model = getattr(package, case.prefix + "Model")(array)
    model.set_all()
    assert scope == before
    assert set(powertrains) <= set(model.array.powertrain.values)
    assert np.isfinite(model["TtW energy"]).all()
    assert (model["TtW energy"].sel(powertrain=powertrains) > 0).all()


def test_scalar_fuel_share_supports_multiple_inventory_years():
    package = load_vehicle_package("carculator")
    inputs = package.CarInputParameters()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={"size": ["Medium"], "powertrain": ["ICEV-d"], "year": [2020, 2030]},
    )
    model = package.CarModel(
        array, fuel_blend={"diesel": {"primary": {"type": "diesel", "share": 0.8}}}
    )
    model.set_all()
    result = package.InventoryCar(model).calculate_impacts()
    assert result.year.values.tolist() == [2020, 2030]
    assert np.isfinite(result).all()
