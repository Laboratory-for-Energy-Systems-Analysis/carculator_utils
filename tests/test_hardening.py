from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.model import VehicleModel
from carculator_utils.vehicle_input_parameters import VehicleInputParameters


def inputs():
    return VehicleInputParameters(
        {
            "mass": {
                "name": "mass",
                "amount": 10.0,
                "kind": "distribution",
                "uncertainty_type": 1,
                "sizes": ["Small"],
                "powertrain": ["BEV"],
                "year": 2020,
            },
            "efficiency": {
                "name": "efficiency",
                "amount": 0.8,
                "kind": "distribution",
                "uncertainty_type": 1,
                "sizes": ["Small"],
                "powertrain": ["BEV"],
                "year": 2020,
            },
        },
        extra=["derived"],
    )


def test_sensitivity_reference_and_one_at_a_time_perturbations():
    ip = inputs()
    ip.static()
    _, static = fill_xarray_from_input_parameters(ip)
    _, result = fill_xarray_from_input_parameters(ip, sensitivity=True)
    xr.testing.assert_allclose(
        result.sel(value="reference", drop=True), static.sel(value=0, drop=True)
    )
    assert result.value.values.tolist() == ["reference", "efficiency", "mass"]
    for parameter in ["efficiency", "mass"]:
        expected = static.sel(value=0, drop=True).copy(deep=True)
        expected.loc[dict(parameter=parameter)] *= 1.1
        xr.testing.assert_allclose(result.sel(value=parameter, drop=True), expected)


def test_scope_is_not_mutated_and_mappings_follow_coordinates():
    ip = inputs()
    ip.static()
    scope = {"powertrain": ["BEV"]}
    original = deepcopy(scope)
    mappings, result = fill_xarray_from_input_parameters(ip, scope=scope)
    assert scope == original
    for mapping, dim in zip(mappings, ["size", "powertrain", "parameter", "year"]):
        assert mapping == {v: i for i, v in enumerate(result[dim].values.tolist())}


def battery_model(missing=()):
    generic = [
        "battery cell energy density",
        "battery cell mass share",
        "battery cycle life",
        "energy battery cost per kWh",
    ]
    chemistry = [p + ", NMC-622" for p in generic[:3] if p not in missing]
    values = [0.0, 0.0, 0.0, 125.0] + [
        v for p, v in zip(generic, [0.2, 0.7, 2000.0]) if p not in missing
    ]
    model = VehicleModel.__new__(VehicleModel)
    model.array = xr.DataArray(
        np.array(values).reshape(1, 1, -1, 1, 1),
        dims=("size", "powertrain", "parameter", "year", "value"),
        coords={
            "size": ["Small"],
            "powertrain": ["BEV"],
            "parameter": generic + chemistry,
            "year": [2020],
            "value": [0],
        },
    )
    model.energy_storage = {"electric": {("BEV", "Small", 2020): "NMC-622"}}
    return model


def test_missing_chemistry_cost_does_not_skip_physical_properties():
    model = battery_model()
    model.set_battery_preferences()
    assert float(model["battery cell energy density"].item()) == 0.2
    assert float(model["battery cell mass share"].item()) == 0.7
    assert float(model["battery cycle life"].item()) == 2000.0
    assert float(model["energy battery cost per kWh"].item()) == 125.0


def test_missing_required_chemistry_property_has_context():
    model = battery_model(missing=("battery cell energy density",))
    with pytest.raises(ValueError, match="battery cell energy density.*NMC-622"):
        model.set_battery_preferences()


def test_nested_selection_restores_outer_scope_after_exception():
    model = battery_model()
    original = model.array.copy(deep=True)
    with model("BEV"):
        outer = model.array.copy(deep=True)
        with pytest.raises(RuntimeError):
            with model("BEV"):
                raise RuntimeError("example")
        xr.testing.assert_identical(model.array, outer)
    xr.testing.assert_identical(model.array, original)


def test_input_extra_rejects_json_string_content(tmp_path):
    path = tmp_path / "extra.json"
    path.write_text('"accidental string"')
    with pytest.raises(ValueError, match="extra"):
        VehicleInputParameters({}, extra=path)


def test_sample_specific_load_factors_and_export_do_not_mutate_inventory(monkeypatch):
    import carculator_utils.export
    from carculator_utils.inventory import Inventory, format_array

    model = SimpleNamespace(
        vehicle_type="car",
        array=xr.DataArray(
            np.array([[[[[1.0, 1.0]], [[2.0, 4.0]]]]]),
            dims=("size", "powertrain", "parameter", "year", "value"),
            coords={
                "size": ["Small"],
                "powertrain": ["BEV"],
                "parameter": ["TtW energy", "average passengers"],
                "year": [2020],
                "value": [0, 1],
            },
        ),
    )
    inventory = Inventory.__new__(Inventory)
    inventory.vm = model
    inventory.array = format_array(model.array)
    inventory.scope = {"size": ["Small"], "powertrain": ["BEV"], "year": [2020]}
    inventory.func_unit = "pkm"
    inventory.iterations = 2
    inventory.inputs = {
        ("input", "CH", "unit", "product"): 0,
        ("transport, car, test", "CH", "vkm", "transport"): 1,
    }
    inventory.rev_inputs = {v: k for k, v in inventory.inputs.items()}
    inventory.find_input_indices = lambda *args: [1]
    inventory.A = np.repeat(np.eye(2)[None, :, :, None], 2, axis=0)
    inventory.A[:, 0, 1, 0] = -8.0
    before = inventory.A.copy()
    labels = inventory.inputs.copy()
    captured = []

    class Export:
        def __init__(self, array, indices, **kwargs):
            captured.append((array.copy(), indices.copy()))

        def write_bw2_lci(self, **kwargs):
            return "export"

    monkeypatch.setattr(carculator_utils.export, "ExportInventory", Export)
    for _ in range(2):
        assert inventory.export_lci(format="file") == "export"
    np.testing.assert_array_equal(inventory.A, before)
    assert inventory.inputs == labels
    np.testing.assert_array_equal(captured[0][0], captured[1][0])
    np.testing.assert_array_equal(captured[0][0][:, 0, 1, 0], [-4.0, -2.0])
    assert captured[0][1][1][2] == "passenger kilometer"
    model.array.loc[dict(parameter="average passengers")] = 0
    with pytest.raises(ValueError, match="positive average passengers"):
        inventory.get_load_factor()


def test_real_noise_model_is_finite_at_stops():
    from carculator_utils.noise_emissions import NoiseEmissionsModel

    velocity = xr.DataArray(
        np.array([0.0, 10.0, 0.0]).reshape(3, 1, 1, 1, 1),
        dims=("second", "value", "year", "powertrain", "size"),
        coords={
            "second": [0, 1, 2],
            "value": [0],
            "year": [2020],
            "powertrain": ["BEV"],
            "size": ["Small"],
        },
    )
    model = NoiseEmissionsModel(velocity, "car")
    with np.errstate(over="raise", invalid="raise"):
        result = model.get_sound_power_per_compartment()
    assert np.all(np.isfinite(result))


def test_convergence_checks_each_cell_and_handles_decreasing_values():
    from carculator_utils.numerical import iterate_until_converged

    state = np.array([100.0, 100.0])
    count = 0
    for step in iterate_until_converged(lambda: state, label="mass", rtol=0.001):
        count += 1
        if step == 1:
            state[:] = [90.0, 110.0]  # unchanged sum does not mean converged
    assert count == 2


def test_convergence_failure_is_bounded_and_identifies_state():
    from carculator_utils.numerical import ConvergenceError, iterate_until_converged

    state = np.array([1.0])
    with pytest.raises(ConvergenceError, match="iteration limit.*3"):
        for _ in iterate_until_converged(
            lambda: state, label="payload", max_iterations=3
        ):
            state *= 2
    with pytest.raises(ConvergenceError, match="non-finite"):
        for _ in iterate_until_converged(lambda: state, label="mass"):
            state[:] = np.nan


def test_convergence_error_reports_string_coordinates():
    from carculator_utils.numerical import ConvergenceError, iterate_until_converged

    state = xr.DataArray([1.0], dims="size", coords={"size": ["3.5t"]})
    with pytest.raises(ConvergenceError, match="3.5t"):
        for _ in iterate_until_converged(
            lambda: state, label="payload", max_iterations=2
        ):
            state[:] *= 2


def test_seeded_sampling_is_reproducible_and_does_not_use_global_rng():
    ip = inputs()
    ip.data["mass"].update(uncertainty_type=4, minimum=5.0, maximum=15.0)
    before = np.random.get_state()
    ip.stochastic(8, seed=42)
    first = ip.values["mass"].copy()
    _, array = fill_xarray_from_input_parameters(ip)
    assert array.sizes["value"] == 8
    np.testing.assert_array_equal(
        array.sel(parameter="mass").values.ravel(), first.astype("float32")
    )
    ip.stochastic(8, seed=42)
    np.testing.assert_array_equal(first, ip.values["mass"])
    ip.stochastic(8, seed=43)
    assert not np.array_equal(first, ip.values["mass"])
    after = np.random.get_state()
    assert before[0] == after[0]
    np.testing.assert_array_equal(before[1], after[1])
    assert before[2:] == after[2:]


@pytest.mark.parametrize("count", [0, -1, True, 1.5])
def test_invalid_sample_counts_are_rejected(count):
    with pytest.raises(ValueError, match="positive integer"):
        inputs().stochastic(count)


@pytest.mark.parametrize("arguments", [{"method": "unknown"}, {"indicator": "endpint"}])
def test_inventory_rejects_invalid_method_before_using_model(arguments):
    from carculator_utils.inventory import Inventory

    with pytest.raises(ValueError, match="method|indicator"):
        Inventory(None, **arguments)
