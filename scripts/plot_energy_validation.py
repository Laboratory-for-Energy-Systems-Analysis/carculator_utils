"""Plot saved audit comparisons; requires matplotlib, separate from the model run."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "results", type=Path, help="Directory containing comparisons.json"
    )
    args = parser.parse_args()
    records = json.loads((args.results / "comparisons.json").read_text())
    rows = {r["case"]: r for r in records}
    panels = [
        (
            "Cars · WLTC vs WLTP",
            "L/100 km",
            [
                ("golf-petrol", "Petrol / Golf"),
                ("golf-diesel", "Diesel / Golf"),
                ("corolla-hybrid", "Hybrid / Corolla"),
            ],
            "2025 models with approximate published mass and power",
        ),
        (
            "Diesel bus · SORT2",
            "L/100 km",
            [
                ("bus-ICEV-d-SORT2", "Default 13 m class"),
                ("bus-diesel-SORT2-approx-test-load", "Approx. test load"),
            ],
            "2025 model vs 2017 measurement; 13 m vs 12 m vehicle",
        ),
        (
            "Diesel truck · different routes",
            "L/100 km",
            [
                ("baseline-truck-40t-ICEV-d-Long_haul", "Default load (27.6 t)"),
                ("truck-31t", "Adjusted load (31 t)"),
            ],
            "VECTO-derived Long haul vs Green Truck 2025 road test",
        ),
        (
            "Electric bus · SORT2",
            "kWh/100 km onboard",
            [
                ("bus-BEV-depot-SORT2", "Default auxiliaries"),
                ("bus-BEV-depot-SORT2-no-hvac", "HVAC off"),
            ],
            "2025 model vs 2017 measurement; exact test conditions unknown",
        ),
    ]
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
        }
    )
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    for ax, (title, unit, cases, note) in zip(axes.flat, panels):
        for i, (case, label) in enumerate(cases):
            row = rows[case]
            center = (row["reported_min"] + row["reported_max"]) / 2
            ax.barh(
                i,
                row["model"],
                height=0.44,
                color="#237a9b",
                zorder=2,
                label="Model" if i == 0 else None,
            )
            ax.errorbar(
                center,
                i,
                xerr=(row["reported_max"] - row["reported_min"]) / 2,
                fmt="D",
                ms=6,
                color="#b24623",
                capsize=7,
                lw=2,
                zorder=3,
                label="Published value/range" if i == 0 else None,
            )
            ax.text(
                row["model"] + 0.012 * max(row["model"], center),
                i + 0.26,
                f"{row['model']:.2f}",
                va="center",
                fontsize=9,
                color="#14566d",
            )
        ax.set_yticks(range(len(cases)), [label for _, label in cases])
        ax.invert_yaxis()
        ax.set_xlabel(unit)
        ax.set_title(title, loc="left", fontweight="bold", pad=12)
        ax.grid(axis="x", alpha=0.18, zorder=0)
        ax.set_xlim(left=0)
        ax.margins(y=0.3, x=0.15)
        ax.text(0, -0.31, note, transform=ax.transAxes, fontsize=8, color="#555555")
    axes.flat[0].legend(
        loc="lower left", bbox_to_anchor=(0, 1.55), ncol=2, frameon=False, fontsize=9
    )
    fig.suptitle(
        "Energy model audit · 2025 vehicles",
        x=0.07,
        y=0.985,
        ha="left",
        fontsize=19,
        fontweight="bold",
    )
    fig.text(
        0.07,
        0.936,
        "Context comparisons, not certification: vehicle specifications and test conditions differ.",
        fontsize=10,
        color="#555555",
    )
    fig.subplots_adjust(
        left=0.18, right=0.97, bottom=0.14, top=0.77, hspace=0.85, wspace=0.68
    )
    fig.text(
        0.07,
        0.02,
        "Sources: Volkswagen MY2025; Toyota MY25; Gis et al. (2017), table 1; Green Truck 2025.\n"
        "See energy_validation_2025.rst and benchmarks JSON for source URLs, masses and limitations.",
        fontsize=8,
        color="#555555",
    )
    for suffix in ["png", "pdf"]:
        fig.savefig(args.results / f"comparison.{suffix}", dpi=180, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
