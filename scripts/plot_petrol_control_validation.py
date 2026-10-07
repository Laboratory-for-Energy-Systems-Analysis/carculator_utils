"""Plot public-API petrol control runs separately from the ADAC comparator."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    rows = {
        r["variant"]: r["run"]
        for r in json.loads((args.results / "runs.json").read_text())
    }
    variants = [
        "no_hybrid",
        "start_stop",
        "start_stop_and_fuel_cut",
        "source_drag_and_controls",
        "fuel_cut_no_drag_reserve",
        "tiny_buffer",
    ]
    labels = [
        "Non-hybrid, no controls",
        "Start-stop",
        "Start-stop + fuel cut",
        "Controls + source drag",
        "Controls, zero drag reserve",
        "Controls, tiny buffer",
    ]
    values = [rows[v]["fuel_L_100km"] for v in variants]
    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    bars = ax.barh(labels, values, color=["#4878a8"] + ["#549b85"] * 5)
    ax.bar_label(bars, fmt="%.2f", padding=4)
    ax.axvline(
        5.6, color="#bd792a", linestyle="--", label="ADAC: 5.6 (different protocol)"
    )
    ax.invert_yaxis()
    ax.set_xlim(0, 8)
    ax.set_xlabel("Petrol consumption, L/100 km")
    ax.set_title(
        "Golf · complete WLTC runs with finite-buffer controls\nEngineering settings, not vehicle-specific calibration"
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="lower right")
    for suffix in ["png", "svg"]:
        fig.savefig(args.results / f"comparison.{suffix}", dpi=180)


if __name__ == "__main__":
    main()
