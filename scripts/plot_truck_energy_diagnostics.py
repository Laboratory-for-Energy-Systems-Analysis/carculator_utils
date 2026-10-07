"""Plot truck diagnostics without conflating electrical measurement boundaries."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    rows = json.loads((args.results / "runs.json").read_text())
    lookup = {(r["observation_id"], r["variant"]): r for r in rows}
    fig, axes = plt.subplots(2, 3, figsize=(14, 9), layout="constrained")
    panels = [
        ("eactros_tour_mean", "eActros 600 · 40 t", "heavy"),
        ("volvo_green_truck", "Volvo FH Electric · 40 t", "heavy"),
        ("calstart_smith_ocbc_dc", "Smith Newton · OCBC · battery DC", "dc"),
        ("nrel_mt45_diesel_ocbc", "MT-45 diesel · OCBC", "fuel"),
        ("nrel_mt45_diesel_nycc_x3", "MT-45 diesel · NYCC × 3", "fuel"),
        ("calstart_smith_ocbc_dc", "Smith Newton · OCBC · charging AC", "ac"),
    ]
    for ax, (case, title, kind) in zip(axes.flat, panels):
        base = lookup[case, "baseline"]
        reported = base["reported"]
        if kind == "heavy":
            values = [
                base["run"]["electricity_kWh_100km"],
                base["run"]["battery_terminal_kWh_100km"],
                lookup[case, "flat_same_speed"]["run"]["battery_terminal_kWh_100km"],
                reported,
            ]
            labels = ["Model AC", "Model DC", "Flat DC", "Reported*"]
        else:
            field = {
                "dc": "battery_terminal_kWh_100km",
                "ac": "electricity_kWh_100km",
                "fuel": "fuel_L_100km",
            }[kind]
            values = [
                base["run"][field],
                lookup[case, "source_road_load"]["run"][field],
            ]
            labels = ["Baseline", "Test load"]
            if kind == "fuel":
                values.append(lookup[case, "source_load_no_hybrid"]["run"][field])
                labels.append("No hybrid")
            if kind == "ac":
                reported = 0.88 / 1.609344 * 100
            values.append(reported)
            labels.append("Measured")
        bars = ax.bar(
            labels, values, color=["#4878a8"] * (len(values) - 1) + ["#d48a38"]
        )
        ax.bar_label(bars, fmt="%.1f", padding=3)
        ax.set_ylim(0, max(values) * 1.2)
        ax.set_title(title)
        ax.set_ylabel("L/100 km" if kind == "fuel" else "kWh/100 km")
        ax.tick_params(axis="x", labelsize=9)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(
        "Truck energy diagnostics — unchanged 2025 technology\n*Heavy-truck reported meter boundary unresolved; flat profile is a sensitivity, not the measured route",
        fontsize=13,
    )
    for ext in ("png", "svg"):
        fig.savefig(args.results / f"comparison.{ext}", dpi=180)


if __name__ == "__main__":
    main()
