"""Plot the expanded, mass-matched comparisons without importing vehicle models."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Patch

DATA = (
    Path(__file__).resolve().parents[1] / "docs/_static/energy_validation_2025/expanded"
)
MODEL, LOSSES, REPORTED = "#176B87", "#A7D3E0", "#CE7138"
LABELS = {
    "adac_kodiaq_diesel": "Skoda Kodiaq diesel",
    "adac_spring65": "Dacia Spring 65",
    "adac_e208": "Peugeot e-208",
    "adac_id3_gtx": "VW ID.3 GTX",
    "adac_ioniq6": "Hyundai Ioniq 6",
    "adac_ev3": "Kia EV3",
    "adac_ev9": "Kia EV9 AWD",
    "adac_idbuzz": "VW ID. Buzz long",
    "adac_golf_petrol": "VW Golf 1.5 TSI",
    "adac_corolla_hybrid": "Corolla estate hybrid",
    "adac_yaris130": "Toyota Yaris hybrid",
    "eactros_summer": "Mercedes eActros 600",
    "volvo_fh_electric": "Volvo FH Electric",
    "adac_octavia_diesel": "Skoda Octavia diesel",
    "adac_leon_cng": "SEAT Leon CNG",
    "adac_mirai": "Toyota Mirai hydrogen",
    "calstart_smith_newton": "Smith Newton Step Van",
    "nrel_mt45_diesel": "Freightliner MT-45 diesel",
    "altoona_gillig_2020_05": "Gillig 40-foot BEV",
    "adac_fiat500_red": "Fiat 500e RED 23.8 kWh",
    "adac_fiat500_prima": "Fiat 500e La Prima 42 kWh",
    "adac_fiat500_cabrio": "Fiat 500e Cabrio 42 kWh",
    "adac_prius_phev": "Toyota Prius PHEV",
    "tcrp_nova_diesel": "Nova RTS diesel",
    "tcrp_orion_hybrid": "Orion VI diesel hybrid",
    "tcrp_nova_hybrid": "Nova-Allison diesel hybrid",
}


def panel(ax, rows, title, electric):
    units = {r["unit"] for r in rows}
    if len(units) != 1:
        raise ValueError("Do not mix fuel volume, fuel mass and electricity units")
    unit = units.pop()
    positions = np.arange(len(rows))
    values = [r["model_onboard"] if electric else r["model_fuel"] for r in rows]
    totals = [
        (
            (
                r["model_onboard"]
                if r["charging_losses"] == "excluded"
                else r["model_charging"]
            )
            if electric
            else r["model_fuel"]
        )
        for r in rows
    ]
    observed = [r["reported"] for r in rows]
    if electric and any(total < value for total, value in zip(totals, values)):
        raise ValueError("Negative model charging losses")
    ax.barh(positions - 0.18, values, height=0.32, color=MODEL)
    if electric:
        ax.barh(
            positions - 0.18,
            np.subtract(totals, values),
            left=values,
            height=0.32,
            color=LOSSES,
        )
    ax.barh(positions + 0.18, observed, height=0.32, color=REPORTED)
    largest = max(totals + observed)
    for y, total, measured in zip(positions, totals, observed):
        ax.text(
            total + largest * 0.014,
            y - 0.18,
            f"{total:.2f}" if unit == "kg/100 km" else f"{total:.1f}",
            va="center",
            fontsize=10,
        )
        ax.text(
            measured + largest * 0.014,
            y + 0.18,
            f"{measured:.2f}" if unit == "kg/100 km" else f"{measured:.1f}",
            va="center",
            fontsize=10,
        )
    ax.set_yticks(
        positions,
        [
            f"{LABELS.get(r['dataset_id'], r['vehicle'])}\n"
            f"{r['model_size']} · {r['target_driving_mass_kg']:,.0f} kg"
            + (" *" if r["mass_basis"] == "protocol_reconstructed" else "")
            + (f"\n{r['source_boundary']}" if r.get("show_boundary_label") else "")
            + (f"\n{r['model_cycle']}" if r.get("show_cycle_label") else "")
            + (f"\n{r['operating_mode']}" if r.get("operating_mode") else "")
            for r in rows
        ],
        fontsize=10,
    )
    ax.invert_yaxis()
    ax.set_xlim(0, largest * 1.17)
    ax.set_xlabel(unit)
    ax.set_title(title, loc="left", fontsize=13, weight="bold", pad=13)
    ax.xaxis.grid(True, alpha=0.18)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0, pad=12)
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    args = parser.parse_args()
    source = args.data / "comparisons.json"
    manifest = json.loads(source.read_text())
    rows = manifest["comparisons"]
    for r in rows:
        if r["model_year"] != 2025:
            raise ValueError("Unexpected model year")
        for field in ["model_driving_mass_kg", "energy_input_driving_mass_kg"]:
            if abs(r[field] - r["target_driving_mass_kg"]) >= 0.1:
                raise ValueError("Mass mismatch in plotted result")
    cars = sorted(
        [
            r
            for r in rows
            if r["vehicle_type"] == "car" and r["model_charging"] is not None
        ],
        key=lambda r: r["target_driving_mass_kg"],
    )
    trucks = [
        r
        for r in rows
        if r["vehicle_type"] == "truck" and r["charging_losses"] == "unknown"
    ]
    metered_trucks = [
        dict(r, show_boundary_label=True)
        for r in rows
        if r["vehicle_type"] == "truck"
        and r["model_charging"] is not None
        and r["charging_losses"] in ["included", "excluded"]
    ]
    fuel = sorted(
        [r for r in rows if r["unit"] == "L/100 km" and r["vehicle_type"] == "car"],
        key=lambda r: r["target_driving_mass_kg"],
    )
    gas_rows = [r for r in rows if r["unit"] == "kg/100 km"]
    fuel_buses = [
        dict(r, show_cycle_label=True)
        for r in rows
        if r["vehicle_type"] == "bus" and r["unit"] == "L/100 km"
    ]
    electric_buses = [
        dict(r, show_cycle_label=True)
        for r in rows
        if r["vehicle_type"] == "bus"
        and r["model_charging"] is not None
        and r["charging_losses"] == "included"
    ]
    uncertain_buses = [
        dict(r, show_cycle_label=True)
        for r in rows
        if r["vehicle_type"] == "bus"
        and r["model_charging"] is not None
        and r["charging_losses"] == "unknown"
    ]
    diesel_trucks = [
        dict(r, show_cycle_label=True)
        for r in rows
        if r["vehicle_type"] == "truck" and r["unit"] == "L/100 km"
    ]
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.labelcolor": "#283C48",
            "text.color": "#283C48",
            "svg.fonttype": "none",
        }
    )
    electric, axes = plt.subplots(
        2,
        1,
        figsize=(12, max(11, 5 + 0.8 * len(cars))),
        gridspec_kw={"height_ratios": [len(cars), len(trucks)]},
    )
    electric.subplots_adjust(left=0.28, right=0.96, top=0.87, bottom=0.13, hspace=0.47)
    electric.suptitle(
        "2025 model vs measured electricity use",
        x=0.03,
        y=0.975,
        ha="left",
        fontsize=19,
        weight="bold",
    )
    electric.text(
        0.03, 0.941, "Driving mass matched; other test conditions differ", fontsize=12
    )
    electric.legend(
        handles=[
            Patch(color=MODEL, label="Model onboard"),
            Patch(color=LOSSES, label="Model battery/charging losses"),
            Patch(color=REPORTED, label="Published measurement"),
        ],
        loc="upper left",
        bbox_to_anchor=(0.023, 0.924),
        frameon=False,
        ncol=3,
    )
    panel(
        axes[0],
        cars,
        "Cars · measured AC charging energy; model WLTC vs ADAC Ecotest",
        True,
    )
    panel(
        axes[1],
        trucks,
        "Trucks · reported meter boundary unresolved; routes differ",
        True,
    )
    electric.text(
        0.03,
        0.075,
        "* Reconstructed mass = ADAC measured curb mass + documented 200 kg test payload.\n"
        "Truck mass is explicitly reported. Dark + light model segments total charging energy.\n"
        "Class road loads and efficiencies retained. These comparisons are screening evidence, not validation.",
        fontsize=10,
        va="top",
        linespacing=1.5,
    )
    gasoline, ax = plt.subplots(figsize=(12, max(5.4, 3.3 + 0.7 * len(fuel))))
    gasoline.subplots_adjust(left=0.28, right=0.96, top=0.74, bottom=0.25)
    gasoline.suptitle(
        "2025 model vs measured liquid-fuel use",
        x=0.03,
        y=0.97,
        ha="left",
        fontsize=19,
        weight="bold",
    )
    gasoline.legend(
        handles=[
            Patch(color=MODEL, label="Model WLTC"),
            Patch(color=REPORTED, label="ADAC Ecotest"),
        ],
        loc="upper left",
        bbox_to_anchor=(0.023, 0.91),
        frameon=False,
        ncol=2,
    )
    panel(
        ax,
        fuel,
        "Petrol, diesel and hybrid modes · driving mass and rated power matched",
        False,
    )
    gasoline.text(
        0.03,
        0.115,
        "* Reconstructed mass = ADAC measured curb mass + documented 200 kg test payload.\n"
        "Cycles, conditioning, road loads and hybrid control differ; no calibration to measured consumption.",
        fontsize=10,
        va="top",
        linespacing=1.5,
    )
    figures = [
        ("electricity_mass_comparison", electric),
        ("fuel_mass_comparison", gasoline),
    ]
    if gas_rows:
        gas, gas_axes = plt.subplots(2, 1, figsize=(12, 6.8))
        gas.subplots_adjust(left=0.28, right=0.96, top=0.76, bottom=0.23, hspace=1.1)
        gas.suptitle(
            "2025 model vs measured gaseous-fuel use",
            x=0.03,
            y=0.97,
            ha="left",
            fontsize=19,
            weight="bold",
        )
        gas.legend(
            handles=[
                Patch(color=MODEL, label="Model WLTC"),
                Patch(color=REPORTED, label="ADAC Ecotest"),
            ],
            loc="upper left",
            bbox_to_anchor=(0.023, 0.915),
            frameon=False,
            ncol=2,
        )
        for ax, pwt, title in zip(
            gas_axes,
            ["ICEV-g", "FCEV"],
            ["CNG · fuel mass at the vehicle", "Hydrogen · fuel mass at the vehicle"],
        ):
            subset = [r for r in gas_rows if r["powertrain"] == pwt]
            if subset:
                panel(ax, subset, title, False)
            else:
                ax.set_visible(False)
        gas.text(
            0.03,
            0.13,
            "* Reconstructed mass = measured curb mass + documented 200 kg test payload.\n"
            "Different fuels have different energy contents; kilograms are not comparable across panels.\n"
            "Model year 2025; measured tests from 2021. Cycles, fuel composition and control differ.",
            fontsize=10,
            va="top",
            linespacing=1.5,
        )
        figures.append(("gas_mass_comparison", gas))
    if metered_trucks:
        delivery, ax = plt.subplots(figsize=(12, 6.6))
        delivery.subplots_adjust(left=0.29, right=0.96, top=0.71, bottom=0.30)
        delivery.suptitle(
            "Delivery truck · battery and grid boundaries",
            x=0.03,
            y=0.96,
            ha="left",
            fontsize=19,
            weight="bold",
        )
        delivery.legend(
            handles=[
                Patch(color=MODEL, label="Model onboard"),
                Patch(color=LOSSES, label="Model battery/charging losses"),
                Patch(color=REPORTED, label="Published measurement"),
            ],
            loc="upper left",
            bbox_to_anchor=(0.023, 0.90),
            frameon=False,
            ncol=3,
        )
        panel(
            ax,
            metered_trucks,
            "OCBC · official reference trace; reported driving mass matched",
            True,
        )
        delivery.text(
            0.03,
            0.19,
            "Two meter boundaries for one test and one model run; not independent tests.\n"
            "DC compares onboard energy; AC includes battery and charging losses.\n"
            "2025 class model vs 2013 vehicle. Road load, auxiliaries and efficiencies differ.\n"
            "Source explicitly sets 13,175 lb; its curb-plus-half-payload description conflicts with its specifications.",
            fontsize=10,
            va="top",
            linespacing=1.5,
        )
        figures.append(("delivery_truck_mass_comparison", delivery))
    if diesel_trucks:
        diesel, ax = plt.subplots(figsize=(12, 6.4))
        diesel.subplots_adjust(left=0.29, right=0.96, top=0.72, bottom=0.28)
        diesel.suptitle(
            "Diesel delivery truck · published test cycles",
            x=0.03,
            y=0.96,
            ha="left",
            fontsize=19,
            weight="bold",
        )
        diesel.legend(
            handles=[
                Patch(color=MODEL, label="2025 model"),
                Patch(color=REPORTED, label="NREL dynamometer measurement"),
            ],
            loc="upper left",
            bbox_to_anchor=(0.023, 0.90),
            frameon=False,
            ncol=2,
        )
        panel(
            ax,
            diesel_trucks,
            "Reported driving mass matched; reference cycle profiles",
            False,
        )
        diesel.text(
            0.03,
            0.17,
            "Two cycles on one diesel truck; historical measurements from 2009.\n"
            "Actual speed tracking, road load, conditioning and fuel properties differ.\n"
            "Road load, auxiliaries and historical powertrain operation remain approximations.",
            fontsize=10,
            va="top",
            linespacing=1.5,
        )
        figures.append(("diesel_truck_mass_comparison", diesel))
    if electric_buses:
        buses, ax = plt.subplots(figsize=(12, 6.4))
        buses.subplots_adjust(left=0.29, right=0.96, top=0.72, bottom=0.28)
        buses.suptitle(
            "Electric bus · measured AC charging energy",
            x=0.03,
            y=0.96,
            ha="left",
            fontsize=19,
            weight="bold",
        )
        buses.legend(
            handles=[
                Patch(color=MODEL, label="Model onboard"),
                Patch(color=LOSSES, label="Model battery/charging losses"),
                Patch(color=REPORTED, label="Altoona measurement"),
            ],
            loc="upper left",
            bbox_to_anchor=(0.023, 0.90),
            frameon=False,
            ncol=3,
        )
        panel(
            ax,
            electric_buses,
            "Measured curb and driving masses matched; reference cycle profiles",
            True,
        )
        buses.text(
            0.03,
            0.17,
            "Model year 2025; measurements from March 2021. Three cycles on one bus.\n"
            "Base auxiliaries use the transferred 8.3 kW prior; road load and motor rating remain approximations.\n"
            "Manhattan resampled to 1 s: positive squared-speed change -2.75%; distance +0.005%.\n"
            "OCBC and HD-UDDS informed calibration; Manhattan was held out. This is not independent validation.",
            fontsize=10,
            va="top",
            linespacing=1.5,
        )
        figures.append(("bus_mass_comparison", buses))
    if uncertain_buses:
        uncertain, ax = plt.subplots(figsize=(12, 6.4))
        uncertain.subplots_adjust(left=0.30, right=0.96, top=0.73, bottom=0.25)
        uncertain.suptitle(
            "Electric bus · unresolved measurement boundary",
            x=0.03,
            y=0.96,
            ha="left",
            fontsize=19,
            weight="bold",
        )
        uncertain.legend(
            handles=[
                Patch(color=MODEL, label="Model battery-terminal energy"),
                Patch(color=LOSSES, label="Model charging losses"),
                Patch(color=REPORTED, label="Published SORT measurement"),
            ],
            loc="upper left",
            bbox_to_anchor=(0.023, 0.90),
            frameon=False,
            ncol=3,
        )
        panel(
            ax,
            uncertain_buses,
            "Documented driving mass; named SORT reference cycles",
            True,
        )
        uncertain.text(
            0.03,
            0.16,
            "Source meter boundary is unresolved: neither model boundary is a confirmed like-for-like comparison.\n"
            "Auxiliaries are off as documented. Historical test vehicle compared with 2025 component priors.\n"
            "Screening evidence only; these measurements were not used to fit the auxiliary default.",
            fontsize=10,
            va="top",
            linespacing=1.5,
        )
        figures.append(("bus_unknown_boundary_comparison", uncertain))
    if fuel_buses:
        bus_fuel, ax = plt.subplots(figsize=(12, max(7, 3.8 + len(fuel_buses) * 0.75)))
        bus_fuel.subplots_adjust(left=0.30, right=0.96, top=0.76, bottom=0.22)
        bus_fuel.suptitle(
            "Diesel and hybrid buses · historical cycle tests",
            x=0.03,
            y=0.97,
            ha="left",
            fontsize=19,
            weight="bold",
        )
        bus_fuel.legend(
            handles=[
                Patch(color=MODEL, label="2025 model"),
                Patch(color=REPORTED, label="1999 NAVC/WVU measurement"),
            ],
            loc="upper left",
            bbox_to_anchor=(0.023, 0.91),
            frameon=False,
            ncol=2,
        )
        panel(
            ax,
            fuel_buses,
            "Curb and driving masses matched; NY Bus differs from NYCC",
            False,
        )
        bus_fuel.text(
            0.03,
            0.13,
            "NY Bus and Manhattan resampled to 1 s. Manhattan positive squared-speed change -2.75%.\n"
            "1999 vehicles versus 2025 class technology: engine, fuel, auxiliaries and control differ.\n"
            "Historical technology and control differences limit interpretation of agreement.",
            fontsize=10,
            va="top",
            linespacing=1.5,
        )
        figures.append(("fuel_bus_mass_comparison", bus_fuel))
    catalog_path = args.data / "measurements.json"
    catalog = json.loads(catalog_path.read_text()) if catalog_path.exists() else {}
    experiment_label = None
    if "conditional_bus_auxiliary_calibration" in catalog:
        experiment_label = (
            "Conditional bus auxiliary fit · Manhattan withheld from fitting"
        )
    elif "component_efficiency_experiment" in catalog:
        experiment_label = "Unfitted component-efficiency sensitivity experiment"
    for name, fig in figures:
        if experiment_label:
            fig.text(0.03, 0.025, experiment_label, fontsize=10, style="italic")
        fig.savefig(args.data / (name + ".png"), dpi=180, facecolor="white")
        fig.savefig(args.data / (name + ".svg"), facecolor="white")
    with PdfPages(args.data / "mass_comparison_bars.pdf") as pdf:
        for _, fig in figures:
            pdf.savefig(fig)
    (args.data / "plot_manifest.json").write_text(
        json.dumps(
            {
                "comparisons_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "plotted_observations": [
                    r["observation_id"]
                    for r in cars
                    + trucks
                    + fuel
                    + gas_rows
                    + metered_trucks
                    + diesel_trucks
                    + electric_buses
                    + uncertain_buses
                    + fuel_buses
                ],
                "note": "Only eligible full-model outputs; exclusions retained in comparisons.json.",
                "experiment_label": experiment_label,
            },
            indent=2,
        )
        + "\n"
    )
    plt.close("all")


if __name__ == "__main__":
    main()
