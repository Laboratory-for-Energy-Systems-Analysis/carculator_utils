"""Fit one conditional Gillig auxiliary load, withholding Manhattan validation.

Fits equal relative-error weights on OCBC and HD-UDDS. All other inputs stay
fixed. This identifies a conditional total base auxiliary load, not individual
accessories or a universal bus default. Full reruns must validate the linear
energy prediction before any default is adopted.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

TRAINING = ("gillig_ocbc", "gillig_hd-udds")
VALIDATION = "gillig_manhattan"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("results", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    comparisons = json.loads((args.results / "comparisons.json").read_text())[
        "comparisons"
    ]
    comparisons = {row["observation_id"]: row for row in comparisons}
    runs = {
        row["case"]: row for row in json.loads((args.results / "runs.json").read_text())
    }
    records = []
    for identifier in (*TRAINING, VALIDATION):
        comparison = comparisons[identifier]
        run = runs[comparison["model_run_id"]]
        if "AC input to charger" not in comparison["source_boundary"]:
            raise ValueError("Calibration requires recharge AC measurements.")
        # W * s / km -> kWh/100 km, including stored and charging boundaries.
        slope = (
            run["finite_seconds"]
            / run["distance_km"]
            / 36000
            / (
                run["battery charge efficiency"]
                * run["battery discharge efficiency"]
                * run["charger efficiency"]
            )
        )
        records.append(
            {
                "observation_id": identifier,
                "role": "training" if identifier in TRAINING else "held-out cycle",
                "reported_kWh_100km": comparison["reported"],
                "baseline_kWh_100km": comparison["model_charging"],
                "slope_kWh_100km_per_W": slope,
                "baseline_auxiliary_W": run["auxiliary power base demand"],
            }
        )
    base = records[0]["baseline_auxiliary_W"]
    assert all(row["baseline_auxiliary_W"] == base for row in records)
    training = records[:2]
    slopes = np.array(
        [r["slope_kWh_100km_per_W"] / r["reported_kWh_100km"] for r in training]
    )
    residuals = np.array(
        [
            (r["reported_kWh_100km"] - r["baseline_kWh_100km"])
            / r["reported_kWh_100km"]
            for r in training
        ]
    )
    delta = float(slopes @ residuals / (slopes @ slopes))
    fitted = base + delta
    if not 0 < fitted < 15000:
        raise ValueError(
            "Fitted base auxiliary load falls outside the exploratory 0–15 kW range."
        )
    for row in records:
        row["predicted_kWh_100km"] = (
            row["baseline_kWh_100km"] + delta * row["slope_kWh_100km_per_W"]
        )
    catalog["conditional_bus_auxiliary_calibration"] = {
        "source_catalog_sha256": hashlib.sha256(args.catalog.read_bytes()).hexdigest(),
        "source_comparisons_sha256": hashlib.sha256(
            (args.results / "comparisons.json").read_bytes()
        ).hexdigest(),
        "parameter": "auxiliary power base demand",
        "fitted_W": fitted,
        "objective": "sum of squared relative errors on two training cycles",
        "status": "conditional fit; verify full reruns and motor-rating sensitivity before adoption",
        "limitations": [
            "One bus; held-out cycle is not an independent vehicle.",
            "Unknown actual motor rating and auxiliary traces.",
            "Transfer beyond this bus is not established.",
        ],
        "predictions": records,
    }
    catalog["observations"] = [
        row for row in catalog["observations"] if row["id"] in (*TRAINING, VALIDATION)
    ]
    for row in catalog["observations"]:
        row["model_overrides"]["inputs"]["auxiliary power base demand"] = fitted
    with args.output.open("x") as stream:
        json.dump(catalog, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps(catalog["conditional_bus_auxiliary_calibration"], indent=2))


if __name__ == "__main__":
    main()
