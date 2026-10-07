"""Create a measurement catalog with explicit, unfitted component priors.

This is a sensitivity experiment, not a native-default update or a calibration.
All measurement values and comparison eligibility rules are preserved.
"""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

FASTSIM_COMMIT = "63808be8d09cb191047b536a2b9b7f883dbbd0c3"
FASTSIM_ROOT = (
    f"https://github.com/NatLabRockies/fastsim/blob/{FASTSIM_COMMIT}/python/fastsim/"
)


def prepare(catalog, *, motor_maps=False):
    result = copy.deepcopy(catalog)
    result["component_efficiency_experiment"] = {
        "status": "unfitted sensitivity experiment; not final calibration",
        "battery_round_trip_efficiency": 0.97,
        "battery_one_way_efficiency": math.sqrt(0.97),
        "battery_source": [
            FASTSIM_ROOT + "resources/vehdb/2016_TOYOTA_Prius_Two.csv",
            FASTSIM_ROOT + "resources/vehdb/2022_Tesla_Model_3_RWD.csv",
            FASTSIM_ROOT + "simdrive.py#L1510-L1515",
        ],
        "transfer_limit": "Source vehicle-model assumptions, not measured universal efficiencies; transfer to buses and trucks is an explicit hypothesis.",
        "charger_efficiency": 0.90,
        "charger_basis": "Unfitted engineering assumption, AC input to battery-terminal DC; separate from battery charge efficiency.",
        "electric_drive_efficiency": None if motor_maps else 0.90,
        "electric_transmission_efficiency": None if motor_maps else 0.97,
        "drive_basis": "Unfitted cycle-average motor/inverter and transmission assumptions; no aggregate TTW fit applied as a component map.",
    }
    for observation in result["observations"]:
        dataset = result["datasets"][observation["dataset_id"]]
        config = copy.deepcopy(dataset.get("model_comparison"))
        if not config:
            continue
        config["cycle"] = observation.get("model_cycle", config["cycle"])
        config.update(copy.deepcopy(observation.get("model_overrides", {})))
        powertrain = config["powertrain"]
        electric = powertrain.startswith("BEV") or powertrain == "PHEV-e"
        hybrid = powertrain.startswith(("HEV", "PHEV-c"))
        if electric or hybrid or powertrain == "FCEV":
            config.setdefault("inputs", {}).update(
                {
                    "battery charge efficiency": math.sqrt(0.97),
                    "battery discharge efficiency": math.sqrt(0.97),
                }
            )
        if electric:
            config["inputs"]["charger efficiency"] = 0.90
            if not motor_maps:
                config["engine_efficiency"] = 0.90
                config["transmission_efficiency"] = 0.97
        observation["model_overrides"] = config
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--retain-motor-maps", action="store_true")
    args = parser.parse_args()
    result = prepare(
        json.loads(args.catalog.read_text()), motor_maps=args.retain_motor_maps
    )
    result["component_efficiency_experiment"]["source_catalog_sha256"] = hashlib.sha256(
        args.catalog.read_bytes()
    ).hexdigest()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
