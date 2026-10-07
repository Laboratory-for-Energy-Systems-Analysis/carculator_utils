"""Reproduce the 2025 energy audit with the matching vehicle packages installed.

Run from a Python 3.12 environment with matching source checkouts installed::

    python scripts/validate_energy_2025.py --output /tmp/energy-audit

The audit records failures; it does not change the energy model or calibrate inputs
to consumption observations. Custom and SORT traces use the public cycle and
gradient overrides; instrumentation only records mass and tightens audit sizing.
"""

import argparse
import contextlib
import csv
import hashlib
import importlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import xarray as xr

from carculator_utils.driving_cycles import get_standard_driving_cycle_and_gradient
from carculator_utils.energy_consumption import EnergyConsumptionModel
from carculator_utils.model import VehicleModel

PACKAGES = {
    "car": ("carculator", "Car"),
    "bus": ("carculator_bus", "Bus"),
    "truck": ("carculator_truck", "Truck"),
    "two-wheeler": ("carculator_two_wheeler", "TwoWheeler"),
}
PARAMETERS = [
    "TtW energy",
    "fuel consumption",
    "fuel mass",
    "electricity consumption",
    "driving mass",
    "curb mass",
    "cargo mass",
    "total cargo mass",
    "average passengers",
    "average passenger mass",
    "power",
    "electric power",
    "engine efficiency",
    "transmission efficiency",
    "fuel density per kg",
    "LHV fuel MJ per kg",
    "auxiliary energy",
    "range",
    "target range",
    "daily distance",
    "HVAC power",
    "rolling resistance coefficient",
    "aerodynamic drag coefficient",
    "frontal area",
    "battery charge efficiency",
    "battery discharge efficiency",
    "charger efficiency",
    "recuperation efficiency",
    "auxiliary power demand",
    "auxiliary power base demand",
    "gross mass",
    "is_available",
    "is_compliant",
]


def input_array(kind, size, powertrain):
    """Load explicit 2025 inputs before running the complete vehicle model."""
    package, prefix = PACKAGES[kind]
    module = importlib.import_module(package)
    inputs = getattr(module, prefix + "InputParameters")()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs, scope={"size": [size], "powertrain": [powertrain], "year": [2025]}
    )
    # Mass-matched benchmarks tighten sizing to 1e-8. The ordinary input
    # builder uses float32, which cannot resolve that relative tolerance.
    return array.astype(float)


def sort_cycle(name):
    """Use the shipped one-second SORT profile; remove NaN storage padding."""
    speed, _ = get_standard_driving_cycle_and_gradient(
        "car", ["Medium"], name.replace("SORT", "SORT ")
    )
    return speed[:, 0][np.isfinite(speed[:, 0])].copy()


def run_case(
    output,
    case_id,
    kind,
    size,
    powertrain,
    cycle,
    *,
    inputs=None,
    factors=None,
    temperature=None,
    curb_mass=None,
    power=None,
    payload=None,
    target_driving_mass=None,
    sizing_rtol=None,
    target_range=None,
    battery_capacity=None,
    engine_efficiency=None,
    transmission_efficiency=None,
    cycle_profile=None,
    cycle_label=None,
    combustion_controls=None,
):
    """Run set_all(), retaining default fuel blends and all sizing steps."""
    package, prefix = PACKAGES[kind]
    module = importlib.import_module(package)
    array = input_array(kind, size, powertrain)
    for name, value in (inputs or {}).items():
        array.loc[dict(parameter=name)] = value
    for name, factor in (factors or {}).items():
        array.loc[dict(parameter=name)] *= factor
    key = (powertrain, size, 2025)
    kwargs = {"cycle": "bus" if kind == "bus" and cycle.startswith("SORT") else cycle}
    if powertrain in {"PHEV-e", "PHEV-c-p", "PHEV-c-d"}:
        # Retain the explicitly requested operating mode after full set_all().
        kwargs["drop_hybrids"] = False
    if temperature is not None:
        kwargs["ambient_temperature"] = temperature
    for name, value in [
        ("target_mass", curb_mass),
        ("power", power),
        ("payload", payload),
        ("target_range", target_range),
    ]:
        if value is not None:
            kwargs[name] = {key: value}
    if battery_capacity is not None:
        kwargs["energy_storage"] = {"capacity": {key: battery_capacity}}
    for name, value in [
        ("engine_efficiency", engine_efficiency),
        ("transmission_efficiency", transmission_efficiency),
    ]:
        if value is not None:
            kwargs[name] = {key: value}

    if combustion_controls is not None:
        kwargs["combustion_controls"] = {key: combustion_controls}

    energy_masses = []
    custom_speed = None
    if cycle_profile is not None:
        profile_path = Path(cycle_profile)
        if not profile_path.is_absolute():
            profile_path = Path(__file__).resolve().parents[1] / profile_path
        profile = np.loadtxt(profile_path, delimiter=",", skiprows=1)
        if (
            profile.ndim != 2
            or profile.shape[1] != 2
            or len(profile) < 2
            or not np.isfinite(profile).all()
            or not np.array_equal(profile[:, 0], np.arange(len(profile)))
            or np.any(profile[:, 1] < 0)
        ):
            raise ValueError(
                "Cycle CSV must contain consecutive seconds and finite nonnegative km/h"
            )
        custom_speed = profile[:, 1].copy()
    original_energy = EnergyConsumptionModel.motive_energy_per_km
    original_sizing = VehicleModel.iterate_sizing

    def capture_energy_mass(ecm, driving_mass, *args, **energy_kwargs):
        # Copy the scalar at calculation time: the final model mass may differ.
        energy_masses.append(float(driving_mass.item()))
        return original_energy(ecm, driving_mass, *args, **energy_kwargs)

    def tight_sizing(model, parameter, rtol, mask=None):
        return original_sizing(model, parameter, min(rtol, sizing_rtol), mask)

    array_cycle = custom_speed is not None or (
        kind == "bus" and cycle.startswith("SORT")
    )
    if array_cycle:
        kwargs["cycle"] = (
            custom_speed.copy() if custom_speed is not None else sort_cycle(cycle)
        )
        kwargs["gradient"] = np.zeros_like(kwargs["cycle"])
    with (output / "logs" / (case_id + ".txt")).open("w") as log:
        with contextlib.ExitStack() as stack:
            stack.enter_context(contextlib.redirect_stdout(log))
            stack.enter_context(
                patch.object(
                    EnergyConsumptionModel, "motive_energy_per_km", capture_energy_mass
                )
            )
            if sizing_rtol is not None:
                stack.enter_context(
                    patch.object(VehicleModel, "iterate_sizing", tight_sizing)
                )
            # Adjust mass/load only, never fit consumption or efficiency to observations.
            for _ in range(30):
                model = getattr(module, prefix + "Model")(array, **kwargs)
                model.set_all()
                if target_driving_mass is None:
                    break
                error = target_driving_mass - float(model["driving mass"].item())
                print(
                    f"Mass iteration: final={float(model['driving mass'].item()):.6f}, "
                    f"energy input={energy_masses[-1]:.6f}, target={target_driving_mass:.6f} kg"
                )
                if (
                    abs(error) < 0.1
                    and abs(energy_masses[-1] - target_driving_mass) < 0.1
                ):
                    break
                if kind == "truck":
                    previous_payload = kwargs.get("payload", {}).get(
                        key, float(model["cargo mass"].item())
                    )
                    kwargs["payload"] = {key: previous_payload + error}
                elif kind == "bus":
                    passenger_mass = float(model["average passenger mass"].item())
                    passenger_mass += float(model["passenger luggage mass"].item())
                    passengers = (
                        float(model["average passengers"].item())
                        + error / passenger_mass
                    )
                    if passengers < 0:
                        raise ValueError(
                            "Requested bus mass is below its modelled curb mass"
                        )
                    array.loc[dict(parameter="average passengers")] = passengers
                else:
                    kwargs["target_mass"] = {
                        key: float(model["curb mass"].item()) + error
                    }
            else:
                raise RuntimeError(
                    "Could not match final and energy-input driving mass within 0.1 kg"
                )

    row = {
        "case": case_id,
        "vehicle": kind,
        "size": size,
        "powertrain": powertrain,
        "year": 2025,
        "cycle": cycle_label or cycle,
        "cycle_profile": cycle_profile,
        "cycle_profile_sha256": (
            hashlib.sha256(profile_path.read_bytes()).hexdigest()
            if custom_speed is not None
            else None
        ),
        "constructor_cycle": "custom array" if array_cycle else cycle,
        "temperature_C": temperature,
        "sort_adapter": False,
        "input_overrides": json.dumps(inputs or {}, sort_keys=True),
        "input_factors": json.dumps(factors or {}, sort_keys=True),
        "requested_curb_mass_kg": curb_mass,
        "requested_power_kW": power,
        "requested_driving_mass_kg": target_driving_mass,
        "energy_input_driving_mass_kg": energy_masses[-1],
        "sizing_rtol_override": sizing_rtol,
        "requested_range_km": target_range,
        "requested_battery_capacity_kWh": battery_capacity,
        "requested_engine_efficiency": engine_efficiency,
        "requested_transmission_efficiency": transmission_efficiency,
    }
    for parameter in PARAMETERS:
        if parameter in model.array.parameter:
            row[parameter] = float(model[parameter].item())
    energy = model.energy.squeeze(drop=True)
    get = lambda name: energy.sel(parameter=name).values
    velocity = get("velocity")
    distance = velocity.sum() / 1000
    raw_cycle = model.ecm.cycle[:, 0]
    last_motion = np.flatnonzero(velocity > 0)[-1]
    finite_seconds = int(np.isfinite(raw_cycle).sum())
    # Some bus columns are padded with zeros rather than NaNs. Report both bounds.
    row.update(
        distance_km=float(distance),
        stored_seconds=len(velocity),
        finite_seconds=finite_seconds,
        last_motion_second=int(last_motion),
        mean_speed_finite_kph=float(distance * 3600 / finite_seconds),
        mean_speed_through_last_motion_kph=float(distance * 3600 / (last_motion + 1)),
        trailing_zero_seconds=int(np.count_nonzero(raw_cycle[last_motion + 1 :] == 0)),
        stopped_seconds_through_last_motion=int(
            np.count_nonzero(velocity[: last_motion + 1] == 0)
        ),
    )
    efficiencies = get("engine efficiency") * get("transmission efficiency")
    required = get("motive energy at wheels") / np.where(
        efficiencies > 0, efficiencies, 1
    )
    deficit = np.maximum(required - get("motive energy"), 0)
    row["motive_input_removed_pct"] = float(100 * deficit.sum() / required.sum())
    row["cap_active_seconds"] = int(np.count_nonzero(deficit > 1e-8))
    row["wheel_power_exceeds_rating_seconds"] = int(
        np.count_nonzero(
            get("motive energy at wheels")
            / np.where(
                get("transmission efficiency") > 0, get("transmission efficiency"), 1
            )
            > row["power"] + 1e-8
        )
    )
    row["ttw_without_input_cap_kJ_km"] = row["TtW energy"] + float(
        deficit.sum() / distance
    )
    row["ttw_kWh_100km"] = row["TtW energy"] / 36
    row["battery_terminal_kWh_100km"] = (
        float(model.battery_terminal_energy.item()) / 36
        if powertrain.startswith("BEV") or powertrain == "PHEV-e"
        else None
    )
    row["electricity_kWh_100km"] = row["electricity consumption"] * 100
    range_parameter = next(
        name
        for name in ["range", "target range", "daily distance"]
        if name in model.array.parameter
    )
    distance_per_tank = float(model[range_parameter].item())
    row["fuel_kg_100km"] = (
        100 * row["fuel mass"] / distance_per_tank if distance_per_tank > 0 else 0.0
    )
    gas = powertrain in {"ICEV-g", "FCEV"}
    row["fuel_L_100km"] = None if gas else row["fuel consumption"] * 100
    row["fuel_reporting_unit"] = "kg/100 km" if gas else "L/100 km"
    if not gas and row["fuel_L_100km"] > 0:
        conversion = row["LHV fuel MJ per kg"] * row["fuel density per kg"] * 10
        row["fuel_from_energy_L_100km"] = row["TtW energy"] / conversion
        row["fuel_without_input_cap_L_100km"] = (
            row["ttw_without_input_cap_kJ_km"] / conversion
        )
    row["energy_finite"] = bool(np.isfinite(energy.values).all())
    row["positive_consumption"] = bool(row["TtW energy"] > 0)
    if "gross mass" in row:
        row["within_gross_mass"] = row["driving mass"] <= row["gross mass"]
    row["eligible_for_comparison"] = bool(
        row["energy_finite"]
        and row["positive_consumption"]
        and row.get("within_gross_mass", True)
        and row.get("is_available", 1)
        and row.get("is_compliant", 1)
    )
    if not row["eligible_for_comparison"]:
        row["ttw_without_input_cap_kJ_km"] = None
    load = get("power load").reshape(model.ecm.velocity.shape)
    next_efficiency = model.ecm.calculate_efficiency(
        np.ones_like(load), load, "engine"
    ).ravel()
    moving = (get("motive energy at wheels") > 0) & (model.ecm.driving_time.ravel() > 0)
    row["engine_efficiency_next_iteration_max_change"] = float(
        np.max(np.abs(next_efficiency[moving] - get("engine efficiency")[moving]))
    )
    row["engine_efficiency_next_iteration_mean_change"] = float(
        np.mean(np.abs(next_efficiency[moving] - get("engine efficiency")[moving]))
    )
    for name in [
        "motive energy at wheels",
        "motive energy",
        "recuperated energy",
        "auxiliary energy",
        "heating energy",
        "cooling energy",
    ]:
        row[name + " kJ/km"] = float(get(name).sum() / distance)
    if "combustion control energy" in energy.parameter:
        row["combustion control energy kJ/km"] = float(
            get("combustion control energy").sum() / distance
        )
        row["shaft_power_deficit_max_kW"] = float(model.ecm.power_deficit_kw.max())
        row["combustion_controls"] = combustion_controls
        row["combustion_control_diagnostics"] = [
            {
                "key": [str(x) for x in key],
                "stopped_engine_seconds": int(np.count_nonzero(d["state"] == 2)),
                "fuel_cut_seconds": int(np.count_nonzero(d["state"] == 3)),
                "buffer_min_kJ": float(d["buffer_energy_J"].min() / 1000),
                "buffer_max_kJ": float(d["buffer_energy_J"].max() / 1000),
                "control_fuel_kJ": float(d["control_fuel_kJ"].sum()),
                "terminal_recharge_fuel_kJ": d["terminal_recharge_fuel_kJ"],
                "delivered_service_kJ": d["delivered_service_kJ"],
                "buffer_losses_kJ": d["buffer_losses_kJ"],
            }
            for key, d in model.ecm.combustion_control_diagnostics.items()
        ]
    print(
        f"{case_id}: {row['fuel_kg_100km'] if gas else row['fuel_L_100km']:.3f} {row['fuel_reporting_unit']}; "
        f"{row['electricity_kWh_100km']:.2f} kWh/100km; "
        f"input cap removes {row['motive_input_removed_pct']:.1f}%",
        flush=True,
    )
    return row


def physics_probes():
    """Independent analytical expectations, not acceptance tolerances fitted to data."""
    records = []

    def record(name, expected, actual, unit, explanation):
        records.append(
            dict(
                check=name,
                expected=expected,
                actual=actual,
                unit=unit,
                passed=bool(np.isclose(expected, actual, rtol=1e-9, atol=1e-9)),
                explanation=explanation,
            )
        )

    def scalar(value):
        return xr.DataArray(
            np.full((1, 1, 1, 1), value, dtype=float),
            dims=["size", "powertrain", "year", "value"],
        )

    def calculate(speed=None, gradient=None, eta=0.25, **overrides):
        speed = np.full(60, 100.0) if speed is None else np.asarray(speed, dtype=float)
        ecm = EnergyConsumptionModel(
            "car", ["Medium"], ["ICEV-p"], speed, gradient, ambient_temperature=20
        )
        ecm.efficiency_coefficients = None  # Isolate physics from empirical load maps.
        values = dict(
            driving_mass=1500,
            rr_coef=0.01,
            drag_coef=0.3,
            frontal_area=2.2,
            electric_motor_power=0,
            engine_power=1000,
            recuperation_efficiency=0.8,
            aux_power=0,
            battery_charge_eff=1,
            battery_discharge_eff=1,
        )
        values.update(overrides)
        args = {name: scalar(value) for name, value in values.items()}
        args["engine_efficiency"] = np.full_like(ecm.velocity, eta)
        args["transmission_efficiency"] = np.ones_like(ecm.velocity)
        return ecm, ecm.motive_energy_per_km(**args).squeeze(drop=True)

    v = 100 / 3.6
    wheel_power = (1500 * 9.81 * 0.01 + 0.5 * 1.204 * 0.3 * 2.2 * v**2) * v / 1000
    _, e = calculate()
    record(
        "rolling_and_drag",
        wheel_power,
        float(e.sel(parameter="motive energy at wheels").mean()),
        "kW",
        "1500 kg, 100 km/h, Crr=.01, Cd=.3, A=2.2 m2; flat, steady speed",
    )
    record(
        "unconstrained_energy_conversion",
        wheel_power / 0.25,
        float(e.sel(parameter="motive energy").mean()),
        "kW",
        "At sufficient rated power, wheel power / efficiency recovers input power",
    )
    record(
        "engine_load_uses_shaft_power",
        wheel_power / 1000,
        float(e.sel(parameter="power load").isel(second=slice(None, -1)).mean()),
        "fraction",
        "Shaft output / rated shaft power, with unit transmission efficiency",
    )
    _, e = calculate(engine_power=20)
    record(
        "fuel_input_cap",
        wheel_power / 0.25,
        float(e.sel(parameter="motive energy").mean()),
        "kW",
        "Wheel demand is below 20 kW shaft rating; fuel input must be wheel/.25",
    )
    _, e = calculate(gradient=np.ones(60), engine_power=1e6)
    record(
        "gradient_documented_degrees",
        1500 * 9.81 * np.sin(np.deg2rad(1)) * v / 1000,
        float(e.sel(parameter="gradient resistance").mean()),
        "kW",
        "Public docstring specifies degrees",
    )
    _, e = calculate(
        speed=[36, 36, 18, 0, 0],
        rr_coef=0,
        drag_coef=0,
        electric_motor_power=1000,
        recuperation_efficiency=0,
        eta=1,
    )
    record(
        "zero_recuperation",
        0,
        float(e.sel(parameter="recuperated energy").sum()),
        "kJ",
        "Zero recuperation efficiency must disable recovery",
    )
    _, e = calculate(speed=[36, 36, 0, 0, 36, 36], aux_power=1000, eta=1)
    record(
        "auxiliaries_during_stop",
        2,
        float(e.sel(parameter="auxiliary energy").isel(second=[2, 3]).sum()),
        "kJ",
        "A specified constant 1 kW auxiliary load for two stopped seconds",
    )
    _, e = calculate(
        aux_power=1000,
        hvac_power=0,
        battery_cooling_unit=0,
        battery_heating_unit=0,
        heat_pump_cop_cooling=1,
        heat_pump_cop_heating=1,
        cooling_consumption=0,
        heating_consumption=0,
    )
    record(
        "zero_hvac_preserves_auxiliary_boundary",
        4,
        float(e.sel(parameter="auxiliary energy").mean()),
        "kW",
        "1 kW / .25 generation efficiency should remain 4 kW when zero HVAC is supplied",
    )
    ecm, _ = calculate(speed=[36, 36, 36])
    record(
        "last_moving_second_active",
        1,
        float(ecm.driving_time[-1].item()),
        "boolean",
        "Final moving second belongs to operating time",
    )
    try:
        calculate(driving_mass=float("nan"))
        rejected = False
    except ValueError:
        rejected = True
    record(
        "nonfinite_mass_rejected",
        True,
        rejected,
        "boolean",
        "An active vehicle with NaN mass should fail explicitly",
    )
    # Probe the public bus custom-cycle path separately from the documented SORT adapter.
    from carculator_bus import BusModel

    try:
        with contextlib.redirect_stdout(None):
            BusModel(
                input_array("bus", "13m-city", "ICEV-d"), cycle=sort_cycle("SORT2")
            ).set_all()
        success, detail = True, "Custom numpy cycle accepted"
    except Exception as exc:
        success, detail = False, f"{type(exc).__name__}: {exc}"
    record("bus_public_custom_cycle", True, success, "boolean", detail)
    return records


def cases():
    for kind, sizes, powertrains, cycles in [
        (
            "car",
            ["Lower medium", "Medium"],
            ["ICEV-p", "ICEV-d", "HEV-p", "BEV"],
            ["WLTC"],
        ),
        ("bus", ["13m-city", "18m"], ["ICEV-d", "HEV-d", "BEV-depot"], ["bus"]),
        (
            "truck",
            ["18t", "40t"],
            ["ICEV-d", "BEV"],
            ["Urban delivery", "Regional delivery", "Long haul"],
        ),
    ]:
        for size in sizes:
            for pwt in powertrains:
                for cycle in cycles:
                    name = f"baseline-{kind}-{size}-{pwt}-{cycle}".replace(" ", "_")
                    yield name, (kind, size, pwt, cycle), {}
    for pwt, mass, power, name in [
        ("ICEV-p", 1307, 85, "golf-petrol"),
        ("ICEV-d", 1387, 85, "golf-diesel"),
        ("HEV-p", 1377.5, 103, "corolla-hybrid"),
    ]:
        yield name, ("car", "Lower medium", pwt, "WLTC"), dict(
            curb_mass=mass,
            power=power,
            inputs={
                "average passengers": 1,
                "average passenger mass": 75,
                "cargo mass": 0,
            },
        )
    for pwt in ["ICEV-d", "BEV-depot"]:
        for cycle in ["SORT1", "SORT2", "SORT3"]:
            yield f"bus-{pwt}-{cycle}", ("bus", "13m-city", pwt, cycle), {}
        yield f"bus-{pwt}-SORT2-no-hvac", ("bus", "13m-city", pwt, "SORT2"), dict(
            temperature=20,
            inputs={
                "HVAC power": 0,
                "battery cooling unit": 0,
                "battery heating unit": 0,
            },
        )
    yield "bus-diesel-SORT2-approx-test-load", (
        "bus",
        "13m-city",
        "ICEV-d",
        "SORT2",
    ), dict(
        curb_mass=10600,
        power=209,
        temperature=20,
        inputs={
            "average passengers": 3200 / 75,
            "average passenger mass": 75,
            "passenger luggage mass": 0,
            "HVAC power": 0,
            "battery cooling unit": 0,
            "battery heating unit": 0,
        },
    )
    yield "truck-31t", ("truck", "40t", "ICEV-d", "Long haul"), dict(
        target_driving_mass=31000
    )
    for kind, size, pwt, cycle in [
        ("car", "Lower medium", "ICEV-d", "WLTC"),
        ("bus", "13m-city", "BEV-depot", "bus"),
        ("truck", "40t", "ICEV-d", "Long haul"),
    ]:
        for temperature in [-10, 20, 35]:
            yield f"temperature-{kind}-{temperature}", (kind, size, pwt, cycle), dict(
                temperature=temperature
            )
        for parameter in [
            "aerodynamic drag coefficient",
            "rolling resistance coefficient",
        ]:
            short = "drag" if parameter.startswith("aero") else "rolling"
            yield f"sensitivity-{kind}-{short}", (kind, size, pwt, cycle), dict(
                factors={parameter: 1.1}
            )


def provenance():
    result = {
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "xarray": xr.__version__,
        "packages": {},
    }
    for name in ["carculator_utils", *(p[0] for p in PACKAGES.values())]:
        module = importlib.import_module(name)
        directory = Path(module.__file__).resolve().parent
        git = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
        )
        files = list(directory.glob("*.py"))
        files += list((directory / "data").glob("*.json"))
        files += list((directory / "data").glob("*.yaml"))
        for subdir in ["efficiency", "driving_cycles", "gradient"]:
            files += list((directory / "data" / subdir).glob("*"))
        result["packages"][name] = {
            "version": str(module.__version__),
            "path": str(directory),
            "git_head": git.stdout.strip() if git.returncode == 0 else None,
            "sha256": {
                str(p.relative_to(directory)): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in sorted(files)
                if p.is_file()
            },
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New directory for results and logs"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "logs").mkdir()
    write_json = lambda name, value: (args.output / name).write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    write_json("provenance.json", provenance())
    rows, errors = [], []
    for name, positional, kwargs in cases():
        try:
            rows.append(run_case(args.output, name, *positional, **kwargs))
        except Exception as exc:
            errors.append({"case": name, "error": f"{type(exc).__name__}: {exc}"})
            print(name, errors[-1]["error"], flush=True)
        write_json("runs.json", rows)
        write_json("errors.json", errors)
    probes = physics_probes()
    write_json("physics_checks.json", probes)
    references = json.loads(
        Path(__file__)
        .with_name("energy_benchmarks_2025.json")
        .read_text(encoding="utf-8")
    )
    comparisons = []
    indexed = {row["case"]: row for row in rows}
    for reference in references["benchmarks"]:
        for case in reference["cases"]:
            if case not in indexed or not indexed[case]["eligible_for_comparison"]:
                continue
            value = indexed[case][reference["metric"]]
            low, high = reference["reported_min"], reference["reported_max"]
            comparisons.append(
                dict(
                    case=case,
                    benchmark=reference["id"],
                    model=value,
                    reported_min=low,
                    reported_max=high,
                    unit=reference["unit"],
                    deviation_low_pct=100 * (value / high - 1),
                    deviation_high_pct=100 * (value / low - 1),
                    comparability=reference["comparability"],
                    source=reference["source"],
                )
            )
    write_json("comparisons.json", comparisons)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with (args.output / "runs.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(
        f"{len(rows)} complete runs; {len(errors)} run errors; "
        f"{sum(p['passed'] for p in probes)}/{len(probes)} physics/API checks passed"
    )
    # A completed audit is not a passing model validation; report failures explicitly.
    return 1 if errors or not all(p["passed"] for p in probes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
