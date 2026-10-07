"""Run mini BEVs unchanged on WLTC and reconstructed ADAC electric traces."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

from validate_energy_2025 import provenance, run_case

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/_static/energy_validation_2025"
IDS = [
    "adac_spring65_combined",
    "adac_fiat500_red_combined",
    "adac_fiat500_prima_combined",
    "adac_fiat500_cabrio_combined",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycles", type=Path, default=DATA / "adac_cycle")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "logs").mkdir()
    catalog_path = DATA / "expanded/measurements.json"
    catalog = json.loads(catalog_path.read_text())
    reconstruction = json.loads((args.cycles / "reconstruction.json").read_text())
    prior = json.loads(
        (DATA / "expanded/calibrated_2025/comparisons.json").read_text()
    )["comparisons"]
    meta = provenance()
    meta.update(
        catalog_sha256=hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
        reconstruction=reconstruction,
        purpose="Cycle-only sensitivity; all vehicle parameters and charging assumptions unchanged",
        script_hashes={
            name: hashlib.sha256(
                Path(__file__).with_name(name).read_bytes()
            ).hexdigest()
            for name in [Path(__file__).name, "validate_energy_2025.py"]
        },
    )
    (args.output / "provenance.json").write_text(json.dumps(meta, indent=2) + "\n")
    runs, comparisons = [], []
    for identifier in IDS:
        observation = next(r for r in catalog["observations"] if r["id"] == identifier)
        dataset = catalog["datasets"][observation["dataset_id"]]
        config = copy.deepcopy(dataset["model_comparison"])
        config["cycle"] = observation.get("model_cycle", config["cycle"])
        config.update(copy.deepcopy(observation.get("model_overrides", {})))
        for variant in ["named_wltc", *reconstruction["variants"]]:
            configuration = copy.deepcopy(config)
            if variant != "named_wltc":
                configuration["cycle_profile"] = str(
                    (args.cycles / (variant + ".csv")).resolve()
                )
            row = run_case(args.output, identifier + "_" + variant, **configuration)
            assert row["eligible_for_comparison"]
            assert abs(row["driving mass"] - config["target_driving_mass"]) < 0.1
            assert (
                abs(row["energy_input_driving_mass_kg"] - config["target_driving_mass"])
                < 0.1
            )
            runs.append(row)
            energy = row["electricity_kWh_100km"]
            if variant == "named_wltc":
                baseline = next(
                    r["model_charging"]
                    for r in prior
                    if r["observation_id"] == identifier
                )
                assert (
                    abs(energy - baseline) < 1e-5
                ), "Baseline changed; investigate before attributing changes to cycle"
            comparisons.append(
                dict(
                    observation_id=identifier,
                    vehicle=dataset["vehicle"],
                    variant=variant,
                    reported_kWh_100km=observation["value"],
                    model_kWh_100km=energy,
                    error_pct=100 * (energy / observation["value"] - 1),
                    distance_km=row["distance_km"],
                    power_exceeded_seconds=row["wheel_power_exceeds_rating_seconds"],
                    source_url=dataset["source_url"],
                )
            )
        named, custom = [
            next(
                r["model_kWh_100km"]
                for r in comparisons
                if r["observation_id"] == identifier and r["variant"] == variant
            )
            for variant in ("named_wltc", "wltc_reference")
        ]
        assert (
            abs(named - custom) < 1e-5
        ), "Custom-cycle adapter differs from named WLTC"
    (args.output / "runs.json").write_text(json.dumps(runs, indent=2) + "\n")
    (args.output / "comparisons.json").write_text(
        json.dumps(comparisons, indent=2) + "\n"
    )
    for row in comparisons:
        print(
            row["observation_id"],
            row["variant"],
            round(row["model_kWh_100km"], 2),
            round(row["error_pct"], 1),
            row["power_exceeded_seconds"],
        )


if __name__ == "__main__":
    main()
