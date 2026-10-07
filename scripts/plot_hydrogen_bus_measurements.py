"""Plot sourced hydrogen-bus observations awaiting numerical road-cycle traces."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DATA = (
    Path(__file__).resolve().parents[1] / "docs/_static/energy_validation_2025/expanded"
)


def main():
    """Write a measurements-only figure, keeping it separate from model comparisons."""
    source = DATA / "measurements.json"
    catalog = json.loads(source.read_text())
    rows = [
        row
        for row in catalog["observations"]
        if row["dataset_id"] == "schatz_humboldt_xhe40_2025"
    ]
    if not rows or any(row["unit"] != "kg/100 km" for row in rows):
        raise ValueError("Expected hydrogen mass observations")
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.subplots_adjust(left=0.36, right=0.95, top=0.78, bottom=0.25)
    values = [r["value"] for r in rows]
    ax.barh(range(len(rows)), values, color="#ce7135", height=0.58)
    ax.set_yticks(
        range(len(rows)),
        [
            f"{r['cycle_or_route']}\n{r['driving_mass_kg']:,.0f} kg* · HVAC "
            + ("full heat" if "full power" in r["hvac"] else r["hvac"])
            for r in rows
        ],
    )
    for index, value in enumerate(values):
        ax.text(value + 0.1, index, f"{value:.1f}", va="center")
    ax.invert_yaxis()
    ax.set_xlim(0, max(values) * 1.17)
    ax.set_xlabel("kg H₂ / 100 km")
    ax.xaxis.grid(True, alpha=0.18)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0, pad=10)
    fig.suptitle(
        "Hydrogen bus · measured road-route consumption",
        x=0.035,
        y=0.96,
        ha="left",
        fontsize=19,
        weight="bold",
    )
    fig.text(
        0.035,
        0.87,
        "New Flyer XHE40 extended-range pilot · April 2025 · measurements only",
        fontsize=12,
    )
    fig.text(
        0.035,
        0.14,
        "* Driving mass reconstructed from measured curb mass plus documented passengers/ballast.\n"
        "Source: Schatz Energy Research Center, May 2025. Published battery-SOC corrections retained.\n"
        "Hydrogen inferred from tank pressure; approximate precision. Route and HVAC conditions differ.\n"
        "No model bars: complete speed/gradient traces are unavailable.",
        fontsize=10,
        va="top",
        linespacing=1.5,
    )
    for extension in ["png", "svg", "pdf"]:
        fig.savefig(
            DATA / f"hydrogen_bus_measurements.{extension}", dpi=180, facecolor="white"
        )
    (DATA / "hydrogen_bus_plot_manifest.json").write_text(
        json.dumps(
            {
                "catalog_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "observation_ids": [r["id"] for r in rows],
                "note": "Measurements only; not model validation.",
            },
            indent=2,
        )
        + "\n"
    )
    plt.close(fig)


if __name__ == "__main__":
    main()
