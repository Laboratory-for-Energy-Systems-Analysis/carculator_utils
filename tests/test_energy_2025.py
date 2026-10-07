"""Native 2025 defaults and complete scoped vehicle construction."""

import importlib
import importlib.util
import json
import os

import numpy as np
import pytest
import xarray as xr

from carculator_utils.vehicle_input_parameters import validate_parameters

pytestmark = pytest.mark.family

FAMILIES = [
    ("carculator", "Car"),
    ("carculator_bus", "Bus"),
    ("carculator_truck", "Truck"),
    ("carculator_two_wheeler", "TwoWheeler"),
]


def load_vehicle_package(name):
    if importlib.util.find_spec(name) is None:
        if os.environ.get("CARCULATOR_REQUIRE_FAMILY") == "1":
            pytest.fail(f"Family verification requires installed package {name!r}.")
        pytest.skip(f"Optional downstream package {name!r} is not installed.")
    return importlib.import_module(name)


@pytest.mark.parametrize("package,prefix", FAMILIES)
def test_native_2025_defaults_cover_existing_cells_and_sample(package, prefix):
    module = load_vehicle_package(package)
    cls = getattr(module, prefix + "InputParameters")
    records = json.loads(cls.DEFAULT.read_text())
    current = {key: value for key, value in records.items() if value["year"] == 2025}
    validate_parameters(current, check_duplicates=True)

    def cells(values):
        return {
            (r["name"], size, powertrain)
            for r in values
            for size in r["sizes"]
            for powertrain in r["powertrain"]
        }

    interpolated = {
        k: r
        for k, r in current.items()
        if r["name"]
        not in {
            "electric motor efficiency",
            "electric motor power share",
            "electric transmission efficiency",
        }
    }
    prior_cells = cells(r for r in records.values() if r["year"] in (2020, 2030))
    actual_cells = cells(interpolated.values())
    assert prior_cells <= actual_cells
    assert all(
        name == "battery discharge efficiency"
        and powertrain in {"PHEV-c-p", "PHEV-c-d"}
        for name, size, powertrain in actual_cells - prior_cells
    )
    inputs = cls(parameters=current)
    inputs.stochastic(4, seed=2025)
    _, array = module.fill_xarray_from_input_parameters(inputs, scope={"year": [2025]})
    assert array.year.values.tolist() == [2025]
    assert array.sizes["value"] == 4
    assert np.isfinite(array).all()


@pytest.mark.parametrize(
    "package,prefix,size,powertrain",
    [
        ("carculator", "Car", "Medium", "ICEV-p"),
        ("carculator_bus", "Bus", "13m-city", "ICEV-d"),
        ("carculator_bus", "Bus", "13m-city", "ICEV-g"),
        ("carculator_truck", "Truck", "7.5t", "ICEV-d"),
        ("carculator_truck", "Truck", "7.5t", "ICEV-g"),
        ("carculator_two_wheeler", "TwoWheeler", "Bicycle <25", "BEV"),
        ("carculator_two_wheeler", "TwoWheeler", "Bicycle <25", "Human"),
        ("carculator_two_wheeler", "TwoWheeler", "Moped <4kW", "ICEV-p"),
    ],
)
def test_complete_native_2025_run(package, prefix, size, powertrain):
    module = load_vehicle_package(package)
    inputs = getattr(module, prefix + "InputParameters")()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs, scope={"size": [size], "powertrain": [powertrain], "year": [2025]}
    )
    kwargs = {}
    if package == "carculator_bus":
        # This public NumPy-cycle path previously failed before energy modelling.
        kwargs["cycle"] = np.array(
            [0, 10, 20, 30, 30, 30, 20, 10, 0, 0, 10, 20, 0], dtype=float
        )
    model = getattr(module, prefix + "Model")(array, **kwargs)
    model.set_all()
    assert model.array.year.values.tolist() == [2025]
    for name in ("driving mass", "TtW energy"):
        assert np.isfinite(model[name]).all()
        assert (model[name] > 0).all()


def test_partial_public_efficiency_override_preserves_other_vehicles():
    module = load_vehicle_package("carculator")
    inputs = module.CarInputParameters()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs,
        scope={"size": ["Medium"], "powertrain": ["ICEV-p", "BEV"], "year": [2025]},
    )
    baseline = module.CarModel(array)
    baseline.set_all()
    override = {("ICEV-p", "Medium", 2025): 0.33}
    modified = module.CarModel(array, engine_efficiency=override)
    modified.set_all()
    np.testing.assert_allclose(
        modified.energy.sel(parameter="engine efficiency", powertrain="ICEV-p"), 0.33
    )
    xr.testing.assert_allclose(
        baseline.energy.sel(powertrain="BEV"), modified.energy.sel(powertrain="BEV")
    )
    assert override == {("ICEV-p", "Medium", 2025): 0.33}


@pytest.mark.parametrize(
    "package,prefix,size,powertrain",
    [
        ("carculator_bus", "Bus", "13m-city", "ICEV-d"),
        ("carculator_truck", "Truck", "7.5t", "ICEV-d"),
        ("carculator_two_wheeler", "TwoWheeler", "Bicycle <25", "BEV"),
    ],
)
def test_efficiency_overrides_reach_each_vehicle_family(
    package, prefix, size, powertrain
):
    module = load_vehicle_package(package)
    inputs = getattr(module, prefix + "InputParameters")()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs, scope={"size": [size], "powertrain": [powertrain], "year": [2025]}
    )
    array = array.isel(value=[0, 0]).assign_coords(value=[0, 1])
    model = getattr(module, prefix + "Model")(
        array,
        engine_efficiency={(powertrain, size, 2025): [0.4, 0.5]},
        transmission_efficiency={(powertrain, size, 2025): 0.9},
    )
    model.set_all()
    for sample, expected in enumerate([0.4, 0.5]):
        np.testing.assert_allclose(
            model.energy.sel(parameter="engine efficiency", value=sample), expected
        )
    np.testing.assert_allclose(
        model.energy.sel(parameter="transmission efficiency"), 0.9
    )


@pytest.mark.parametrize(
    "package,prefix,size",
    [
        ("carculator_bus", "Bus", "13m-city"),
        ("carculator_truck", "Truck", "7.5t"),
    ],
)
def test_cng_correction_changes_fuel_input_at_fixed_mechanical_demand(
    package, prefix, size
):
    module = load_vehicle_package(package)
    inputs = getattr(module, prefix + "InputParameters")()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs,
        scope={"size": [size], "powertrain": ["ICEV-g", "ICEV-d"], "year": [2025]},
    )
    model = getattr(module, prefix + "Model")(array)
    model.set_all()
    model["CNG engine efficiency correction factor"] = 0
    model.calculate_ttw_energy()
    original = model.energy.copy(deep=True)
    original_total = model["TtW energy"].copy(deep=True)
    model["CNG engine efficiency correction factor"] = 0.2
    model.calculate_ttw_energy()
    for powertrain, fuel_ratio in [("ICEV-g", 1.25), ("ICEV-d", 1.0)]:
        np.testing.assert_allclose(
            model["TtW energy"].sel(powertrain=powertrain),
            original_total.sel(powertrain=powertrain) * fuel_ratio,
        )
        for parameter, ratio in [
            ("engine efficiency", 1 / fuel_ratio),
            ("motive energy", fuel_ratio),
            ("auxiliary energy", fuel_ratio),
            ("power load", 1),
        ]:
            selection = dict(powertrain=powertrain, parameter=parameter)
            np.testing.assert_allclose(
                model.energy.sel(**selection), original.sel(**selection) * ratio
            )


@pytest.mark.parametrize(
    "powertrain,input_energy,recovered,expected",
    [
        ("HEV-p", 2000, 100, -288),
        ("HEV-p", 4000, 100, -576),
        ("HEV-p", 2000, 10000, -2000),
        ("BEV", 2000, 100, -100),
        ("FCEV", 2000, 100, -200),
    ],
)
def test_regeneration_credit_uses_correct_energy_boundary(
    powertrain, input_energy, recovered, expected
):
    module = load_vehicle_package("carculator")
    inputs = module.CarInputParameters()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs, scope={"size": ["Medium"], "powertrain": [powertrain], "year": [2025]}
    )
    model = module.CarModel(array)
    model["combustion power share"] = 0.5 if powertrain == "HEV-p" else 0
    model["fuel cell system efficiency"] = 0.5 if powertrain == "FCEV" else 0
    # 500 kJ wheel work over 1 km; transmission .8 and electric motor .9.
    # Fuel saved = recovered DC * .9 * .8 / (500 / fuel input).
    model.energy = xr.DataArray(
        np.array([500, input_energy, -recovered, 0.8, 1000]).reshape(1, 1, 1, 1, 1, 5),
        dims=("second", "value", "year", "powertrain", "size", "parameter"),
        coords={
            "second": [0],
            "value": [0],
            "year": [2025],
            "powertrain": [powertrain],
            "size": ["Medium"],
            "parameter": [
                "motive energy at wheels",
                "motive energy",
                "recuperated energy",
                "transmission efficiency",
                "velocity",
            ],
        },
    )
    assert model.get_regeneration_credit().item() == pytest.approx(expected)


@pytest.mark.parametrize("powertrain", ["BEV", "PHEV-e"])
def test_short_electric_range_does_not_erase_consumption(powertrain):
    module = load_vehicle_package("carculator")
    inputs = module.CarInputParameters()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs, scope={"size": ["Medium"], "powertrain": [powertrain], "year": [2025]}
    )
    key = (powertrain, "Medium", 2025)
    kwargs = (
        {"target_range": {key: 60}}
        if powertrain == "BEV"
        else {"energy_storage": {"capacity": {key: 8}}}
    )
    model = module.CarModel(array, drop_hybrids=False, **kwargs)
    model.set_all()
    assert 0 < model["range"].item() < 100
    assert model["TtW energy"].item() > 0
    assert model["electricity consumption"].item() > 0


def test_truck_at_gross_mass_limit_remains_compliant():
    module = load_vehicle_package("carculator_truck")
    inputs = module.TruckInputParameters()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs, scope={"size": ["7.5t"], "powertrain": ["ICEV-d"], "year": [2025]}
    )
    model = module.TruckModel(array)
    model.set_all()
    model["driving mass"] = model["gross mass"]
    model.remove_energy_consumption_from_unavailable_vehicles()
    assert model["is_compliant"].item() == 1
    assert model["TtW energy"].item() > 0


def test_bus_capacity_override_survives_complete_sizing():
    module = load_vehicle_package("carculator_bus")
    inputs = module.BusInputParameters()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs,
        scope={"size": ["13m-city"], "powertrain": ["BEV-depot"], "year": [2025]},
    )
    storage = {"capacity": {("BEV-depot", "13m-city", 2025): 444}}
    model = module.BusModel(array, energy_storage=storage)
    model.set_all()
    assert model["electric energy stored"].item() == pytest.approx(444)
    assert model["battery cell mass"].item() == pytest.approx(
        444 / model["battery cell energy density"].item(), rel=1e-6
    )
    assert storage == {"capacity": {("BEV-depot", "13m-city", 2025): 444}}


def test_hybrid_component_peaks_need_not_sum_to_system_rating():
    module = load_vehicle_package("carculator")
    inputs = module.CarInputParameters()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs, scope={"size": ["Medium"], "powertrain": ["PHEV-c-p"], "year": [2025]}
    )
    model = module.CarModel(
        array.astype(float), power={("PHEV-c-p", "Medium", 2025): 164}
    )
    model["combustion power share"] = 112 / 164
    model["electric motor power share"] = 120 / 164
    model.set_power_parameters()
    assert model["power"].item() == pytest.approx(164)
    assert model["combustion power"].item() == pytest.approx(112)
    assert model["electric power"].item() == pytest.approx(120)
    model.set_recuperation()
    assert model["recuperation efficiency"].item() > 0


def test_native_hybrid_bus_has_electric_motor_and_recovers_energy():
    module = load_vehicle_package("carculator_bus")
    inputs = module.BusInputParameters()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs, scope={"size": ["13m-city"], "powertrain": ["HEV-d"], "year": [2025]}
    )
    model = module.BusModel(array)
    model.set_all()
    assert model["electric power"].item() > 0
    assert model.energy.sel(parameter="recuperated energy").sum() < 0
    assert model.regeneration_credit.item() < 0


@pytest.mark.parametrize("recovered_dc", [0, 100])
def test_stored_terminal_and_grid_battery_balance(recovered_dc):
    module = load_vehicle_package("carculator")
    inputs = module.CarInputParameters()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs, scope={"size": ["Medium"], "powertrain": ["BEV"], "year": [2025]}
    )
    model = module.CarModel(array.astype(float))
    model["battery discharge efficiency"] = 0.8
    model["battery charge efficiency"] = 0.9
    model["charger efficiency"] = 0.95
    model["charger mass"] = 10
    # One kilometre: deliver 800 kJ to the DC bus, receive R kJ at terminals.
    # Stored draw must be 1000 - .9 R, terminal draw 800 - R.
    reusable = recovered_dc * 0.9 * 0.8
    model["TtW energy"] = 800 - reusable
    model.energy = xr.DataArray(
        np.array([-reusable, 1000]).reshape(1, 1, 1, 1, 1, 2),
        dims=("second", "value", "year", "powertrain", "size", "parameter"),
        coords={
            "second": [0],
            "value": [0],
            "year": [2025],
            "powertrain": ["BEV"],
            "size": ["Medium"],
            "parameter": ["recuperated energy", "velocity"],
        },
    )
    model.set_battery_energy_balance()
    expected_stored = 1000 - 0.9 * recovered_dc
    assert model["TtW energy"].item() == pytest.approx(expected_stored)
    assert model.battery_terminal_energy.item() == pytest.approx(800 - recovered_dc)
    model["electric energy stored"] = 10
    model["battery DoD"] = 0.8
    model["fuel mass"] = 0
    model.set_range()
    assert model["range"].item() == pytest.approx(28800 / expected_stored)
    model.set_electricity_consumption()
    assert model["electricity consumption"].item() == pytest.approx(
        expected_stored / (0.9 * 0.95 * 3600)
    )


def test_battery_stored_energy_override_survives_complete_run():
    module = load_vehicle_package("carculator")
    inputs = module.CarInputParameters()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs, scope={"size": ["Medium"], "powertrain": ["BEV"], "year": [2025]}
    )
    model = module.CarModel(
        array.astype(float), energy_consumption={("BEV", "Medium", 2025): 720}
    )
    model.set_all()
    assert model["TtW energy"].item() == pytest.approx(720)


@pytest.mark.parametrize(
    "package,prefix,size,powertrain",
    [
        ("carculator", "Car", "Medium", "BEV"),
        ("carculator_bus", "Bus", "13m-city", "BEV-depot"),
        ("carculator_truck", "Truck", "7.5t", "BEV"),
        ("carculator_two_wheeler", "TwoWheeler", "Moped <4kW", "BEV"),
    ],
)
def test_native_component_efficiencies_have_separate_boundaries(
    package, prefix, size, powertrain
):
    module = load_vehicle_package(package)
    inputs = getattr(module, prefix + "InputParameters")()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs, scope={"size": [size], "powertrain": [powertrain], "year": [2025]}
    )
    model = getattr(module, prefix + "Model")(array.astype(float))
    model.set_all()
    np.testing.assert_allclose(model.energy.sel(parameter="engine efficiency"), 0.9)
    np.testing.assert_allclose(
        model.energy.sel(parameter="transmission efficiency"), 0.97
    )
    assert (
        model["battery charge efficiency"] * model["battery discharge efficiency"]
    ).item() == pytest.approx(0.97)
    assert model["charger efficiency"].item() == pytest.approx(0.90)
    assert model["electricity consumption"].item() == pytest.approx(
        model["TtW energy"].item() / (np.sqrt(0.97) * 0.9 * 3600)
    )


def test_bus_peak_occupancy_assumption_does_not_erase_valid_consumption():
    module = load_vehicle_package("carculator_bus")
    inputs = module.BusInputParameters()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs,
        scope={"size": ["13m-city"], "powertrain": ["BEV-depot"], "year": [2025]},
    )
    model = module.BusModel(array.astype(float))
    model["TtW energy"] = 3600
    model["electricity consumption"] = 1.2
    model["fuel consumption"] = 0
    model["curb mass"] = 14000
    model["driving mass"] = 18000
    model["gross mass"] = 18000
    model["average passengers"] = 40
    model["average passenger mass"] = 100
    model.remove_energy_consumption_from_unavailable_vehicles()
    assert not model.peak_passenger_capacity_sufficient.item()
    assert model["is_compliant"].item() == 1
    assert model["TtW energy"].item() == 3600
    assert model["electricity consumption"].item() == 1.2
    model["driving mass"] = 18001
    model.remove_energy_consumption_from_unavailable_vehicles()
    assert model["is_compliant"].item() == 0
    assert model["TtW energy"].item() == 0
    assert model["electricity consumption"].item() == 0


@pytest.mark.parametrize(
    "package,prefix,size,powertrain",
    [
        ("carculator", "Car", "Medium", "BEV"),
        ("carculator_truck", "Truck", "7.5t", "BEV"),
        ("carculator_two_wheeler", "TwoWheeler", "Moped <4kW", "BEV"),
    ],
)
@pytest.mark.parametrize(
    "kwargs", [{"ambient_temperature": -5}, {"indoor_temperature": 25}]
)
def test_unsupported_temperature_is_not_silently_ignored(
    package, prefix, size, powertrain, kwargs
):
    module = load_vehicle_package(package)
    inputs = getattr(module, prefix + "InputParameters")()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs, scope={"size": [size], "powertrain": [powertrain], "year": [2025]}
    )
    with pytest.raises(ValueError, match="supported only by bus HVAC"):
        getattr(module, prefix + "Model")(array, **kwargs)


@pytest.mark.parametrize("temperature", [np.nan, np.inf, -273.15, [20, 21]])
def test_bus_rejects_invalid_temperature_before_calculation(temperature):
    module = load_vehicle_package("carculator_bus")
    inputs = module.BusInputParameters()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs,
        scope={"size": ["13m-city"], "powertrain": ["BEV-depot"], "year": [2025]},
    )
    with pytest.raises(ValueError, match="Ambient temperature"):
        module.BusModel(array, ambient_temperature=temperature)


def test_unavailable_historical_bus_does_not_block_active_bus_sizing():
    module = load_vehicle_package("carculator_bus")
    inputs = module.BusInputParameters()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs,
        scope={
            "size": ["13m-coach"],
            "powertrain": ["BEV-depot"],
            "year": [2000, 2025],
        },
    )
    model = module.BusModel(array.astype(float), max_iterations=20)
    model.set_all()
    assert model["is_available"].sel(year=2000).item() == 0
    assert model["TtW energy"].sel(year=2000).item() == 0
    assert model["electricity consumption"].sel(year=2000).item() == 0
    assert model["is_available"].sel(year=2025).item() == 1
    assert model["TtW energy"].sel(year=2025).item() > 0
    assert model["driving mass"].sel(year=2025).item() < 30000


@pytest.mark.parametrize(
    "package,prefix,size,powertrain",
    [
        ("carculator", "Car", "Medium", "BEV"),
        ("carculator_bus", "Bus", "13m-city", "BEV-depot"),
        ("carculator_truck", "Truck", "7.5t", "BEV"),
        ("carculator_two_wheeler", "TwoWheeler", "Bicycle <25", "BEV"),
    ],
)
def test_historical_availability_masks_all_reported_energy(
    package, prefix, size, powertrain
):
    module = load_vehicle_package(package)
    inputs = getattr(module, prefix + "InputParameters")()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs,
        scope={"size": [size], "powertrain": [powertrain], "year": [2010, 2025]},
    )
    model = getattr(module, prefix + "Model")(array)
    model.set_all()
    for parameter in ["TtW energy", "electricity consumption", "fuel consumption"]:
        assert (model[parameter].sel(year=2010) == 0).all()
    assert (model.battery_terminal_energy.sel(year=2010) == 0).all()
    assert (model["TtW energy"].sel(year=2025) > 0).all()
    assert (model["electricity consumption"].sel(year=2025) > 0).all()
    # Zero net stored energy is not an availability policy: a valid vehicle
    # can recover enough terminal energy to offset its battery losses.
    model.array.loc[dict(parameter="TtW energy", year=2025)] = 0
    model.battery_terminal_energy.loc[dict(year=2025)] = -1
    model.remove_energy_consumption_from_unavailable_vehicles()
    assert (model.battery_terminal_energy.sel(year=2025) == -1).all()


@pytest.mark.parametrize(
    "package,prefix,size,powertrain,overweight",
    [
        ("carculator", "Car", "Micro", "ICEV-p", False),
        ("carculator_two_wheeler", "TwoWheeler", "Moped <4kW", "BEV", False),
        ("carculator_truck", "Truck", "7.5t", "ICEV-d", True),
        ("carculator_bus", "Bus", "13m-city", "ICEV-d", True),
    ],
)
def test_unavailable_or_overweight_policy_clears_stale_supply_outputs(
    package, prefix, size, powertrain, overweight
):
    module = load_vehicle_package(package)
    inputs = getattr(module, prefix + "InputParameters")()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs, scope={"size": [size], "powertrain": [powertrain], "year": [2025]}
    )
    model = getattr(module, prefix + "Model")(array)
    reported = {
        "TtW energy": 1000,
        "TtW energy, combustion mode": 1000,
        "TtW energy, electric mode": 1000,
        "auxiliary energy": 10,
        "electricity consumption": 0.2,
        "fuel consumption": 0.05,
    }
    for parameter, value in reported.items():
        if parameter in model.array.parameter.values:
            model[parameter] = value
    model.battery_terminal_energy = xr.ones_like(model["TtW energy"])
    if overweight:
        model["driving mass"] = 20000
        model["gross mass"] = 18000
        model["is_compliant"] = 1
        model["is_available"] = 1
    model.remove_energy_consumption_from_unavailable_vehicles()
    for parameter in reported:
        if parameter in model.array.parameter.values:
            assert (model[parameter] == 0).all(), parameter
    assert (model.battery_terminal_energy == 0).all()
    if overweight:
        assert (model["driving mass"] == 20000).all()
