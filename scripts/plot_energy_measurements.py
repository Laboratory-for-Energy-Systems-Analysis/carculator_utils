"""Create paired bar charts from saved 2025 runs and published consumption data.

Requires matplotlib, but does not import or rerun any vehicle model. Run with::

    python scripts/plot_energy_measurements.py

The JSON/CSV outputs retain the source and model mapping for every plotted pair.
These are screening comparisons, not matched vehicle-validation experiments.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Patch

DATA = Path(__file__).resolve().parents[1] / "docs/_static/energy_validation_2025"
MODEL = "#176B87"
LOSSES = "#A7D3E0"
PUBLISHED = "#CE7138"
TEXT = "#283C48"

# The first column is a source ID, the second an existing model-run ID.
# Reusing a class run for several observations does not create independent runs.
ORIGINAL = [
    ("golf-petrol-2025", "golf-petrol", "fuel_cars", "Golf petrol · WLTP [1]"),
    ("golf-diesel-2025", "golf-diesel", "fuel_cars", "Golf diesel · WLTP [1]"),
    ("corolla-hybrid-my25", "corolla-hybrid", "fuel_cars", "Corolla hybrid · WLTP [2]"),
    (
        "sort2-diesel-2017",
        "bus-diesel-SORT2-approx-test-load",
        "fuel_heavy",
        "Diesel bus · SORT 2 [3]",
    ),
    ("green-truck-2025", "truck-31t", "fuel_heavy", "Diesel trucks · road test [4]"),
    (
        "sort2-electric-2017",
        "bus-BEV-depot-SORT2",
        "electric_buses",
        "2017 bus · SORT 2 · onboard [3]",
    ),
]
ADDITIONAL = [
    ("golf_combined", "golf-petrol", "fuel_cars", "Golf petrol · Ecotest [5]"),
    ("corolla_combined", "corolla-hybrid", "fuel_cars", "Corolla estate · Ecotest [6]"),
    (
        "id3_combined",
        "baseline-car-Lower_medium-BEV-WLTC",
        "electric_cars",
        "ID.3 GTX · compact-class proxy [7]",
    ),
    (
        "ioniq6_combined",
        "baseline-car-Medium-BEV-WLTC",
        "electric_cars",
        "Ioniq 6 · medium-class proxy [8]",
    ),
    (
        "ev3_combined",
        "baseline-car-Lower_medium-BEV-WLTC",
        "electric_cars",
        "EV3 · compact-class proxy [9]",
    ),
    *[
        (
            f"byd_sort{i}",
            f"bus-BEV-depot-SORT{i}",
            "electric_buses",
            f"BYD · SORT {i} · meter unclear [10]",
        )
        for i in [1, 2, 3]
    ],
    (
        "eactros_tour_mean",
        "baseline-truck-40t-BEV-Long_haul",
        "electric_trucks",
        "eActros 600 · summer tour [11]",
    ),
    (
        "volvo_green_truck",
        "baseline-truck-40t-BEV-Long_haul",
        "electric_trucks",
        "Volvo FH Electric · road test [12]",
    ),
]


def read_records(folder):
    """Join sources to eligible saved runs without imputing missing observations."""
    with (folder / "runs.csv").open(newline="", encoding="utf-8") as stream:
        runs = {row["case"]: row for row in csv.DictReader(stream)}
    original = json.loads((folder / "benchmarks.json").read_text())
    original = {row["id"]: row for row in original["benchmarks"]}
    catalog = json.loads((folder / "additional_measurements.json").read_text())
    observations = {row["id"]: row for row in catalog["observations"]}
    records = []
    for kind, specifications in [("original", ORIGINAL), ("additional", ADDITIONAL)]:
        for source_id, case, panel, label in specifications:
            run = runs[case]
            if run["eligible_for_comparison"] != "True":
                raise ValueError(f"Ineligible model run: {case}")
            electric = panel.startswith("electric")
            record = {
                "panel": panel,
                "label": label,
                "source_catalog": kind,
                "source_id": source_id,
                "model_case": case,
                "model_year": int(run["year"]),
                "model_size": run["size"],
                "model_cycle": run["cycle"],
                "model_driving_mass_kg": float(run["driving mass"]),
                "unit": "kWh/100 km" if electric else "L/100 km",
                "model_fuel": None if electric else float(run["fuel_L_100km"]),
                "model_onboard": float(run["ttw_kWh_100km"]) if electric else None,
                "model_charging": (
                    float(run["electricity_kWh_100km"]) if electric else None
                ),
            }
            if kind == "original":
                source = original[source_id]
                record.update(
                    reported_min=source["reported_min"],
                    reported_max=source["reported_max"],
                    source_url=source["source"],
                    source_boundary="onboard" if electric else "fuel volume",
                    source_conditions=source["conditions"],
                    comparability=source["comparability"],
                )
            else:
                observation = observations[source_id]
                dataset = catalog["datasets"][observation["dataset_id"]]
                if observation["measure_type"] != "absolute_consumption":
                    raise ValueError(f"Absolute chart cannot include {source_id}")
                if observation["unit"] != record["unit"]:
                    raise ValueError(f"Unit mismatch for {source_id}")
                record.update(
                    reported_min=observation["value"],
                    reported_max=observation["value"],
                    source_url=dataset["source_url"],
                    source_boundary=dataset["energy_boundary"],
                    source_conditions=dataset["conditions"],
                    source_measurement_period=dataset["measurement_period"],
                    source_publication_date=dataset["publication_date"],
                    source_test_mass_kg=dataset["test_gross_mass_kg"],
                    comparability=dataset["validation_use"],
                )
            record["reported_bar"] = (
                record["reported_min"] + record["reported_max"]
            ) / 2
            if electric and record["model_charging"] < record["model_onboard"]:
                raise ValueError(f"Negative charging losses for {case}")
            records.append(record)

    plotted = {item[0] for item in ADDITIONAL}
    reasons = {
        "phase": "No saved model run reproduces the ADAC phase and conditioning.",
        "temperature_bin": "No saved model run matches these fleet routes, loads and temperature bins.",
        "route_day": "No saved run reproduces this daily route and terrain; tour mean is shown.",
        "season_comparison": "Relative percentage, without an absolute measured consumption counterpart.",
    }
    excluded = [
        {"source_id": row["id"], "reason": reasons[row["scope"]]}
        for row in observations.values()
        if row["id"] not in plotted
    ]
    return records, excluded


def panel(ax, rows, title, note, electric=False):
    """Draw paired bars, preserving zero baselines and the electrical boundaries."""
    y = np.arange(len(rows))
    gap, height = 0.19, 0.31
    published = np.array([r["reported_bar"] for r in rows])
    observed_range = np.array(
        [(r["reported_max"] - r["reported_min"]) / 2 for r in rows]
    )
    onboard = np.array([r["model_onboard" if electric else "model_fuel"] for r in rows])
    total = np.array([r["model_charging"] for r in rows]) if electric else onboard
    max_value = max(total.max(), max(r["reported_max"] for r in rows))
    offset = max_value * 0.017
    ax.barh(y - gap, onboard, height, color=MODEL, zorder=3)
    if electric:
        ax.barh(y - gap, total - onboard, height, left=onboard, color=LOSSES, zorder=3)
    ax.barh(y + gap, published, height, color=PUBLISHED, zorder=3)
    # These whiskers are published variant/test ranges, not statistical errors.
    ranged = observed_range > 0
    if ranged.any():
        ax.errorbar(
            published[ranged],
            y[ranged] + gap,
            xerr=observed_range[ranged],
            fmt="none",
            ecolor="#593314",
            capsize=5,
            linewidth=1.5,
            zorder=4,
        )
    for i, row in enumerate(rows):
        ax.text(
            total[i] + offset,
            y[i] - gap,
            f"{total[i]:.2f}",
            va="center",
            color=MODEL,
            fontsize=10,
        )
        if electric:
            ax.text(
                onboard[i] - offset,
                y[i] - gap,
                f"{onboard[i]:.2f}",
                va="center",
                ha="right",
                color="white",
                fontsize=10,
            )
        value = f"{published[i]:.2f}"
        if observed_range[i] > 0:
            value = f"{row['reported_min']:.2f}–{row['reported_max']:.2f}"
        ax.text(
            row["reported_max"] + offset,
            y[i] + gap,
            value,
            va="center",
            color="#934A20",
            fontsize=10,
        )
    ax.set_yticks(y, [r["label"] for r in rows], fontsize=10)
    ax.set_ylim(len(rows) - 0.5, -0.5)
    ax.set_xlim(0, max_value * 1.22)
    ax.set_xlabel("kWh / 100 km" if electric else "L / 100 km", fontsize=10)
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", pad=30)
    ax.text(
        0, 1.025, note, transform=ax.transAxes, fontsize=9, color="#566573", va="bottom"
    )
    ax.grid(axis="x", color="#DDE4E8", linewidth=0.7, zorder=0)
    ax.tick_params(axis="both", length=0)


def make_figure(records, electric):
    """Return a standalone figure with source keys and comparison limitations."""
    selected = lambda key: [row for row in records if row["panel"] == key]
    if electric:
        fig, axes = plt.subplots(
            3, 1, figsize=(12.5, 13.5), gridspec_kw={"height_ratios": [3, 4, 2]}
        )
        panel(
            axes[0],
            selected("electric_cars"),
            "Electric cars · charging energy",
            "Model: generic WLTC classes. Published: ADAC Ecotest, including charging losses.",
            True,
        )
        panel(
            axes[1],
            selected("electric_buses"),
            "Electric buses · onboard and charging energy shown",
            "BYD meter boundary unclear; 2017 measurement onboard. Masses and auxiliaries differ.",
            True,
        )
        panel(
            axes[2],
            selected("electric_trucks"),
            "Electric trucks · different routes and loads",
            "Model: 32.98 t, Long haul. Tests: 40 t; exact meter boundaries unclear.",
            True,
        )
        title = "Electricity use · model vs published measurements"
        legend = [
            Patch(color=MODEL, label="Model: onboard"),
            Patch(color=LOSSES, label="Model: charging losses"),
            Patch(color=PUBLISHED, label="Published measurement"),
        ]
        footnote = (
            "Model bar total = charging energy; white labels = onboard energy. Use the boundary appropriate to each measurement.\n"
            "Cars use class proxies, including a compact proxy for the EV3 SUV; vehicle mass, road load and power are not matched.\n"
            "BYD SORT tests: 16.675 t, auxiliaries off. Model SORT runs: 12.56–13.05 t, default auxiliaries.\n"
            "Sources: [3] Gis et al. 2017; [7–9] ADAC ID.3 (2025), Ioniq 6 (2023), EV3 (2025);\n"
            "[10] ICCT / BYD test (2020); [11] Daimler tour (2024); [12] Volvo report (2022). Full URLs in bar_comparisons.csv."
        )
        fig.subplots_adjust(left=0.34, right=0.96, top=0.82, bottom=0.155, hspace=0.64)
        legend_y = 0.903
    else:
        fig, axes = plt.subplots(
            2, 1, figsize=(12.5, 9.2), gridspec_kw={"height_ratios": [5, 2]}
        )
        panel(
            axes[0],
            selected("fuel_cars"),
            "Passenger cars",
            "Model: WLTC with approximate mass/power. Published: WLTP or ADAC Ecotest.",
        )
        panel(
            axes[1],
            selected("fuel_heavy"),
            "Diesel bus and trucks",
            "Bus: approximate SORT 2 test load. Trucks: 31 t model, different road-test route.",
        )
        title = "Fuel use · model vs published data"
        legend = [
            Patch(color=MODEL, label="2025 model run"),
            Patch(color=PUBLISHED, label="Published value / range"),
        ]
        footnote = (
            "Range bars use the midpoint; whiskers show published ranges, not statistical uncertainty.\n"
            "The Corolla estate comparison uses the existing hatchback approximation. Exact road load and control are not matched.\n"
            "Sources: [1] Volkswagen MY2025; [2] Toyota MY25; [3] Gis et al. 2017; [4] Green Truck 2025;\n"
            "[5] ADAC Golf (2024); [6] ADAC Corolla Touring Sports (2023). Full URLs in bar_comparisons.csv."
        )
        fig.subplots_adjust(left=0.34, right=0.96, top=0.76, bottom=0.18, hspace=0.72)
        legend_y = 0.903
    fig.suptitle(
        title, x=0.04, y=0.975, ha="left", fontsize=20, fontweight="bold", color=TEXT
    )
    fig.text(
        0.04,
        0.929,
        "2025 model outputs · screening comparisons with differing cycles, vehicles and test conditions",
        fontsize=10,
        color="#566573",
    )
    fig.legend(
        handles=legend,
        loc="upper left",
        bbox_to_anchor=(0.035, legend_y),
        ncol=len(legend),
        frameon=False,
        fontsize=10,
    )
    fig.text(0.04, 0.035, footnote, fontsize=9, color="#566573", linespacing=1.6)
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = args.output or args.data
    output.mkdir(parents=True, exist_ok=True)
    records, excluded = read_records(args.data)
    provenance = {
        "purpose": "Screening charts from existing runs; no new model runs or calibration.",
        "input_sha256": {
            name: hashlib.sha256((args.data / name).read_bytes()).hexdigest()
            for name in [
                "runs.csv",
                "benchmarks.json",
                "additional_measurements.json",
                "provenance.json",
            ]
        },
        "plot_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "comparisons": records,
        "additional_observations_not_paired": excluded,
    }
    (output / "bar_comparisons.json").write_text(
        json.dumps(provenance, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    fields = list(dict.fromkeys(key for record in records for key in record))
    with (output / "bar_comparisons.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "text.color": TEXT,
            "axes.labelcolor": TEXT,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
            "axes.spines.bottom": False,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )
    with PdfPages(output / "model_vs_measurements_bars.pdf") as pdf:
        for electric, name in [
            (False, "fuel_comparison_bars"),
            (True, "electricity_comparison_bars"),
        ]:
            fig = make_figure(records, electric)
            for suffix in ["png", "svg"]:
                fig.savefig(output / f"{name}.{suffix}", dpi=180, facecolor="white")
            pdf.savefig(fig, facecolor="white")
            plt.close(fig)
    print(
        f"Plotted {len(records)} comparisons; {len(excluded)} additional observations lack a paired saved run."
    )
    print(output)


if __name__ == "__main__":
    main()
