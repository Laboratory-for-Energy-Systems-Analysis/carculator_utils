"""Cost draws belong to input samples, independently of model execution order."""

from copy import deepcopy

import numpy as np
import pytest
import stats_arrays as sa
import xarray as xr

from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.cost_uncertainty import (
    DISTRIBUTIONS,
    FCEV_FACTOR,
    GENERAL_FACTOR,
    attach_cost_factors,
    sample_cost_factors,
)
from carculator_utils.model import VehicleModel
from carculator_utils.vehicle_input_parameters import VehicleInputParameters

ENERGY = "energy battery cost per kWh"


def inputs():
    return VehicleInputParameters(
        {
            str(year): dict(
                name=ENERGY,
                amount=100,
                loc=100,
                minimum=80,
                maximum=120,
                uncertainty_type=5,
                sizes=["Medium"],
                powertrain=["BEV"],
                year=year,
            )
            for year in (2020, 2030)
        },
        extra=[],
    )


def build(ip, **kwargs):
    return fill_xarray_from_input_parameters(ip, **kwargs)[1]


def project(array):
    # A partial model suffices to isolate the projected-price contract.
    model = VehicleModel.__new__(VehicleModel)
    model.array = array.copy(deep=True)
    model.adjust_cost()
    return model


def assert_rng_equal(before, after):
    assert before[0] == after[0]
    np.testing.assert_array_equal(before[1], after[1])
    assert before[2:] == after[2:]


@pytest.mark.parametrize("seed", [0, 42, np.int64(17), [1, 2, 3]])
def test_seed_reproduces_cost_draws_without_changing_parameter_draws_or_global_rng(
    seed,
):
    ip = inputs()
    state = np.random.get_state()
    ip.stochastic(4, seed=seed)
    array = build(ip)
    result = project(array).array
    assert_rng_equal(state, np.random.get_state())

    # The existing stats_arrays parameter stream must remain byte-for-byte
    # equivalent; projected prices use separate streams.
    parameters = sa.UncertaintyBase.from_dicts(*[ip.data[k] for k in sorted(ip.data)])
    expected = sa.MCRandomNumberGenerator(parameters, seed=seed).generate(4)
    for key, row in zip(sorted(ip.data), expected):
        np.testing.assert_array_equal(ip.values[key], row)

    other = inputs()
    try:
        np.random.random(31)
        other.stochastic(4, seed=seed)
        xr.testing.assert_identical(array, build(other))
        xr.testing.assert_identical(result, project(build(other)).array)
    finally:
        np.random.set_state(state)


def test_cost_streams_are_distinct_bounded_and_stable_when_sample_count_changes():
    small = sample_cost_factors(4, seed=42)
    large = sample_cost_factors(20000, seed=42)
    other = sample_cost_factors(4, seed=43)
    for name, (lower, mode, upper) in DISTRIBUTIONS.items():
        np.testing.assert_array_equal(small[name], large[name][:4])
        assert not np.array_equal(small[name], other[name])
        assert ((large[name] >= lower) & (large[name] <= upper)).all()
        # Independent moments of a triangular distribution, not an RNG snapshot.
        mean = (lower + mode + upper) / 3
        variance = (
            lower**2 + mode**2 + upper**2 - lower * mode - lower * upper - mode * upper
        ) / 18
        assert abs(large[name].mean() - mean) < 5 * np.sqrt(variance / 20000)
        assert large[name].var() == pytest.approx(variance, rel=0.04)
    assert abs(np.corrcoef(*large.values())[0, 1]) < 0.04


def test_unseeded_draws_are_reused_until_inputs_are_resampled():
    ip = inputs()
    ip.stochastic(4)
    original = build(ip)
    xr.testing.assert_identical(original, build(ip))
    xr.testing.assert_identical(project(original).array, project(original).array)
    ip.stochastic(4)
    assert not np.array_equal(original[GENERAL_FACTOR], build(ip)[GENERAL_FACTOR])


def test_factors_survive_scoping_interpolation_reordering_transpose_and_netcdf(
    tmp_path,
):
    ip = inputs()
    ip.stochastic(4, seed=42)
    full = build(ip)
    scoped = build(ip, scope={"year": [2030]})
    xr.testing.assert_identical(full.sel(year=[2030]), scoped)
    expected = project(full).array
    # In particular, a single retained sample is not a deterministic calculation.
    for samples in ([3, 1], [2]):
        array = full.interp(year=[2020, 2025, 2030]).sel(value=samples)
        array = array.transpose("value", "year", "parameter", "powertrain", "size")
        path = tmp_path / "samples.nc"
        array.to_netcdf(path)
        restored = xr.load_dataarray(path)
        xr.testing.assert_identical(array, restored)
        result = project(restored).array.transpose(*full.dims)
        xr.testing.assert_allclose(
            result.sel(year=[2020, 2030]), expected.sel(value=samples)
        )
        prices = result.sel(year=2025, parameter=ENERGY).values.ravel()
        np.testing.assert_allclose(
            prices,
            (2.75e86 * np.exp(-0.0961 * 2025) + 50.59)
            * full[GENERAL_FACTOR].sel(value=samples),
            rtol=1e-6,
        )
    # Auxiliary coordinates are copied; building/editing an array cannot change
    # the remembered factors on the input-parameter object.
    reference = deepcopy(ip._cost_factors)
    full.coords[GENERAL_FACTOR].values[:] = 1
    for name in DISTRIBUTIONS:
        np.testing.assert_array_equal(ip._cost_factors[name], reference[name])


def test_static_and_sensitivity_reset_sampled_factors_even_without_reference_sample():
    ip = inputs()
    ip.stochastic(3, seed=42)
    ip.static()
    static = build(ip)
    sensitivity = build(ip, sensitivity=True).sel(value=[ENERGY])
    for name, (_, mode, _) in DISTRIBUTIONS.items():
        assert (static[name] == mode).all()
        assert (sensitivity[name] == mode).all()
    for array in (static, sensitivity):
        result = project(array).array.sel(parameter=ENERGY)
        expected = 2.75e86 * np.exp(-0.0961 * result.year.values) + 50.59
        np.testing.assert_allclose(result.values.ravel(), expected, rtol=1e-6)


def test_single_stochastic_draw_has_uncertainty_and_matches_first_cost_draw():
    ip = inputs()
    ip.stochastic(1, seed=42)
    array = build(ip)
    ip.stochastic(3, seed=42)
    for name in DISTRIBUTIONS:
        xr.testing.assert_identical(array[name], build(ip)[name].sel(value=[0]))
    assert array[GENERAL_FACTOR].item() != 1


@pytest.mark.parametrize("mode", ["static", "sensitivity", "sampled"])
def test_legacy_array_uses_local_fallback_once_without_mutating_caller(mode):
    ip = inputs()
    ip.static() if mode != "sampled" else ip.stochastic(3, seed=42)
    array = build(ip, sensitivity=mode == "sensitivity").reset_coords(drop=True)
    original = array.copy(deep=True)
    state = np.random.get_state()
    model = project(array)
    once = model.array.copy(deep=True)
    model.adjust_cost()
    xr.testing.assert_identical(model.array, once)
    xr.testing.assert_identical(array, original)
    assert_rng_equal(state, np.random.get_state())
    if mode != "sampled":
        assert (model.array[GENERAL_FACTOR] == 1).all()
        assert (model.array[FCEV_FACTOR] == 5).all()


@pytest.mark.parametrize("bad", [np.nan, np.inf, 0, 2, "bad", 1j])
def test_invalid_retained_factor_fails_clearly(bad):
    ip = inputs()
    ip.static()
    array = build(ip).assign_coords({GENERAL_FACTOR: ("value", [bad])})
    with pytest.raises(ValueError, match="Cost-factor coordinate.*finite"):
        attach_cost_factors(array)


def test_missing_or_misaligned_factor_is_not_silently_resampled():
    ip = inputs()
    ip.static()
    array = build(ip)
    with pytest.raises(ValueError, match="Missing cost-factor coordinate"):
        attach_cost_factors(array.drop_vars(FCEV_FACTOR))
    with pytest.raises(ValueError, match="must have dimension 'value'"):
        attach_cost_factors(array.assign_coords({FCEV_FACTOR: 5}))
