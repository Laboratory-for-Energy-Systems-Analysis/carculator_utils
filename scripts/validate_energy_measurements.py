"""Run the expanded measurement catalog with documented driving-mass targets.

Requires the Python 3.12 model environment. Results include failures and exclusions;
matching mass does not match road load, control, route, or environmental conditions.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from validate_energy_2025 import provenance, run_case

DATA = (
    Path(__file__).resolve().parents[1] / "docs/_static/energy_validation_2025/expanded"
)


def write_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )


def write_csv(path, records):
    fields = list(dict.fromkeys(key for record in records for key in record))
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    key: (
                        json.dumps(value, ensure_ascii=False)
                        if isinstance(value, (dict, list))
                        else value
                    )
                    for key, value in record.items()
                }
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DATA / "measurements.json")
    parser.add_argument(
        "--output", type=Path, required=True, help="New output directory"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "logs").mkdir()
    catalog = json.loads(args.catalog.read_text())
    metadata = provenance()
    metadata["catalog_sha256"] = hashlib.sha256(args.catalog.read_bytes()).hexdigest()
    metadata["runner_sha256"] = {
        name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in ["validate_energy_measurements.py", "validate_energy_2025.py"]
    }
    metadata["mass_tolerance_kg"] = 0.1
    metadata["numerical_note"] = (
        "Benchmark-only sizing tolerance 1e-8; full set_all() calls with current "
        "physics and availability rules. Capture driving mass passed to the final "
        "energy calculation, as well as the final stored mass. Battery terminal DC and stored energy are reported separately. No efficiency fitting."
    )
    write_json(args.output / "provenance.json", metadata)
    runs, comparisons, excluded, errors, flat = [], [], [], [], []
    run_cache = {}
    for observation in catalog["observations"]:
        dataset = catalog["datasets"][observation["dataset_id"]]
        flat.append({**dataset, **observation})
        config = dataset.get("model_comparison")
        reason = None
        if observation.get("comparison_exclusion"):
            reason = observation["comparison_exclusion"]
        elif observation["measure_type"] != "absolute_consumption":
            reason = "Relative change has no measured absolute counterpart."
        elif not config:
            reason = "No documented driving mass and corresponding model configuration."
        elif observation["scope"] not in ["combined", "cycle"]:
            reason = "No model trace/conditioning for this phase, route day, or temperature bin."
        if reason:
            excluded.append({"observation_id": observation["id"], "reason": reason})
            continue
        config = dict(config)
        config["cycle"] = observation.get("model_cycle", config["cycle"])
        config.update(observation.get("model_overrides", {}))
        case = observation["id"]
        try:
            cache_key = json.dumps(config, sort_keys=True)
            if cache_key not in run_cache:
                run_cache[cache_key] = run_case(args.output, case, **config)
                runs.append(run_cache[cache_key])
            run = run_cache[cache_key]
            target = config["target_driving_mass"]
            for field in ["driving mass", "energy_input_driving_mass_kg"]:
                if abs(run[field] - target) >= 0.1:
                    raise ValueError(f"Mass mismatch: {field}")
            if not run["eligible_for_comparison"]:
                excluded.append(
                    {
                        "observation_id": case,
                        "reason": "Completed full model run fails consumption/availability eligibility; see runs.json. A zeroed result is not plotted as physical consumption.",
                    }
                )
                continue
            electric = observation["unit"] == "kWh/100 km"
            if observation["unit"] not in ["kWh/100 km", "L/100 km", "kg/100 km"]:
                raise ValueError(
                    "Add an explicit gas/mass unit conversion before comparison"
                )
            comparisons.append(
                {
                    "observation_id": case,
                    "model_run_id": run["case"],
                    "dataset_id": observation["dataset_id"],
                    "vehicle": dataset["vehicle"],
                    "vehicle_type": dataset["vehicle_type"],
                    "powertrain": dataset["powertrain"],
                    "model_powertrain": config["powertrain"],
                    "operating_mode": observation.get("operating_mode"),
                    "model_year": 2025,
                    "model_size": config["size"],
                    "model_cycle": run["cycle"],
                    "reported_cycle": observation.get(
                        "cycle_or_route", dataset["cycle_or_route"]
                    ),
                    "cycle_match": observation.get(
                        "cycle_match", dataset["cycle_match"]
                    ),
                    "sampling_note": observation.get("sampling_note"),
                    "mass_basis": dataset["mass_basis"],
                    "target_driving_mass_kg": target,
                    "model_driving_mass_kg": run["driving mass"],
                    "energy_input_driving_mass_kg": run["energy_input_driving_mass_kg"],
                    "reported": observation["value"],
                    "unit": observation["unit"],
                    "model_fuel": (
                        None
                        if electric
                        else run[
                            (
                                "fuel_kg_100km"
                                if observation["unit"] == "kg/100 km"
                                else "fuel_L_100km"
                            )
                        ]
                    ),
                    "model_onboard": (
                        run["battery_terminal_kWh_100km"] if electric else None
                    ),
                    "model_stored_energy": run["ttw_kWh_100km"] if electric else None,
                    "model_onboard_boundary": "net DC at battery terminals",
                    "model_charging": (
                        run["electricity_kWh_100km"] if electric else None
                    ),
                    "charging_losses": observation.get(
                        "charging_losses", dataset["charging_losses"]
                    ),
                    "source_boundary": observation.get(
                        "energy_boundary", dataset["energy_boundary"]
                    ),
                    "source_url": dataset["source_url"],
                    "mass_reconstruction": dataset.get("mass_reconstruction"),
                    "remaining_mismatches": dataset["remaining_mismatches"],
                    "motive_input_removed_pct": run["motive_input_removed_pct"],
                }
            )
        except Exception as exc:
            failure = {"observation_id": case, "reason": f"{type(exc).__name__}: {exc}"}
            errors.append(failure)
            excluded.append(failure)
            print(failure, flush=True)
        finally:
            write_json(args.output / "runs.json", runs)
            write_json(args.output / "errors.json", errors)
    write_csv(args.output / "runs.csv", runs)
    write_csv(args.output / "measurements.csv", flat)
    write_csv(args.output / "comparisons.csv", comparisons)
    write_json(
        args.output / "comparisons.json",
        {
            "catalog_sha256": metadata["catalog_sha256"],
            "comparisons": comparisons,
            "excluded": excluded,
        },
    )
    print(
        f"{len(runs)} complete model runs; {len(comparisons)} paired observations; "
        f"{len(excluded)} unpaired; {len(errors)} run errors."
    )


if __name__ == "__main__":
    main()
