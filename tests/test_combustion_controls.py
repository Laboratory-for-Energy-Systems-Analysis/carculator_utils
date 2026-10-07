"""Independent state-transition, service-energy and buffer-boundary regressions."""

import numpy as np
import pytest

from carculator_utils.combustion_controls import CombustionControl, schedule_controls


def run(
    speed, wheel=None, auxiliary=1000, shaft=None, rated=10000, active=None, **options
):
    speed = np.asarray(speed, dtype=float)
    n = len(speed)
    wheel = np.zeros(n) if wheel is None else np.asarray(wheel, dtype=float)
    aux = np.broadcast_to(auxiliary, (n,))
    shaft = np.maximum(wheel, 0) + aux if shaft is None else shaft
    defaults = dict(
        warmup_seconds=0,
        stop_delay_seconds=0,
        minimum_on_seconds=0,
        fuel_cut_delay_seconds=0,
        buffer_capacity_kJ=2,
        buffer_round_trip_efficiency=0.5,
        terminal_recharge_engine_efficiency=0.25,
        restart_fuel_kJ=3,
        fuel_resume_kJ=7,
    )
    defaults.update(options)
    cfg = CombustionControl.from_mapping(defaults)
    return schedule_controls(
        speed,
        wheel,
        aux,
        shaft,
        rated,
        np.ones(n, dtype=bool) if active is None else active,
        cfg,
    )


def test_finite_buffer_exhaustion_and_terminal_recharge_are_not_free_energy():
    result = run(
        [0, 0, 0, 10], wheel=[0, 0, 0, 5000], start_stop=True, buffer_recharge_power_W=0
    )
    assert result["state"].tolist() == [2, 2, 1, 1]
    assert result["buffer_energy_J"].tolist() == [1000, 0, 0, 0]
    # 2 kJ delivered through a 50% buffer and 25% engine require 16 kJ fuel.
    assert result["terminal_recharge_fuel_kJ"] == 16
    assert result["control_fuel_kJ"].sum() == 16 + 3  # one restart
    assert result["engine_auxiliary_power_W"].tolist() == [0, 0, 1000, 1000]


def test_recharge_is_causal_and_limited_by_engine_headroom_and_capacity():
    result = run(
        [0, 0, 10, 10, 10],
        wheel=[0, 0, 9500, 7000, 5000],
        shaft=[1000, 1000, 10500, 8000, 6000],
        start_stop=True,
        buffer_recharge_power_W=8000,
    )
    assert result["recharge_input_J"].tolist() == [0, 0, 0, 2000, 2000]
    assert result["buffer_energy_J"].tolist() == [1000, 0, 0, 1000, 2000]
    assert result["terminal_recharge_fuel_kJ"] == 0
    assert result["control_fuel_kJ"].sum() == 3
    assert result["buffer_losses_kJ"] == 2


def test_deceleration_cut_uses_kinetic_energy_and_charges_resume_fuel():
    result = run(
        [20, 20, 20, 20],
        wheel=[5000, -10000, -10000, 5000],
        deceleration_fuel_cut=True,
        engine_drag_power_W=5000,
    )
    assert result["state"].tolist() == [1, 3, 3, 1]
    assert result["kinetic_service_J"].sum() == 2000
    assert result["control_fuel_kJ"].tolist() == [0, 0, 0, 7]
    assert result["terminal_recharge_fuel_kJ"] == 0
    assert result["buffer_service_J"].sum() == 0


def test_weak_braking_low_speed_and_external_eligibility_veto_fuel_cut():
    result = run(
        [20, 2, 20, 20],
        wheel=[-5000, -20000, -20000, -20000],
        deceleration_fuel_cut=True,
        fuel_cut_allowed=[True, True, False, True],
    )
    assert result["state"].tolist() == [1, 1, 1, 3]


def test_warmup_stop_delay_minimum_on_time_and_thermal_veto():
    result = run(
        [0] * 8,
        auxiliary=0,
        start_stop=True,
        warmup_seconds=2,
        stop_delay_seconds=1,
        minimum_on_seconds=2,
        control_allowed=[True, True, True, False, True, True, True, True],
    )
    assert result["state"].tolist() == [1, 1, 2, 1, 1, 2, 2, 2]
    assert result["control_fuel_kJ"].sum() == 3


def test_cut_delay_restarts_after_eligibility_break():
    result = run(
        [20] * 6,
        wheel=[-20000] * 6,
        deceleration_fuel_cut=True,
        fuel_cut_delay_seconds=1,
        fuel_cut_allowed=[True, True, False, True, True, True],
    )
    assert result["state"].tolist() == [1, 3, 1, 1, 3, 3]


def test_padding_is_not_an_operating_or_restart_event():
    result = run([0, 0, 0, 0], start_stop=True, active=[True, True, False, False])
    assert result["state"].tolist() == [2, 2, 0, 0]
    assert result["control_fuel_kJ"].tolist() == [0, 16, 0, 0]
    assert result["delivered_service_kJ"] == 2


def test_disabled_controls_preserve_load_without_buffer_operations():
    result = run([0, 20, 20], wheel=[0, -20000, 5000])
    assert result["state"].tolist() == [1, 1, 1]
    assert result["engine_auxiliary_power_W"].tolist() == [1000] * 3
    assert result["control_fuel_kJ"].sum() == 0
    assert result["recharge_input_J"].sum() == 0


@pytest.mark.parametrize(
    "options",
    [
        {"start_stop": 1},
        {"buffer_capacity_kJ": -1},
        {"restart_fuel_kJ": float("nan")},
        {"buffer_round_trip_efficiency": 0},
        {"reverse_transmission_efficiency": 1.1},
        {"warmup_seconds": 0.5},
        {"unknown": True},
        {"control_allowed": [0, 1]},
    ],
)
def test_invalid_control_options_are_rejected(options):
    with pytest.raises(ValueError):
        CombustionControl.from_mapping(options)


def test_eligibility_mask_length_is_checked():
    with pytest.raises(ValueError, match="cycle length"):
        run([0, 0], start_stop=True, control_allowed=[True])


def test_ecm_control_fuel_is_separate_and_wheel_work_is_preserved():
    import xarray as xr
    from carculator_utils.energy_consumption import EnergyConsumptionModel

    speed = np.array([0, 0, 0, 36, 36, 18, 0, 0], dtype=float)
    ecm = EnergyConsumptionModel("car", ["Lower medium"], ["ICEV-p"], speed, None)
    dims = ("size", "powertrain", "year", "value")
    coords = dict(size=["Lower medium"], powertrain=["ICEV-p"], year=[2025], value=[0])
    parameters = dict(
        driving_mass=1500.0,
        rr_coef=0.0,
        drag_coef=0.0,
        frontal_area=2.0,
        electric_motor_power=0.0,
        engine_power=100.0,
        recuperation_efficiency=0.0,
        aux_power=1000.0,
        battery_charge_eff=1.0,
        battery_discharge_eff=1.0,
    )
    kwargs = {
        name: xr.DataArray(np.full((1, 1, 1, 1), value), dims=dims, coords=coords)
        for name, value in parameters.items()
    }
    kwargs.update(engine_efficiency=0.25, transmission_efficiency=1.0)
    baseline = ecm.motive_energy_per_km(**kwargs)
    result = ecm.motive_energy_per_km(
        **kwargs,
        combustion_controls={
            ("ICEV-p", "Lower medium", 2025): dict(
                start_stop=True,
                warmup_seconds=0,
                stop_delay_seconds=0,
                minimum_on_seconds=0,
                buffer_capacity_kJ=2,
                buffer_round_trip_efficiency=0.5,
                terminal_recharge_engine_efficiency=0.25,
                restart_fuel_kJ=3,
                buffer_recharge_power_W=0,
            )
        },
    )
    np.testing.assert_array_equal(
        result.sel(parameter="motive energy at wheels"),
        baseline.sel(parameter="motive energy at wheels"),
    )
    assert float(result.sel(parameter="combustion control energy").sum()) == 19
    assert (
        float(
            baseline.sel(parameter="auxiliary energy").sum()
            - result.sel(parameter="auxiliary energy").sum()
        )
        == 8
    )
    # Buffer losses plus restart cost raise fuel for a constant-efficiency engine.
    # The controller must not promise savings independently of the engine map.
    assert float(
        result.sel(
            parameter=["motive energy", "auxiliary energy", "combustion control energy"]
        ).sum()
        - baseline.sel(parameter=["motive energy", "auxiliary energy"]).sum()
    ) == pytest.approx(11)
    assert len(ecm.combustion_control_diagnostics) == 1
    again = ecm.motive_energy_per_km(**kwargs)
    xr.testing.assert_equal(again, baseline)
    assert ecm.combustion_control_diagnostics == {}
    ecm.efficiency_coefficients["gasoline"]["transmission"] = {0: 0.8, 1: 0.9}
    kwargs.pop("transmission_efficiency")
    with pytest.raises(ValueError, match="constant positive transmission"):
        ecm.motive_energy_per_km(
            **kwargs,
            combustion_controls={
                ("ICEV-p", "Lower medium", 2025): {"start_stop": True}
            },
        )


def test_zero_capacity_cannot_supply_nonzero_stopped_auxiliaries():
    result = run([0, 0, 0], start_stop=True, buffer_capacity_kJ=0)
    assert result["state"].tolist() == [1, 1, 1]
    assert result["terminal_recharge_fuel_kJ"] == 0
