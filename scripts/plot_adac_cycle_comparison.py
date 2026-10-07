"""Plot the graph-reconstructed ADAC cycle sensitivity without model imports."""

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="Cycle directory with sensitivity results",
    )
    args = parser.parse_args()
    rows = json.loads((args.data / "sensitivity/comparisons.json").read_text())
    ids = list(dict.fromkeys(r["observation_id"] for r in rows))

    def values(variant):
        return [
            next(
                r["model_kWh_100km"]
                for r in rows
                if r["observation_id"] == name and r["variant"] == variant
            )
            for name in ids
        ]

    fig, ax = plt.subplots(figsize=(11, 6.4))
    fig.subplots_adjust(left=0.09, right=0.98, top=0.77, bottom=0.27)
    x = np.arange(len(ids))
    width = 0.19
    series = [
        ("WLTC", values("named_wltc"), "#176B87"),
        ("ADAC graph reconstruction", values("adac_graph_nominal"), "#45A6B8"),
        (
            "Slower acceleration probe",
            values("adac_tail_gentle_acceleration"),
            "#8CB77B",
        ),
        (
            "ADAC measurement",
            [
                next(
                    r["reported_kWh_100km"] for r in rows if r["observation_id"] == name
                )
                for name in ids
            ],
            "#CE7138",
        ),
    ]
    for i, (label, y, color) in enumerate(series):
        bars = ax.bar(x + (i - 1.5) * width, y, width, label=label, color=color)
        ax.bar_label(bars, fmt="%.2f", fontsize=9, padding=3)
    ax.set_xticks(
        x,
        ["Dacia Spring 65", "Fiat 500e RED", "Fiat 500e La Prima", "Fiat 500e Cabrio"],
    )
    ax.set_ylabel("Charging electricity (kWh/100 km)")
    ax.set_ylim(0, 20)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis="y", alpha=0.2)
    fig.suptitle(
        "Mini BEVs · effect of reconstructing the ADAC cycle",
        x=0.06,
        ha="left",
        fontsize=18,
        weight="bold",
    )
    fig.legend(
        *ax.get_legend_handles_labels(),
        loc="upper left",
        bbox_to_anchor=(0.05, 0.91),
        ncol=2,
        frameon=False,
    )
    fig.text(
        0.06,
        0.17,
        "All vehicle parameters held fixed; 2025 technology and charging assumptions.\nReconstructed from ADAC's published figure, not an official numerical or measured speed trace.\nNominal graph accelerations exceed rated power briefly; slower probe retimes the ending to 0.25 m/s².\nNeither reconstruction matches measured HVAC, road load, temperature or SOC trajectories.",
        fontsize=10,
        va="top",
        linespacing=1.5,
    )
    cycle, axes = plt.subplots(2, 1, figsize=(11, 7))
    cycle.subplots_adjust(left=0.09, right=0.97, top=0.86, bottom=0.17, hspace=0.38)
    for name, label, color in [
        ("wltc_reference", "Numerical WLTC", "#176B87"),
        ("adac_graph_nominal", "Reconstructed ADAC ending", "#CE7138"),
        ("adac_tail_gentle_acceleration", "Slower acceleration probe", "#77A560"),
    ]:
        data = np.loadtxt(args.data / (name + ".csv"), delimiter=",", skiprows=1)
        for axis in axes:
            axis.plot(data[:, 0], data[:, 1], label=label, color=color, lw=1.3)
    axes[0].set_xlim(0, 2070)
    axes[1].set_xlim(1700, 2070)
    for axis in axes:
        axis.set_ylabel("Speed (km/h)")
        axis.set_xlabel("Time (s)")
        axis.grid(alpha=0.2)
    axes[0].set_title("Complete profiles")
    axes[1].set_title("Ending: numerical WLTC retained through second 1767")
    cycle.suptitle(
        "ADAC electric-cycle reconstruction · source figure 3, April 2021 protocol",
        fontsize=14,
    )
    cycle.legend(
        *axes[0].get_legend_handles_labels(),
        loc="lower center",
        bbox_to_anchor=(0.5, 0.04),
        ncol=3,
        frameon=False,
    )
    for name, figure in [("consumption_comparison", fig), ("cycle_profiles", cycle)]:
        figure.savefig(args.data / (name + ".png"), dpi=160)
        figure.savefig(args.data / (name + ".svg"))
    with PdfPages(args.data / "adac_cycle_comparison.pdf") as pdf:
        pdf.savefig(fig)
        pdf.savefig(cycle)
    with (args.data / "sensitivity/comparisons.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
