"""Check benchmark provenance, coverage, mass matching and unit consistency.

This verifies the saved comparison artifacts, not the validity of vehicle physics.
"""

import argparse
import hashlib
import json
import math
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/_static/energy_validation_2025/expanded"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    """Write a coverage audit after checking every saved run and observation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument(
        "--recorded-commits",
        action="store_true",
        help="Verify model hashes against saved Git revisions instead of the working tree.",
    )
    args = parser.parse_args()
    data = args.data
    read = lambda name: json.loads((data / name).read_text())
    catalog, comparisons, provenance = (
        read("measurements.json"),
        read("comparisons.json"),
        read("provenance.json"),
    )
    runs = read("runs.json")
    paired = comparisons["comparisons"]
    excluded = comparisons["excluded"]
    assert not read("errors.json"), "Unresolved run errors"
    assert (
        digest(data / "measurements.json")
        == provenance["catalog_sha256"]
        == comparisons["catalog_sha256"]
    )
    checked_files = 0
    line_ending_normalizations = []
    for package in provenance["packages"].values():
        for relative, expected in package["sha256"].items():
            package_path = Path(package["path"])
            if args.recorded_commits:
                contents = subprocess.check_output(
                    [
                        "git",
                        "-C",
                        str(package_path.parent),
                        "show",
                        f"{package['git_head']}:{package_path.name}/{relative}",
                    ]
                )
                actual = hashlib.sha256(contents).hexdigest()
                # Git stores LF while some checked-out text resources use CRLF.
                # Accept only a byte-exact match after this specific conversion,
                # and record it rather than weakening the content check.
                if actual != expected and Path(relative).suffix in {
                    ".csv",
                    ".json",
                    ".yaml",
                    ".py",
                }:
                    checkout_bytes = contents.replace(b"\r\n", b"\n").replace(
                        b"\n", b"\r\n"
                    )
                    if hashlib.sha256(checkout_bytes).hexdigest() == expected:
                        actual = expected
                        line_ending_normalizations.append(
                            f"{package_path.name}/{relative}"
                        )
            else:
                actual = digest(package_path / relative)
            assert actual == expected, relative
            checked_files += 1
    for name, expected in provenance["runner_sha256"].items():
        assert digest(ROOT / "scripts" / name) == expected, name
    observation_ids = [o["id"] for o in catalog["observations"]]
    paired_ids = [r["observation_id"] for r in paired]
    excluded_ids = [r["observation_id"] for r in excluded]
    assert len(set(observation_ids)) == len(observation_ids)
    assert Counter(paired_ids + excluded_ids) == Counter(observation_ids)
    for dataset in catalog["datasets"].values():
        for field in [
            "source_url",
            "source_title",
            "cycle_or_route",
            "energy_boundary",
            "charging_losses",
        ]:
            assert dataset.get(field), field
        assert dataset["source_url"].startswith("https://")
    by_run = {r["case"]: r for r in runs}
    assert len(by_run) == len(runs)
    max_mass_error = 0.0
    for run in runs:
        assert run["year"] == 2025
        target = run["requested_driving_mass_kg"]
        for field in ["driving mass", "energy_input_driving_mass_kg"]:
            error = abs(run[field] - target)
            assert error < 0.1, (run["case"], field, error)
            max_mass_error = max(max_mass_error, error)
        assert math.isclose(run["ttw_kWh_100km"], run["TtW energy"] / 36, abs_tol=1e-8)
        if run["fuel_L_100km"]:
            expected = run["TtW energy"] / (
                10 * run["LHV fuel MJ per kg"] * run["fuel density per kg"]
            )
            assert math.isclose(run["fuel_L_100km"], expected, rel_tol=1e-6), run[
                "case"
            ]
        if run["cycle_profile"]:
            assert digest(ROOT / run["cycle_profile"]) == run["cycle_profile_sha256"]
    for row in paired:
        assert by_run[row["model_run_id"]]["eligible_for_comparison"]
        assert (
            row["model_year"] == 2025
            and math.isfinite(row["reported"])
            and row["reported"] > 0
        )
        if row["unit"] == "kWh/100 km":
            run = by_run[row["model_run_id"]]
            assert math.isclose(
                row["model_onboard"], run["battery_terminal_kWh_100km"], rel_tol=1e-9
            )
            assert math.isclose(
                row["model_charging"], run["electricity_kWh_100km"], rel_tol=1e-9
            )
    plot = read("plot_manifest.json")
    assert plot["comparisons_sha256"] == digest(data / "comparisons.json")
    assert Counter(plot["plotted_observations"]) == Counter(paired_ids)
    hydrogen_audited = (data / "hydrogen_bus_plot_manifest.json").exists()
    if hydrogen_audited:
        hydrogen_plot = read("hydrogen_bus_plot_manifest.json")
        assert hydrogen_plot["catalog_sha256"] == digest(data / "measurements.json")
    coverage = {}
    for kind in ["car", "bus", "truck"]:
        dataset_ids = {
            k for k, d in catalog["datasets"].items() if d["vehicle_type"] == kind
        }
        rows = [r for r in paired if r["vehicle_type"] == kind]
        coverage[kind] = {
            "datasets": len(dataset_ids),
            "source_values": sum(
                o["dataset_id"] in dataset_ids for o in catalog["observations"]
            ),
            "paired_values": len(rows),
            "paired_vehicles": len({r["dataset_id"] for r in rows}),
            "model_sizes": sorted({r["model_size"] for r in rows}),
            "model_powertrains": sorted({r["model_powertrain"] for r in rows}),
        }
    result = {
        "catalog_sha256": digest(data / "measurements.json"),
        "comparisons_sha256": digest(data / "comparisons.json"),
        "runs_sha256": digest(data / "runs.json"),
        "model_hash_source": (
            "recorded commits" if args.recorded_commits else "working tree"
        ),
        "checkout_line_ending_normalizations": line_ending_normalizations,
        "hydrogen_context_plot_audited": hydrogen_audited,
        "checked_model_files": checked_files,
        "complete_model_runs": len(runs),
        "paired_values": len(paired),
        "excluded_values": len(excluded),
        "maximum_driving_mass_error_kg": max_mass_error,
        "coverage": coverage,
        "electricity_boundary_counts": dict(
            Counter(r["charging_losses"] for r in paired if r["unit"] == "kWh/100 km")
        ),
        "cycle_match_counts": dict(Counter(r["cycle_match"] for r in paired)),
        "datasets_without_source_content_hash": [
            k for k, d in catalog["datasets"].items() if not d.get("source_sha256")
        ],
        "interpretation": "Artifact consistency passed. Numerical eligibility is not physical validation. Do not pool residuals across fuel units, charging boundaries, vehicles, repeated cycles or mismatched routes.",
    }
    (data / "coverage_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
