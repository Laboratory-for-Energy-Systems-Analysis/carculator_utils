"""Run unfitted hybrid component-transfer sensitivities against saved observations.

Download the pinned FASTSim vehicle CSV named in SOURCE_URL and pass its path
with --reference. This experiment does not modify native model defaults.
"""

import argparse
import ast
import copy
import csv
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from carculator_utils.energy_consumption import get_efficiency_coefficients
from validate_energy_2025 import provenance, run_case

SOURCE_URL = (
    "https://github.com/NatLabRockies/fastsim/blob/"
    "63808be8d09cb191047b536a2b9b7f883dbbd0c3/"
    "python/fastsim/resources/vehdb/2016_TOYOTA_Prius_Two.csv"
)
SOURCE_SHA256 = "b269debfd02bbad043e01f422f62e947645a7f4f6c3a32a23f80839dda0c0298"
DATA = (
    Path(__file__).resolve().parents[1] / "docs/_static/energy_validation_2025/expanded"
)
OBSERVATIONS = [
    "corolla_combined",
    "adac_yaris130_combined",
    "adac_prius_phev_depleted",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=DATA / "measurements.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reference_bytes = args.reference.read_bytes()
    if hashlib.sha256(reference_bytes).hexdigest() != SOURCE_SHA256:
        raise ValueError("FASTSim reference checksum does not match the pinned source.")
    params = {
        row[1]: row[2]
        for row in csv.reader(reference_bytes.decode().splitlines())
        if len(row) > 2
    }
    curve = dict(
        zip(
            ast.literal_eval(params["fc_pwr_out_perc"]),
            ast.literal_eval(params["fc_eff_map"]),
        )
    )
    transmission = float(params["trans_eff"])
    catalog_bytes = args.catalog.read_bytes()
    catalog = json.loads(catalog_bytes)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "logs").mkdir()
    rows = []
    for observation_id in OBSERVATIONS:
        observation = next(
            item for item in catalog["observations"] if item["id"] == observation_id
        )
        dataset = catalog["datasets"][observation["dataset_id"]]
        config = copy.deepcopy(dataset["model_comparison"])
        config["cycle"] = observation.get("model_cycle", config["cycle"])
        config.update(copy.deepcopy(observation.get("model_overrides", {})))
        for variant in ["reference_transmission", "atkinson_map", "both"]:
            configuration = copy.deepcopy(config)
            if variant in ["reference_transmission", "both"]:
                configuration["transmission_efficiency"] = transmission

            def maps(kind):
                coefficients = get_efficiency_coefficients(kind)
                if kind == "car":
                    # Reconstruct the original ordinary-petrol baseline for this
                    # controlled experiment, even after architecture-map adoption.
                    coefficients.pop("powertrain_categories", None)
                if kind == "car" and variant in ["atkinson_map", "both"]:
                    coefficients["gasoline"]["engine"] = curve.copy()
                    coefficients["gasoline"][
                        "engine_map_reference_transmission_efficiency"
                    ] = 1.0
                return coefficients

            with patch(
                "carculator_utils.energy_consumption.get_efficiency_coefficients", maps
            ):
                row = run_case(
                    args.output, observation_id + "_" + variant, **configuration
                )
            row.update(
                observation_id=observation_id,
                variant=variant,
                reported=observation["value"],
                cycle_match=dataset["cycle_match"],
            )
            rows.append(row)
    metadata = provenance()
    metadata.update(
        source_url=SOURCE_URL,
        source_sha256=SOURCE_SHA256,
        catalog_sha256=hashlib.sha256(catalog_bytes).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        engine_curve=curve,
        transmission_efficiency=transmission,
        omitted_source_control_parameters={
            key: params[key]
            for key in ["min_fc_time_on", "idle_fc_kw", "force_aux_on_fc"]
        },
        status="Unfitted transfer sensitivity from a 2016 Prius component model; not modern-car validation or adopted defaults. Cycle mismatch and differing hybrid control remain.",
    )
    for name, payload in [("results.json", rows), ("provenance.json", metadata)]:
        (args.output / name).write_text(json.dumps(payload, indent=2) + "\n")


if __name__ == "__main__":
    main()
