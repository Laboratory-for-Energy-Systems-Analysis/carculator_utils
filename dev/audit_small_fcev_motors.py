"""Offline sensitivity of small FCEV motor ratings; no installed data changes.

The candidate ratings are motor-only proxies, not complete vehicle calibrations.
Run with Python 3.12 and the matched sibling source checkouts.
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
for package in ("carculator_utils", "carculator_truck"):
    sys.path.insert(0, str(ROOT.parent / package))

from carculator_truck import TruckInputParameters, TruckModel
from carculator_utils.array import fill_xarray_from_input_parameters


def screen(model, case, cycle):
    rows = []
    for z, size in enumerate(model.array.coords["size"].values):
        speed = np.nan_to_num(model.ecm.cycle[:, z]) / 3.6
        acceleration = np.zeros_like(speed)
        acceleration[1:-1] = (speed[2:] - speed[:-2]) / 2
        # Shorter size-specific profiles are padded with missing gradients
        # after the stopped endpoint; the energy model treats those as flat.
        angle = np.nan_to_num(model.ecm.gradient[:, z])
        for y, year in enumerate(model.array.year.values):
            selection = dict(size=size, year=year, powertrain="FCEV", value=0)
            cell = model.array.sel(selection)
            p = lambda name: float(cell.sel(parameter=name))
            trace = model.energy.sel(selection)
            t = lambda name: np.asarray(trace.sel(parameter=name), float)
            mass = p("driving mass")
            forces = {
                "inertia": mass * acceleration,
                "rolling": mass
                * 9.81
                * p("rolling resistance coefficient")
                * np.cos(angle)
                * (speed > 0),
                "grade": mass * 9.81 * np.sin(angle) * (speed > 0),
                "drag": 0.5
                * model.ecm.rho_air
                * p("aerodynamic drag coefficient")
                * p("frontal area")
                * speed**2,
            }
            wheels = np.maximum(sum(forces.values()), 0) * speed / 1000
            shaft = wheels / t("transmission efficiency")
            # Independent force reconstruction, final mass and loaded trace.
            np.testing.assert_allclose(
                wheels, t("motive energy at wheels"), rtol=2e-6, atol=1e-5
            )
            np.testing.assert_allclose(
                shaft,
                model.ecm.shaft_power_demand_kw[:, 0, y, 0, z],
                rtol=2e-6,
                atol=1e-5,
            )
            deficit = np.maximum(shaft - p("electric power"), 0)
            np.testing.assert_allclose(
                deficit,
                model.ecm.power_deficit_kw[:, 0, y, 0, z],
                rtol=2e-5,
                atol=2e-5,
            )
            peak = int(np.argmax(shaft))
            row = dict(
                case=case,
                cycle=cycle,
                size=str(size),
                year=int(year),
                motor_kw=p("electric power"),
                peak_shaft_kw=float(shaft.max()),
                shortfall_kw=float(deficit.max()),
                seconds_above_motor=int(np.count_nonzero(deficit > 1e-5)),
                peak_second=peak,
                peak_speed_kmh=float(speed[peak] * 3.6),
                peak_acceleration_m_s2=float(acceleration[peak]),
                peak_grade_percent=float(np.tan(angle[peak]) * 100),
                curb_kg=p("curb mass"),
                driving_kg=mass,
                cargo_kg=p("cargo mass"),
                available_payload_kg=p("available payload"),
                motor_kg=p("electric engine mass"),
                gross_stack_kw=p("fuel cell power"),
                net_stack_kw=p("fuel cell power") / p("fuel cell own consumption"),
                battery_kw=p("battery power"),
                battery_kwh=p("electric energy stored"),
                battery_kg=p("energy battery mass"),
                fuel_kg=p("fuel mass"),
                ttw_kj_km=p("TtW energy"),
            )
            for name, force in forces.items():
                row[f"peak_{name}_wheel_kw"] = float(force[peak] * speed[peak] / 1000)
            rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--baseline-parameters",
        type=Path,
        default=ROOT.parent
        / "premise/premise/data/additional_inventories/lci-trucks.parameters.csv",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for cycle in ("Regional delivery", "Urban delivery", "Long haul"):
        years = [2020, 2050] if cycle == "Regional delivery" else [2020]
        inputs = TruckInputParameters()
        inputs.static()
        _, array = fill_xarray_from_input_parameters(
            inputs,
            scope={
                "size": ["3.5t", "7.5t", "40t"],
                "powertrain": ["FCEV"],
                "year": years,
            },
        )
        for case in ("installed_defaults", "candidate_motor_proxies"):
            baseline_array = array.copy(deep=True)
            if "rated power" in baseline_array.parameter.values:
                baseline_array.loc[dict(parameter="rated power")] = 0
            power = (
                None
                if case == "installed_defaults"
                else {
                    ("FCEV", size, year): rating
                    for size, rating in (("3.5t", 57), ("7.5t", 129))
                    for year in years
                }
            )
            model = TruckModel(baseline_array, country="CH", cycle=cycle, power=power)
            model.set_all()
            rows.extend(screen(model, case, cycle))
    with args.baseline_parameters.open() as stream:
        installed = {
            r["size"]: r for r in csv.DictReader(stream) if r["powertrain"] == "FCEV"
        }
    for row in rows:
        if row["cycle"] == "Regional delivery" and row["year"] == 2020:
            if row["case"] == "installed_defaults":
                for output, field in (
                    ("motor_kw", "power"),
                    ("battery_kwh", "electric energy stored"),
                    ("ttw_kj_km", "TtW energy"),
                ):
                    np.testing.assert_allclose(
                        row[output], float(installed[row["size"]][field]), rtol=2e-6
                    )
        if row["case"] == "candidate_motor_proxies" and row["size"] == "40t":
            baseline = next(
                r
                for r in rows
                if r["case"] == "installed_defaults"
                and all(r[k] == row[k] for k in ("cycle", "size", "year"))
            )
            assert all(row[k] == baseline[k] for k in row if k != "case")
    with (args.output / "motor_screen.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    manifest = dict(
        python=sys.version,
        executable=sys.executable,
        numpy=np.__version__,
        input_module=sys.modules[TruckInputParameters.__module__].__file__,
        model_module=sys.modules[TruckModel.__module__].__file__,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        commits={
            name: subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT.parent / name, text=True
            ).strip()
            for name in ("carculator_utils", "carculator_truck")
        },
        rows=len(rows),
        independent_force_balance_checked=True,
        installed_regional_2020_baseline_checked=True,
        baseline_parameters=str(args.baseline_parameters),
        baseline_parameters_sha256=hashlib.sha256(
            args.baseline_parameters.read_bytes()
        ).hexdigest(),
        unaffected_40t_control_identical=True,
        installed_inventories_changed=False,
        candidate_requires_user_choice=False,
        user_approved_motor_proxies=True,
        future_case="Native 2050 sensitivity; not a transformed Premise database.",
    )
    (args.output / "run.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
