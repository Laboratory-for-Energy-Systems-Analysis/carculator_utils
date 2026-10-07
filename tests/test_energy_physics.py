"""Energy-balance regressions independent of empirical vehicle consumption."""

import numpy as np
import pytest
import xarray as xr

from carculator_utils.energy_consumption import (
    EnergyConsumptionModel,
    get_efficiency_coefficients,
)


def scalar(value):
    return xr.DataArray(
        np.full((1, 1, 1, 1), value, dtype=float),
        dims=("size", "powertrain", "year", "value"),
    )


def calculate(
    speed=None,
    eta=0.25,
    transmission=1.0,
    maps=None,
    gradient=None,
    powertrain="ICEV-p",
    **overrides,
):
    speed = np.full(6, 100.0) if speed is None else np.asarray(speed, dtype=float)
    model = EnergyConsumptionModel("car", ["Medium"], [powertrain], speed, gradient)
    model.efficiency_coefficients = maps
    parameters = dict(
        driving_mass=1500,
        rr_coef=0.01,
        drag_coef=0.3,
        frontal_area=2.2,
        electric_motor_power=0,
        engine_power=20,
        recuperation_efficiency=0,
        aux_power=0,
        battery_charge_eff=1,
        battery_discharge_eff=1,
    )
    parameters.update(overrides)
    args = {name: scalar(value) for name, value in parameters.items()}
    if eta is not None:
        args["engine_efficiency"] = (
            eta if np.ma.isMaskedArray(eta) else np.full_like(model.velocity, eta)
        )
    if transmission is not None:
        args["transmission_efficiency"] = np.full_like(model.velocity, transmission)
    return model, model.motive_energy_per_km(**args).squeeze(drop=True)


def wheel_power_kw():
    speed = 100 / 3.6
    return (1500 * 9.81 * 0.01 + 0.5 * 1.204 * 0.3 * 2.2 * speed**2) * speed / 1000


def test_fuel_input_may_exceed_rated_shaft_power():
    model, result = calculate()
    np.testing.assert_allclose(
        result.sel(parameter="motive energy"), wheel_power_kw() / 0.25
    )
    assert (model.power_deficit_kw == 0).all()


def test_infeasible_trace_reports_deficit_without_erasing_energy():
    model, result = calculate(engine_power=5)
    np.testing.assert_allclose(model.power_deficit_kw, wheel_power_kw() - 5)
    np.testing.assert_allclose(
        result.sel(parameter="motive energy"), wheel_power_kw() / 0.25
    )


@pytest.mark.parametrize("eta", [0.2, 0.4, 0.9])
def test_engine_load_uses_mechanical_output_not_fuel_input(eta):
    _, result = calculate(eta=eta, transmission=0.8)
    np.testing.assert_allclose(
        result.sel(parameter="power load"),
        wheel_power_kw() / (0.8 * 20),
    )


def test_disabled_regeneration_does_not_recover_braking_energy():
    _, result = calculate(
        speed=[36, 36, 18, 0, 0],
        rr_coef=0,
        drag_coef=0,
        electric_motor_power=100,
        recuperation_efficiency=0,
        eta=1,
    )
    assert result.sel(parameter="negative motive energy").sum() < 0
    assert (result.sel(parameter="recuperated energy") == 0).all()


@pytest.mark.parametrize("mass", [np.nan, np.inf, -1])
def test_invalid_mass_is_rejected(mass):
    with pytest.raises(ValueError, match="Driving mass"):
        calculate(driving_mass=mass)


def test_explicit_efficiency_overrides_take_precedence_over_maps():
    maps = {"gasoline": {"engine": {0: 0.8, 1: 0.8}, "transmission": {0: 0.6, 1: 0.6}}}
    _, result = calculate(eta=0.25, transmission=0.9, maps=maps)
    np.testing.assert_allclose(
        result.sel(parameter="motive energy"), wheel_power_kw() / (0.25 * 0.9)
    )


@pytest.mark.parametrize("eta,expected", [(None, 0.2), (0.4, 0.4)])
def test_map_correction_preserves_shaft_work_and_corrects_all_fuel_input(eta, expected):
    maps = {"gasoline": {"engine": {0: 0.25, 1: 0.25}}}
    _, result = calculate(
        eta=eta, maps=maps, engine_efficiency_factor=0.8, aux_power=1000
    )
    np.testing.assert_allclose(result.sel(parameter="engine efficiency"), expected)
    np.testing.assert_allclose(
        result.sel(parameter="motive energy"), wheel_power_kw() / expected
    )
    np.testing.assert_allclose(result.sel(parameter="auxiliary energy"), 1 / expected)
    np.testing.assert_allclose(
        result.sel(parameter="power load"), (wheel_power_kw() + 1) / 20
    )


@pytest.mark.parametrize("factor", [0, -0.1, 1.1, np.nan, np.inf])
def test_invalid_engine_map_correction_is_rejected(factor):
    with pytest.raises(ValueError, match="Engine efficiency factor"):
        calculate(engine_efficiency_factor=factor)


def test_load_dependent_transmission_converges_to_analytical_root():
    # eta_transmission = .8 + .1 * load; load * eta_transmission = P_wheel / P_rated.
    maps = {
        "gasoline": {"engine": {0: 0.25, 1: 0.25}, "transmission": {0: 0.8, 1: 0.9}}
    }
    model, result = calculate(eta=None, transmission=None, maps=maps)
    expected_load = (-0.8 + np.sqrt(0.8**2 + 0.4 * wheel_power_kw() / 20)) / 0.2
    np.testing.assert_allclose(
        result.sel(parameter="power load"),
        expected_load,
        rtol=1e-8,
    )
    assert model.efficiency_iterations < 100


@pytest.mark.parametrize("wheel_load", [0.04, 0.16, 0.32])
@pytest.mark.parametrize(
    "powertrain,coefficients",
    [("ICEV-p", (0.1181, 2.1153, 3.9871)), ("ICEV-d", (0.0544, 1.5247, 5.2731))],
)
def test_split_car_map_reproduces_published_wheel_efficiency(
    wheel_load, powertrain, coefficients
):
    a, b, c = coefficients  # Hjelkrem et al., Table 4, Willans approximation.
    ttw_efficiency = wheel_load / (a + b * wheel_load + c * wheel_load**2)
    _, result = calculate(
        eta=None,
        transmission=None,
        maps=get_efficiency_coefficients("car"),
        powertrain=powertrain,
        engine_power=wheel_power_kw() / wheel_load,
    )
    np.testing.assert_allclose(
        result.sel(parameter="motive energy"), wheel_power_kw() / ttw_efficiency
    )
    np.testing.assert_allclose(result.sel(parameter="power load"), wheel_load / 0.8)
    np.testing.assert_allclose(
        result.sel(parameter="engine efficiency"), ttw_efficiency / 0.8
    )


def test_split_map_keeps_auxiliary_demand_at_stationary_samples():
    _, result = calculate(
        speed=[0, 0, 36, 36, 0, 0],
        eta=None,
        transmission=None,
        maps=get_efficiency_coefficients("car"),
        aux_power=1250,
        engine_power=100,
    )
    # 1.25 kW at the shaft corresponds to 1 kW at the reference wheels:
    # utility .01; eta_TTW=.01/(a+b*.01+c*.01**2).
    eta = (0.01 / (0.1181 + 2.1153 * 0.01 + 3.9871 * 0.01**2)) / 0.8
    np.testing.assert_allclose(
        result.sel(parameter="auxiliary energy")[[0, 1, 5]], 1.25 / eta
    )


def test_transmission_override_does_not_redefine_the_reference_engine_map():
    _, result = calculate(
        eta=None,
        transmission=0.9,
        maps=get_efficiency_coefficients("car"),
        engine_power=wheel_power_kw() / 0.09,
    )
    # Shaft load .1 corresponds to source-map utilization .08 even when the
    # actual transmission is .9: its reference split remains .8.
    eta = (0.08 / (0.1181 + 2.1153 * 0.08 + 3.9871 * 0.08**2)) / 0.8
    np.testing.assert_allclose(result.sel(parameter="engine efficiency"), eta)
    np.testing.assert_allclose(
        result.sel(parameter="motive energy"), wheel_power_kw() / (eta * 0.9)
    )


def test_low_load_transmission_map_does_not_oscillate():
    maps = {
        "gasoline": {
            "engine": {0: 0.25, 1: 0.25},
            "transmission": {0: 0, 0.025: 0.6, 1: 0.9},
        }
    }
    # In this segment eta = 24 * load. Hence 24 * load**2 = P_wheel / P_rated.
    model, result = calculate(
        speed=[3.6] * 6,
        eta=None,
        transmission=None,
        maps=maps,
        driving_mass=1000,
        rr_coef=0.001,
        drag_coef=0,
        engine_power=100,
    )
    expected = np.sqrt((1000 * 9.81 * 0.001 / 100000) / 24)
    np.testing.assert_allclose(
        result.sel(parameter="power load"),
        expected,
        rtol=1e-7,
    )
    assert model.efficiency_iterations < 100


def test_auxiliaries_remain_on_during_stops_and_final_moving_second():
    model, result = calculate(speed=[36, 36, 0, 0, 36, 36], aux_power=1000)
    np.testing.assert_array_equal(model.driving_time, 1)
    np.testing.assert_allclose(result.sel(parameter="auxiliary energy"), 4)


def test_zero_hvac_does_not_change_auxiliary_generation_losses():
    _, without_hvac = calculate(aux_power=1000)
    _, with_hvac = calculate(
        aux_power=1000,
        hvac_power=0,
        battery_cooling_unit=0,
        battery_heating_unit=0,
        heat_pump_cop_cooling=1,
        heat_pump_cop_heating=1,
        cooling_consumption=0,
        heating_consumption=0,
    )
    np.testing.assert_allclose(with_hvac, without_hvac)


def test_custom_terminal_stops_consume_auxiliary_energy():
    _, result = calculate(speed=[36, 36, 0, 0, 0], aux_power=1000)
    np.testing.assert_allclose(
        result.sel(parameter="auxiliary energy"), [4, 4, 4, 4, 4]
    )


def test_stationary_custom_cycle_preserves_auxiliary_demand():
    _, result = calculate(speed=[0, 0, 0], aux_power=1000)
    np.testing.assert_allclose(result.sel(parameter="auxiliary energy"), 4)


def test_coasting_load_reaches_exact_zero_in_efficiency_iteration():
    # A damped residual must not turn a zero-load map endpoint into a tiny
    # positive efficiency when there is no traction or auxiliary demand.
    maps = {"gasoline": {"engine": {0: 0, 1: 0.4}, "transmission": {0: 0.8, 1: 0.8}}}
    _, result = calculate(
        speed=[36, 36, 18, 0, 0],
        eta=None,
        transmission=None,
        maps=maps,
        aux_power=0,
        drag_coef=0,
        rr_coef=0,
    )
    assert result.sel(parameter="power load").isel(second=1) == 0
    assert result.sel(parameter="engine efficiency").isel(second=1) == 0
    assert np.isfinite(result).all()


def test_auxiliary_shaft_demand_is_included_in_combustion_load():
    _, result = calculate(speed=[36, 0, 36], aux_power=1000, rr_coef=0, drag_coef=0)
    assert result.sel(parameter="power load").isel(second=1).item() == pytest.approx(
        1 / 20
    )
    assert result.sel(parameter="auxiliary energy").isel(
        second=1
    ).item() == pytest.approx(4)


@pytest.mark.parametrize("powertrain", ["BEV", "BEV-depot", "PHEV-e"])
def test_electric_auxiliaries_bypass_traction_motor(powertrain):
    _, result = calculate(powertrain=powertrain, eta=0.5, aux_power=1000)
    np.testing.assert_allclose(result.sel(parameter="auxiliary energy"), 1)


def test_fuel_cell_auxiliaries_use_fuel_cell_conversion():
    _, result = calculate(
        powertrain="FCEV", eta=0.8, aux_power=1000, fuel_cell_system_efficiency=0.5
    )
    np.testing.assert_allclose(result.sel(parameter="auxiliary energy"), 2)


@pytest.mark.parametrize("factor", [1.0, 0.8])
def test_masked_efficiency_cells_retain_their_load_map(factor):
    efficiency = np.ma.array(np.full((6, 1, 1, 1, 1), 0.5), mask=False)
    efficiency.mask[3:] = True
    maps = {"gasoline": {"engine": {0: 0.25, 1: 0.25}, "transmission": {0: 1, 1: 1}}}
    _, result = calculate(eta=efficiency, maps=maps, engine_efficiency_factor=factor)
    np.testing.assert_allclose(
        result.sel(parameter="motive energy")[:3], wheel_power_kw() / 0.5
    )
    np.testing.assert_allclose(
        result.sel(parameter="motive energy")[3:], wheel_power_kw() / (0.25 * factor)
    )


@pytest.mark.parametrize("eta", [np.nan, np.inf, -0.1, 1.1])
def test_invalid_fixed_efficiency_rejected(eta):
    with pytest.raises(ValueError, match="Fixed efficiencies"):
        calculate(eta=eta)


@pytest.mark.parametrize(
    "parameter,value",
    [
        ("rr_coef", np.nan),
        ("drag_coef", np.inf),
        ("frontal_area", -1),
        ("engine_power", np.nan),
        ("aux_power", np.nan),
        ("recuperation_efficiency", 1.1),
        ("battery_charge_eff", -1),
    ],
)
def test_invalid_energy_inputs_cannot_turn_into_zero_results(parameter, value):
    with pytest.raises(ValueError):
        calculate(**{parameter: value})


def test_regeneration_power_limit_applies_before_generator_losses():
    model, result = calculate(
        speed=[72, 72, 0, 0],
        rr_coef=0,
        drag_coef=0,
        electric_motor_power=10,
        recuperation_efficiency=0.8,
        electric_motor_efficiency=0.9,
        battery_charge_eff=0.8,
        battery_discharge_eff=0.8,
    )
    assert model.regenerative_shaft_power_kw.max() == pytest.approx(10)
    assert result.sel(parameter="recuperated energy").min().item() == pytest.approx(
        -10 * 0.9 * 0.8 * 0.8
    )


def test_regeneration_cannot_exceed_available_braking_energy():
    _, result = calculate(
        speed=[72, 72, 0, 0],
        rr_coef=0,
        drag_coef=0,
        electric_motor_power=1000,
        recuperation_efficiency=0.8,
        electric_motor_efficiency=0.9,
        battery_charge_eff=0.95,
        battery_discharge_eff=0.95,
    )
    expected = result.sel(parameter="negative motive energy") * 0.8 * 0.9 * 0.95**2
    np.testing.assert_allclose(result.sel(parameter="recuperated energy"), expected)


def test_hybrid_load_uses_combustion_rating_not_combined_system_rating():
    _, result = calculate(
        powertrain="HEV-p", engine_power=100, combustion_engine_power=50
    )
    np.testing.assert_allclose(
        result.sel(parameter="power load"), wheel_power_kw() / 50
    )


def test_gradient_degrees_and_normal_force_on_slope():
    _, result = calculate(gradient=np.full(6, 10.0))
    speed = 100 / 3.6
    np.testing.assert_allclose(
        result.sel(parameter="gradient resistance"),
        1500 * 9.81 * np.sin(np.deg2rad(10)) * speed / 1000,
    )
    np.testing.assert_allclose(
        result.sel(parameter="rolling resistance"),
        1500 * 9.81 * 0.01 * np.cos(np.deg2rad(10)) * speed / 1000,
    )


def test_named_cycle_accepts_gradient_override():
    original = EnergyConsumptionModel("car", ["Medium"], ["ICEV-p"], "WLTC", None)
    gradient = np.full(len(original.cycle), 1.0)
    modified = EnergyConsumptionModel("car", ["Medium"], ["ICEV-p"], "WLTC", gradient)
    np.testing.assert_array_equal(modified.cycle, original.cycle)
    np.testing.assert_allclose(modified.gradient, np.deg2rad(1))
    np.testing.assert_array_equal(gradient, 1)


def test_custom_cycle_broadcasts_sizes_without_mutating_input():
    speed = np.array([0.0, 100.0, 100.0, 0.0])
    model = EnergyConsumptionModel("car", ["Micro", "Medium"], ["BEV"], speed, None)
    np.testing.assert_array_equal(speed, [0, 100, 100, 0])
    np.testing.assert_array_equal(model.cycle[:, 0], [0, 90, 90, 0])
    np.testing.assert_array_equal(model.cycle[:, 1], speed)


@pytest.mark.parametrize("speed", [[], [0, -1], [0, np.nan], [0, np.inf], [[0, 1]]])
def test_invalid_custom_speed_rejected(speed):
    with pytest.raises(ValueError, match="(cycle|speeds)"):
        EnergyConsumptionModel("car", ["Medium"], ["BEV"], speed, None)


def test_named_car_cycle_keeps_terminal_stops_but_excludes_nan_padding():
    model = EnergyConsumptionModel("car", ["Medium"], ["BEV"], "WLTC 3.1", None)
    speed = model.cycle[:, 0]
    finite = np.isfinite(speed)
    moving = np.flatnonzero(speed > 0)
    # The packaged low-speed phase includes a final idle period.
    assert np.flatnonzero(finite)[-1] > moving[-1]
    np.testing.assert_array_equal(model.driving_time[:, 0, 0, 0, 0], finite)
    assert not model.driving_time[~finite].any()
