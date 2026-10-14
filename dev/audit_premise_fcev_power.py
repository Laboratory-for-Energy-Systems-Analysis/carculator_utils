"""Offline FCEV power-boundary screening; no inventory or runtime changes.

Run with matched Python 3.12 vehicle sources. One-second trace energies in kJ
are numerically powers in kW. A nominal model requirement is not a measured
battery capability. The storage calculation is an optimistic lower bound,
not a fuel-cell controller, SOC simulation, or battery certification.
"""

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def dc_rating(motor_kw, motor_efficiency, auxiliary_kw, stack_kw, gross_net):
    """Compare mechanical motor output with net electrical supply, in kW.

    Motor efficiency covers the model's declared motor conversion losses.
    No additional inverter efficiency or battery internal loss is invented.
    Auxiliary demand is delivered at the DC bus, bypassing the motor.
    """
    values = np.asarray(
        [motor_kw, motor_efficiency, auxiliary_kw, stack_kw, gross_net], float
    )
    if not np.isfinite(values).all() or min(motor_kw, auxiliary_kw, stack_kw) < 0:
        raise ValueError("Power inputs must be finite and nonnegative.")
    if not 0 < motor_efficiency <= 1 or gross_net < 1:
        raise ValueError("Invalid motor efficiency or stack gross/net multiplier.")
    required = motor_kw / motor_efficiency + auxiliary_kw
    net_stack = stack_kw / gross_net
    return required, net_stack, max(required - net_stack, 0)


def storage_lower_bound(demand_kw, regeneration_kw, net_stack_kw, eta_c, eta_d):
    """Minimum usable kWh for a periodic trace with instantaneous maximum FC.

    Assumes unlimited charging/discharging power, perfect foresight, free
    curtailment, and a freely chosen initial SOC. Surplus DC power replenishes
    storage with charge losses; deficits draw stored energy with discharge
    losses. An energy-deficient period cannot repeat indefinitely. Two periods
    cover the largest drawdown crossing the trace boundary. No SOC window is
    supplied by the FCEV defaults, so the result is not nominal capacity.
    """
    demand, regeneration = np.asarray(demand_kw, float), np.asarray(
        regeneration_kw, float
    )
    if demand.ndim != 1 or demand.size == 0 or demand.shape != regeneration.shape:
        raise ValueError("Expected matching nonempty one-second power traces.")
    if (
        not np.isfinite(demand).all()
        or not np.isfinite(regeneration).all()
        or np.any(demand < 0)
        or np.any(regeneration < 0)
        or not np.isfinite(net_stack_kw)
        or net_stack_kw < 0
        or not 0 < eta_c <= 1
        or not 0 < eta_d <= 1
    ):
        raise ValueError("Invalid trace, stack power, or storage efficiency.")
    deficit = demand - regeneration - net_stack_kw
    stored_draw = np.maximum(deficit, 0) / eta_d + np.minimum(deficit, 0) * eta_c
    if stored_draw.sum() > 1e-8:
        return None
    cumulative_draw = np.r_[0, np.cumsum(np.tile(stored_draw, 2))] / 3600
    return float(np.max(cumulative_draw - np.minimum.accumulate(cumulative_draw)))


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for package in ("carculator_utils", "carculator", "carculator_truck"):
        sys.path.insert(0, str(ROOT.parent / package))
    from carculator import CarInputParameters, CarModel
    from carculator_truck import TruckInputParameters, TruckModel
    from carculator_utils.array import fill_xarray_from_input_parameters

    rows, snapshots, manifests, parameter_sources = [], {}, {}, {}
    for family, label, input_cls, model_cls in (
        ("car", "pass_cars", CarInputParameters, CarModel),
        ("truck", "trucks", TruckInputParameters, TruckModel),
    ):
        path = ROOT.parent / (
            f"premise/premise/data/additional_inventories/lci-{label}.parameters.csv"
        )
        with path.open() as stream:
            installed = {
                r["size"]: r
                for r in csv.DictReader(stream)
                if r["powertrain"] == "FCEV"
            }
        inputs = input_cls()
        inputs.static()
        _, array = fill_xarray_from_input_parameters(
            inputs,
            scope={"size": sorted(installed), "powertrain": ["FCEV"], "year": [2020]},
        )
        kwargs = (
            {"starts_per_day": 1.8}
            if family == "car"
            else {"cycle": "Regional delivery"}
        )
        model = model_cls(array, country="CH", **kwargs)
        model.set_all()
        for size in sorted(installed):
            selection = dict(size=size, powertrain="FCEV", year=2020, value=0)
            cell = model.array.sel(selection)
            p = {str(k): float(cell.sel(parameter=k)) for k in cell.parameter.values}
            trace = model.energy.sel(selection)
            t = lambda name: np.asarray(trace.sel(parameter=name), float)
            demand = (t("motive energy") + t("auxiliary energy")) * p[
                "fuel cell system efficiency"
            ]
            auxiliaries = t("auxiliary energy") * p["fuel cell system efficiency"]
            eta_c, eta_d = (
                p["battery charge efficiency"],
                p["battery discharge efficiency"],
            )
            regeneration = -t("recuperated energy") / (eta_c * eta_d)
            # Independent wheel -> shaft -> DC identity, including auxiliaries.
            independently_required = (
                t("motive energy at wheels")
                / t("transmission efficiency")
                / t("engine efficiency")
                + auxiliaries
            )
            np.testing.assert_allclose(
                demand, independently_required, rtol=2e-6, atol=1e-6
            )
            np.testing.assert_allclose(
                t("engine efficiency"), p["electric motor efficiency"], rtol=2e-6
            )
            for field in (
                "power",
                "fuel cell power",
                "battery power",
                "electric energy stored",
                "energy battery mass",
                "TtW energy",
            ):
                np.testing.assert_allclose(
                    p[field],
                    float(installed[size][field]),
                    rtol=2e-6,
                    err_msg=f"Installed template mismatch: {family} {size} {field}",
                )
            rated_dc, net_fc, buffer = dc_rating(
                p["electric power"],
                p["electric motor efficiency"],
                float(auxiliaries.max()),
                p["fuel cell power"],
                p["fuel cell own consumption"],
            )
            cycle_buffer = np.maximum(demand - net_fc, 0)
            shaft = t("motive energy at wheels") / t("transmission efficiency")
            lower_bound = storage_lower_bound(
                demand, regeneration, net_fc, eta_c, eta_d
            )
            rows.append(
                dict(
                    family=family,
                    size=size,
                    year=2020,
                    cycle="WLTC" if family == "car" else "Regional delivery",
                    motor_shaft_kw=p["electric power"],
                    motor_efficiency=p["electric motor efficiency"],
                    gross_stack_kw=p["fuel cell power"],
                    net_stack_kw=net_fc,
                    recorded_buffer_kw=p["battery power"],
                    nominal_kwh=p["electric energy stored"],
                    cell_kg=p["battery cell mass"],
                    pack_kg=p["energy battery mass"],
                    peak_auxiliary_dc_kw=float(auxiliaries.max()),
                    rated_motor_plus_auxiliary_dc_kw=rated_dc,
                    rated_dc_gap_kw=rated_dc - net_fc - p["battery power"],
                    required_buffer_at_fixed_stack_kw=buffer,
                    required_buffer_at_fixed_stack_kw_per_kg_cell=buffer
                    / p["battery cell mass"],
                    required_buffer_at_fixed_stack_power_energy_ratio_per_h=buffer
                    / p["electric energy stored"],
                    alternative_same_dc_share_net_stack_kw=rated_dc
                    * p["fuel cell power share"],
                    alternative_same_dc_share_buffer_kw=rated_dc
                    * (1 - p["fuel cell power share"]),
                    peak_cycle_dc_kw=float(demand.max()),
                    peak_cycle_shaft_kw=float(shaft.max()),
                    cycle_shaft_shortfall_kw=max(
                        float(shaft.max()) - p["electric power"], 0
                    ),
                    cycle_seconds_above_motor_rating=int(
                        np.count_nonzero(shaft > p["electric power"] + 1e-6)
                    ),
                    peak_cycle_buffer_kw=float(cycle_buffer.max()),
                    cycle_seconds_above_recorded_buffer=int(
                        np.count_nonzero(cycle_buffer > p["battery power"] + 1e-6)
                    ),
                    peak_regenerative_dc_kw=float(regeneration.max()),
                    peak_regenerative_dc_kw_per_kg_cell=float(regeneration.max())
                    / p["battery cell mass"],
                    optimistic_usable_storage_lower_bound_kwh=lower_bound,
                    lower_bound_fraction_nominal=(
                        lower_bound / p["electric energy stored"]
                        if lower_bound is not None
                        else None
                    ),
                    declared_battery_dod=p["battery DoD"],
                    current_ttw_kj_per_km=p["TtW energy"],
                )
            )
            snapshots[f"{family}|{size}"] = p
        manifests[family] = dict(
            input_module=sys.modules[input_cls.__module__].__file__,
            model_module=sys.modules[model_cls.__module__].__file__,
            installed_parameters=str(path),
            installed_parameters_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        package = "carculator" if family == "car" else "carculator_truck"
        defaults = ROOT.parent / package / package / "data/default_parameters.json"
        parameter_sources[family] = {
            key: record
            for key, record in json.loads(defaults.read_text()).items()
            if record.get("year") == 2020
            and "FCEV" in record.get("powertrain", [])
            and record["name"]
            in {
                "battery cell power density",
                "battery cell energy density, NMC-622",
                "battery cell mass share",
                "fuel cell power share",
                "fuel cell own consumption",
                "electric motor efficiency",
            }
        }
        print(family, "complete", flush=True)
    source_hashes, commits = {}, {}
    for repo in (ROOT, ROOT.parent / "carculator", ROOT.parent / "carculator_truck"):
        commits[repo.name] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip()
        for path in sorted((repo / repo.name).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".json", ".csv", ".yaml"}:
                source_hashes[str(path.relative_to(ROOT.parent))] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    write_csv(args.output / "power_screen.csv", rows)
    (args.output / "model_snapshot.json").write_text(
        json.dumps(snapshots, indent=2) + "\n"
    )
    (args.output / "parameter_sources.json").write_text(
        json.dumps(parameter_sources, indent=2) + "\n"
    )
    (args.output / "run.json").write_text(
        json.dumps(
            dict(
                python=sys.version,
                executable=sys.executable,
                numpy=np.__version__,
                models=manifests,
                commits=commits,
                source_hashes=source_hashes,
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                templates_checked=len(rows),
                dc_energy_identity_verified=True,
                installed_template_specifications_verified=True,
                inventories_changed=False,
                scenario_databases_regenerated=False,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
