"""Run the public petrol-control API on the Golf, without fitting defaults."""

import argparse
import copy
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from carculator_utils.combustion_controls import CombustionControl
from validate_energy_2025 import provenance, run_case

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/_static/energy_validation_2025"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "logs").mkdir()
    catalog = json.loads((DATA / "expanded/measurements.json").read_text())
    config = catalog["datasets"]["adac_golf_petrol"]["model_comparison"]
    historical = json.loads((DATA / "petrol_diagnostics/runs.json").read_text())
    historical = {r["variant"]: r["run"] for r in historical}
    variants = [
        "archived_baseline",
        "no_hybrid",
        "disabled_controls",
        "start_stop",
        "start_stop_and_fuel_cut",
        "source_drag_and_controls",
        "fuel_cut_no_drag_reserve",
        "double_restart_cost",
        "tiny_buffer",
        "controls_vetoed",
    ]
    rows = []
    for variant in variants:
        options = copy.deepcopy(config)
        if variant != "archived_baseline":
            options["inputs"].update(
                {"combustion power share": 1.0, "electric motor power share": 0.0}
            )
        controls = asdict(
            CombustionControl(start_stop=True, deceleration_fuel_cut=True)
        )
        if variant == "start_stop":
            controls["deceleration_fuel_cut"] = False
        if variant == "disabled_controls":
            controls.update(start_stop=False, deceleration_fuel_cut=False)
        if variant == "source_drag_and_controls":
            options["inputs"]["aerodynamic drag coefficient"] = 0.28
        if variant == "fuel_cut_no_drag_reserve":
            controls["engine_drag_power_W"] = 0.0
        if variant == "double_restart_cost":
            controls.update(restart_fuel_kJ=10.0, fuel_resume_kJ=10.0)
        if variant == "tiny_buffer":
            controls["buffer_capacity_kJ"] = 1.0
        if variant == "controls_vetoed":
            controls["warmup_seconds"] = 10000
        if variant not in {"archived_baseline", "no_hybrid"}:
            options["combustion_controls"] = controls
        result = run_case(args.output, "golf_" + variant, **options)
        assert result.get("shaft_power_deficit_max_kW", 0) < 1e-8
        assert result["eligible_for_comparison"]
        assert (
            result["cap_active_seconds"]
            == result["wheel_power_exceeds_rating_seconds"]
            == 0
        )
        assert abs(result["energy_input_driving_mass_kg"] - 1496) < 0.1
        if variant in {
            "archived_baseline",
            "no_hybrid",
            "disabled_controls",
            "controls_vetoed",
        }:
            reference = historical[
                "baseline" if variant == "archived_baseline" else "no_hybrid"
            ]
            assert abs(result["TtW energy"] - reference["TtW energy"]) < 1e-7
        if variant != "archived_baseline":
            assert result["electric power"] == 0
            energy_sum = sum(
                result.get(name + " kJ/km", 0.0)
                for name in [
                    "motive energy",
                    "auxiliary energy",
                    "combustion control energy",
                ]
            )
            assert abs(energy_sum - result["TtW energy"]) < 1e-7
        rows.append(dict(variant=variant, run=result))
    meta = provenance()
    meta.update(
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        interpretation="Full public API runs, all WLTC. Control defaults are engineering assumptions, not a Golf calibration or a matched ADAC test.",
        source="https://assets.adac.de/image/upload/Autodatenbank/Autotest/at6463-vw-golf-15-tsi-life/vw-golf-15-tsi-life.pdf",
        observed_adac_combined_L_100km=5.6,
        control_assumptions=asdict(
            CombustionControl(start_stop=True, deceleration_fuel_cut=True)
        ),
    )
    (args.output / "runs.json").write_text(json.dumps(rows, indent=2) + "\n")
    (args.output / "provenance.json").write_text(json.dumps(meta, indent=2) + "\n")


if __name__ == "__main__":
    main()
