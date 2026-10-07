"""Temporal assumptions: anchor preservation, physical bounds and uncertainty."""

import importlib
import importlib.util
import json
import os

import numpy as np
import pytest

from carculator_utils.vehicle_input_parameters import VehicleInputParameters

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


def test_shared_temporal_uncertainty():
    records = {
        str(y): dict(
            name="auxiliary power",
            sizes=["bus"],
            powertrain=["BEV"],
            year=y,
            amount=8300,
            loc=8300,
            minimum=6225,
            maximum=10375,
            uncertainty_type=5,
            kind="distribution",
            uncertainty_group="transfer",
        )
        for y in (2020, 2025, 2030)
    }
    inputs = VehicleInputParameters(records, extra=[])
    state = np.random.get_state()
    inputs.stochastic(100, seed=72)
    for key in ("2025", "2030"):
        np.testing.assert_array_equal(inputs.values[key], inputs.values["2020"])
    assert np.ptp(inputs.values["2020"]) > 0
    assert np.all((inputs.values["2020"] >= 6225) & (inputs.values["2020"] <= 10375))
    reference = inputs.values["2020"].copy()
    inputs.stochastic(100, seed=72)
    np.testing.assert_array_equal(inputs.values["2020"], reference)
    for a, b in zip(state, np.random.get_state()):
        np.testing.assert_array_equal(a, b)
    records["2030"]["loc"] = 8400
    with pytest.raises(ValueError, match="identical distributions"):
        VehicleInputParameters(records, extra=[]).stochastic(2, seed=72)


@pytest.mark.family
@pytest.mark.parametrize("package,prefix", FAMILIES)
def test_temporal_energy_preserves_anchors_and_physical_bounds(package, prefix):
    module = load_vehicle_package(package)
    cls = getattr(module, prefix + "InputParameters")
    records = json.loads(cls.DEFAULT.read_text())
    manifest = json.loads(
        (cls.DEFAULT.parent / "temporal_energy_provenance.json").read_text()
    )
    originals = manifest["original_records"]
    for key, detail in manifest["records"].items():
        record = records[key]
        anchor = records[detail["anchor_record"]]
        assert record["year"] != 2025
        if "efficiency" in record["name"]:
            assert 0 < record["amount"] <= 1
        if record["name"] == "auxiliary power base demand":
            assert record["amount"] == 8300
            assert record["minimum"] == 6225
            assert record["maximum"] == 10375
            assert record["uncertainty_group"] == anchor["uncertainty_group"]
    for key, original in originals.items():
        if original["year"] == 2025:
            assert {
                k: v for k, v in records[key].items() if k != "uncertainty_group"
            } == original
    inputs = cls()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(inputs)
    annual = array.interp(year=np.arange(2020, 2031))
    for parameter, value in [
        ("electric motor efficiency", 0.9),
        ("electric transmission efficiency", 0.97),
    ]:
        np.testing.assert_allclose(annual.sel(parameter=parameter), value, rtol=1e-6)
    # The bus calibration is one uncertain assumption, not independent year noise.
    if package == "carculator_bus":
        inputs.stochastic(8, seed=2025)
        _, draws = module.fill_xarray_from_input_parameters(
            inputs,
            scope={
                "size": ["13m-city"],
                "powertrain": ["BEV-depot"],
                "year": [2020, 2025, 2030],
            },
        )
        data = draws.sel(parameter="auxiliary power base demand").values
        np.testing.assert_array_equal(data[..., 0, :], data[..., 1, :])
        np.testing.assert_array_equal(data[..., 1, :], data[..., 2, :])


@pytest.mark.family
@pytest.mark.parametrize(
    "package,prefix,size,powertrain",
    [
        ("carculator", "Car", "Lower medium", "BEV"),
        ("carculator_bus", "Bus", "13m-city", "BEV-depot"),
        ("carculator_truck", "Truck", "40t", "BEV"),
        ("carculator_two_wheeler", "TwoWheeler", "Scooter <4kW", "BEV"),
    ],
)
def test_full_models_have_no_isolated_2025_energy_step(
    package, prefix, size, powertrain
):
    module = load_vehicle_package(package)
    inputs = getattr(module, prefix + "InputParameters")()
    inputs.static()
    _, native = module.fill_xarray_from_input_parameters(
        inputs,
        scope={"size": [size], "powertrain": [powertrain], "year": [2020, 2025, 2030]},
    )
    annual = native.astype(float).interp(year=[2024, 2025, 2026])
    model = getattr(module, prefix + "Model")(annual)
    model.set_all()
    energy = model["TtW energy"].values.flatten()
    assert np.isfinite(energy).all() and (energy > 0).all()
    # Guard against the former 2025-only component-definition switch. This is a
    # regression envelope for these fixed cases, not a universal technology rule.
    assert np.max(np.abs(np.diff(energy) / energy[:-1])) < 0.05
