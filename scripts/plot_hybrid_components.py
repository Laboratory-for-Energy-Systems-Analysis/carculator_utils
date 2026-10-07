"""Plot the unfitted hybrid component sensitivity separately from validation."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    args = parser.parse_args()
    results = json.loads((args.data / "results.json").read_text())
    baseline = {
        row["observation_id"]: row
        for row in json.loads((args.baseline / "comparisons.json").read_text())[
            "comparisons"
        ]
    }
    cases = ["corolla_combined", "adac_yaris130_combined", "adac_prius_phev_depleted"]
    variants = [
        "baseline",
        "reference_transmission",
        "atkinson_map",
        "both",
        "reported",
    ]
    labels = [
        "Current baseline",
        "Transmission 0.98",
        "Atkinson map",
        "Both",
        "Reported",
    ]
    colors = ["#176B87", "#57A8A0", "#7F9D50", "#8A6BA8", "#CE7138"]
    fig, ax = plt.subplots(figsize=(11, 6))
    positions = np.arange(len(cases))
    for index, (variant, label, color) in enumerate(zip(variants, labels, colors)):
        values = []
        for case in cases:
            if variant == "baseline":
                value = baseline[case]["model_fuel"]
            elif variant == "reported":
                value = baseline[case]["reported"]
            else:
                selected = [
                    r
                    for r in results
                    if r["observation_id"] == case and r["variant"] == variant
                ]
                assert len(selected) == 1
                assert selected[0]["eligible_for_comparison"]
                value = selected[0]["fuel_L_100km"]
            values.append(value)
        bars = ax.bar(
            positions + (index - 2) * 0.16, values, width=0.15, color=color, label=label
        )
        ax.bar_label(bars, fmt="%.2f", fontsize=8, padding=3)
    ax.set_xticks(positions, ["Corolla hybrid", "Yaris hybrid", "Prius: depleted mode"])
    ax.set_ylabel("L/100 km")
    ax.set_ylim(0, 8.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis="y", alpha=0.15)
    ax.legend(ncols=3, loc="upper left", frameon=False)
    fig.suptitle(
        "2025 hybrid component sensitivity",
        x=0.08,
        ha="left",
        weight="bold",
        fontsize=18,
    )
    fig.text(
        0.08,
        0.91,
        "Unfitted component transfer; model WLTC and measured ADAC Ecotest differ.",
        fontsize=11,
    )
    fig.text(
        0.08,
        0.055,
        "Source: pinned FASTSim 2016 Prius model. Engine map peaks at 38%; transmission assumption is 98%.\nSource hybrid control is not transferred. These are sensitivity results, not calibrated defaults.",
        fontsize=9,
    )
    fig.subplots_adjust(left=0.08, right=0.98, top=0.86, bottom=0.18)
    for extension in ["png", "svg", "pdf"]:
        fig.savefig(args.data / f"hybrid_component_sensitivity.{extension}", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
