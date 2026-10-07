"""Plot Golf sensitivity runs and the fuel attributed to operating states."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    rows = json.loads((args.results / "runs.json").read_text())
    runs = {r["variant"]: r for r in rows}
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), layout="constrained")
    variants = [
        "baseline",
        "no_hybrid",
        "source_drag_coefficient",
        "stop_start_probe",
        "stop_start_overrun_reserve5kw",
        "stop_start_overrun_probe",
    ]
    labels = [
        "Archived baseline",
        "No hybrid",
        "No hybrid + source Cd",
        "Start-stop probe",
        "+ Fuel cut, 5 kW reserve",
        "+ Fuel cut, no reserve",
    ]
    values = [runs[v]["run"]["fuel_L_100km"] for v in variants]
    bars = axes[0].barh(labels, values, color=["#4878a8"] * 3 + ["#549b85"] * 3)
    axes[0].bar_label(bars, fmt="%.2f", padding=3)
    axes[0].invert_yaxis()
    axes[0].axvline(
        5.6, color="#bd792a", linestyle="--", label="ADAC 5.6 (different protocol)"
    )
    axes[0].set_xlim(0, 8)
    axes[0].set_xlabel("Petrol, L/100 km")
    axes[0].set_title("Complete WLTC runs · 85 kW · 1,496 kg")
    axes[0].legend(loc="lower right", fontsize=9)
    states = runs["no_hybrid"]["accounting"]["states"]
    names = ["traction", "moving_nontraction", "stopped"]
    motive = [
        states[n]["fuel_equivalent_L_per_100km_whole_cycle"]["motive energy"]
        for n in names
    ]
    auxiliary = [
        states[n]["fuel_equivalent_L_per_100km_whole_cycle"]["auxiliary energy"]
        for n in names
    ]
    axes[1].bar(names, motive, label="Motive fuel", color="#4878a8")
    top = axes[1].bar(
        names,
        auxiliary,
        bottom=motive,
        label="Auxiliary / low-load fuel",
        color="#bd792a",
    )
    axes[1].bar_label(
        top, labels=[f"{m+a:.2f}" for m, a in zip(motive, auxiliary)], padding=3
    )
    axes[1].set_xticks(range(3), ["Traction", "Moving without\ntraction", "Stopped"])
    axes[1].set_ylim(0, 7)
    axes[1].set_ylabel("Contribution to whole-cycle consumption, L/100 km")
    axes[1].set_title("Non-hybrid baseline: fuel by operating state")
    axes[1].legend(loc="upper right", fontsize=9)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(
        "Lower-medium petrol diagnostics — no default calibration\nControl probes preserve auxiliary service energy; restart, thermal and gear controls remain unresolved",
        fontsize=13,
    )
    for ext in ["png", "svg"]:
        fig.savefig(args.results / f"comparison.{ext}", dpi=180)


if __name__ == "__main__":
    main()
