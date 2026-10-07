"""Plot before/after annual energy results produced by audit_energy_time_trends."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

CASES = [
    ("carculator", "Lower medium", "ICEV-p", "Lower-medium petrol car"),
    ("carculator", "Lower medium", "BEV", "Lower-medium electric car"),
    ("carculator_bus", "13m-city", "BEV-depot", "13 m depot-charged bus"),
    ("carculator_bus", "13m-city", "HEV-d", "13 m hybrid diesel bus"),
    ("carculator_truck", "40t", "BEV", "40 t electric truck"),
    ("carculator_two_wheeler", "Bicycle <25", "BEV", "Electric bicycle (<25 km/h)"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--after-only", action="store_true")
    args = parser.parse_args()
    rows = json.loads(args.results.read_text())
    fig, axes = plt.subplots(3, 2, figsize=(11, 11), constrained_layout=True)
    for ax, (package, size, pt, title) in zip(axes.flat, CASES):
        electric = pt.startswith("BEV")
        metric = "electricity consumption" if electric else "fuel consumption"
        for variant, color, style in [
            ("before", "#b66147", "--"),
            ("after", "#16796b", "-"),
        ]:
            if args.after_only and variant == "before":
                continue
            selected = {
                r["year"]: r
                for r in rows
                if (r["package"], r["size"], r["powertrain"], r["variant"])
                == (package, size, pt, variant)
            }
            years = sorted(y for y in selected if 2020 <= y <= 2030)
            values = [
                (
                    selected[y].get(metric, np.nan) * 100
                    if selected[y]["status"] == "ok"
                    else np.nan
                )
                for y in years
            ]
            ax.plot(
                years,
                values,
                color=color,
                linestyle=style,
                marker="o",
                markersize=3,
                label=variant.capitalize(),
            )
        ax.axvline(2025, color="#888888", alpha=0.4, linewidth=1)
        ax.set_title(title, loc="left", fontsize=12)
        ax.set_ylabel("AC electricity (kWh/100 km)" if electric else "Fuel (L/100 km)")
        ax.set_xticks([2020, 2022, 2025, 2028, 2030])
        ax.grid(alpha=0.18)
        ax.legend(frameon=False)
    fig.suptitle(
        "Consistent energy assumptions around the preserved 2025 anchor", fontsize=15
    )
    fig.supxlabel(
        "Model year · same standard cycle within each panel"
        + ("" if args.after_only else " · gaps indicate failed legacy sizing")
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180)
    fig.savefig(args.output.with_suffix(".svg"))


if __name__ == "__main__":
    main()
