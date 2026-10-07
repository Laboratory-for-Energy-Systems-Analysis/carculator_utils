"""Opt-in operating controls for conventional petrol cars, at one-second resolution.

Configuration defaults are engineering assumptions, not calibrated vehicle data.
The buffer starts full. Any terminal deficit is recharged outside the trace and
charged to cycle fuel, so stored initial energy is never a free energy source.
"""

from collections.abc import Mapping
from dataclasses import dataclass, fields

import numpy as np


@dataclass(frozen=True)
class CombustionControl:
    """Explicit control assumptions; power in W and energy in kJ.

    ``control_allowed`` can veto controls by sample (e.g. thermal conditions).
    ``fuel_cut_allowed`` can supply external gear/RPM eligibility. Without it,
    speed and braking-power thresholds are proxies, not an engine-speed model.
    """

    start_stop: bool = False
    deceleration_fuel_cut: bool = False
    warmup_seconds: int = 120
    stop_delay_seconds: int = 2
    minimum_on_seconds: int = 5
    fuel_cut_delay_seconds: int = 2
    minimum_fuel_cut_speed_kmh: float = 20.0
    engine_drag_power_W: float = 5000.0
    reverse_transmission_efficiency: float = 0.8
    buffer_capacity_kJ: float = 180.0
    buffer_recharge_power_W: float = 500.0
    buffer_round_trip_efficiency: float = 0.75
    terminal_recharge_engine_efficiency: float = 0.3
    restart_fuel_kJ: float = 5.0
    fuel_resume_kJ: float = 5.0
    control_allowed: object = None
    fuel_cut_allowed: object = None

    @classmethod
    def from_mapping(cls, options):
        """Validate explicit controls without silently accepting misspelled keys."""
        if not isinstance(options, Mapping):
            raise ValueError("Combustion controls must be a mapping of options.")
        unknown = set(options) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(
                f"Unknown combustion control options: {sorted(unknown, key=str)}"
            )
        result = cls(**options)
        for field in fields(cls):
            name = field.name
            value = getattr(result, name)
            if name in {"start_stop", "deceleration_fuel_cut"}:
                if not isinstance(value, (bool, np.bool_)):
                    raise ValueError(f"{name} must be boolean.")
            elif name in {"control_allowed", "fuel_cut_allowed"}:
                if value is not None:
                    mask = np.asarray(value)
                    if mask.ndim != 1 or mask.dtype.kind != "b":
                        raise ValueError(
                            f"{name} must be a one-dimensional boolean mask."
                        )
            else:
                if (
                    isinstance(value, (bool, np.bool_))
                    or not isinstance(value, (int, float, np.integer, np.floating))
                    or not np.isfinite(value)
                    or value < 0
                ):
                    raise ValueError(f"{name} must be finite and nonnegative.")
                if name.endswith("seconds") and value != int(value):
                    raise ValueError(f"{name} must be an integer number of seconds.")
                if "efficiency" in name and not 0 < value <= 1:
                    raise ValueError(f"{name} must be in (0, 1].")
        return result


def validate_control_keys(controls, driving_mass, vehicle_type):
    """Validate keyed configurations against the labelled model scope."""
    if controls is None:
        return {}
    if not isinstance(controls, Mapping):
        raise ValueError(
            "combustion_controls must be keyed by (powertrain, size, year)."
        )
    if controls and vehicle_type != "car":
        raise ValueError(
            "Combustion controls currently support conventional petrol cars only."
        )
    validated = {}
    for key, options in controls.items():
        if not isinstance(key, tuple) or len(key) != 3:
            raise ValueError(
                "Combustion control keys must be (powertrain, size, year)."
            )
        for coordinate, label in zip(("powertrain", "size", "year"), key):
            if label not in driving_mass.coords[coordinate].values:
                raise ValueError(
                    f"Combustion control coordinate {coordinate}={label!r} is outside the model scope."
                )
        if key[0] != "ICEV-p":
            raise ValueError(
                "Combustion controls currently support conventional petrol cars only."
            )
        validated[key] = CombustionControl.from_mapping(options)
    return validated


def schedule_controls(
    speed, wheel_power, auxiliary_power, shaft_power, rated_power, active, config
):
    """Return a causal, bounded-buffer schedule and its independent energy ledger.

    Inputs are one-dimensional SI arrays, except scalar rated shaft power (W).
    Each active sample lasts one second. State codes: 0 inactive, 1 fueled,
    2 stopped engine, 3 rotating engine with deceleration fuel cut.
    """
    speed, wheel_power, auxiliary_power, shaft_power = np.broadcast_arrays(
        *[
            np.asarray(a, dtype=float)
            for a in (speed, wheel_power, auxiliary_power, shaft_power)
        ]
    )
    active = np.asarray(active, dtype=bool)
    if (
        speed.ndim != 1
        or active.shape != speed.shape
        or not all(
            np.isfinite(a).all()
            for a in (speed, wheel_power, auxiliary_power, shaft_power)
        )
    ):
        raise ValueError(
            "Control inputs must be finite one-dimensional arrays with matching masks."
        )
    if (
        np.any(speed < 0)
        or np.any(auxiliary_power < 0)
        or not np.isfinite(rated_power)
        or rated_power <= 0
    ):
        raise ValueError(
            "Control speed/auxiliary demand must be nonnegative and rated power positive."
        )

    def permission(value):
        if value is None:
            return active.copy()
        mask = np.asarray(value, dtype=bool)
        if mask.shape == active.shape:
            return mask & active
        if len(mask) == active.sum():
            full = np.zeros_like(active)
            full[active] = mask
            return full
        raise ValueError(
            "Control eligibility masks must match the stored or active cycle length."
        )

    allowed = permission(config.control_allowed)
    cut_allowed = permission(config.fuel_cut_allowed)
    n = len(speed)
    engine_aux = np.zeros(n)
    kinetic_service = np.zeros(n)
    recharge = np.zeros(n)
    buffer_service = np.zeros(n)
    control_fuel = np.zeros(n)  # kJ at each one-second sample
    state = np.zeros(n, dtype=np.int8)
    capacity = config.buffer_capacity_kJ * 1000
    stored = capacity
    soc = np.full(n, capacity)
    elapsed = stopped = cut_duration = on_duration = 0
    previous = 1
    for t in range(n):
        if not active[t]:
            soc[t] = stored
            continue
        service = auxiliary_power[t]
        stopped = stopped + 1 if speed[t] == 0 else 0
        warm = elapsed >= config.warmup_seconds and allowed[t]
        brake_available = (
            max(0.0, -wheel_power[t]) * config.reverse_transmission_efficiency
        )
        cut_candidate = bool(
            warm
            and cut_allowed[t]
            and speed[t] > 0
            and speed[t] * 3.6 >= config.minimum_fuel_cut_speed_kmh
            and brake_available >= service + config.engine_drag_power_W
        )
        cut_duration = cut_duration + 1 if cut_candidate else 0
        can_stop = bool(
            config.start_stop
            and warm
            and speed[t] == 0
            and stopped > config.stop_delay_seconds
            and stored >= service
            and (previous == 2 or on_duration >= config.minimum_on_seconds)
        )
        can_cut = bool(
            config.deceleration_fuel_cut
            and cut_candidate
            and cut_duration > config.fuel_cut_delay_seconds
        )
        if can_stop:
            current = 2
            stored -= service
            buffer_service[t] = service
        elif can_cut:
            current = 3
            kinetic_service[t] = service
        else:
            current = 1
            # Charge only during positive traction, bounded by shaft headroom.
            if config.start_stop and wheel_power[t] > 0:
                charge = min(
                    config.buffer_recharge_power_W,
                    max(0.0, rated_power - shaft_power[t]),
                    max(0.0, capacity - stored) / config.buffer_round_trip_efficiency,
                )
            else:
                charge = 0.0
            stored += charge * config.buffer_round_trip_efficiency
            recharge[t] = charge
            engine_aux[t] = service + charge
        if previous == 2 and current != 2:
            control_fuel[t] += config.restart_fuel_kJ
        if previous == 3 and current == 1:
            control_fuel[t] += config.fuel_resume_kJ
        on_duration = (
            on_duration + 1
            if current != 2 and previous != 2
            else (1 if current != 2 else 0)
        )
        state[t] = current
        previous = current
        elapsed += 1
        soc[t] = stored
    deficit = max(0.0, capacity - stored)
    terminal_shaft = deficit / config.buffer_round_trip_efficiency
    terminal_fuel = terminal_shaft / config.terminal_recharge_engine_efficiency / 1000
    # Boundary correction is distinct from instantaneous on-trace fuel.
    if active.any():
        control_fuel[np.flatnonzero(active)[-1]] += terminal_fuel
    engine_service = engine_aux - recharge
    assert np.allclose(
        engine_service + kinetic_service + buffer_service, auxiliary_power * active
    )
    assert np.isclose(
        recharge.sum() * config.buffer_round_trip_efficiency - buffer_service.sum(),
        stored - capacity,
        atol=1e-6,
    )
    assert np.all(soc >= -1e-7) and np.all(soc <= capacity + 1e-7)
    return dict(
        engine_auxiliary_power_W=engine_aux,
        state=state,
        buffer_energy_J=soc,
        recharge_input_J=recharge,
        buffer_service_J=buffer_service,
        kinetic_service_J=kinetic_service,
        control_fuel_kJ=control_fuel,
        terminal_recharge_fuel_kJ=terminal_fuel,
        terminal_recharge_input_kJ=terminal_shaft / 1000,
        delivered_service_kJ=float((auxiliary_power * active).sum() / 1000),
        buffer_losses_kJ=float(
            (recharge.sum() + terminal_shaft)
            * (1 - config.buffer_round_trip_efficiency)
            / 1000
        ),
    )
