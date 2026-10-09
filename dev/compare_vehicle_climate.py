"""Summarize completed before/after vehicle LCIA runs without rerunning models.

Requires matplotlib for the figures. The source report is produced from the
completed runs of validate_iam_models.py with the two aligned IAM bundles.
Verify the previous Git bundle and current resource hashes before reporting.
"""

import argparse
import csv
import hashlib
import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VEHICLES = {
    "carculator": "Lower-medium car",
    "carculator_truck": "18 t truck (urban delivery)",
    "carculator_bus": "13 m city bus",
    "carculator_two_wheeler": "Scooter <4 kW",
}
POWERTRAINS = {
    "BEV": "BEV",
    "BEV-depot": "BEV (depot)",
    "ICEV-p": "Petrol",
    "ICEV-d": "Diesel",
}


def verify_bundles(report, previous_ref):
    revision = subprocess.check_output(
        ["git", "rev-parse", previous_ref], cwd=ROOT, text=True
    ).strip()
    for name, checksum in report["original_bundle_sha256"].items():
        data = subprocess.check_output(
            ["git", "show", f"{revision}:carculator_utils/data/IAM/{name}"], cwd=ROOT
        )
        if hashlib.sha256(data).hexdigest() != checksum:
            # The CSV backup changed line endings; every label and its
            # ordering must still be identical to the previous Git version.
            normalized = data.replace(b"\r\n", b"\n")
            equivalent_hashes = {
                hashlib.sha256(value).hexdigest()
                for value in (normalized, normalized.replace(b"\n", b"\r\n"))
            }
            if name != "dict_inputs_A_matrix.csv" or checksum not in equivalent_hashes:
                raise ValueError(f"Previous bundle does not match {revision}: {name}")
    folder = ROOT / "carculator_utils/data/IAM"
    manifest = json.loads((folder / "build_manifest.json").read_text())
    if not manifest["complete"]:
        raise ValueError("Current bundle is incomplete")
    if report.get("current_bundle_sha256") != manifest["resource_hashes"]:
        raise ValueError(
            "Stored model runs do not match the current bundle fingerprint"
        )
    for name, checksum in manifest["resource_hashes"].items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Current bundle has changed: {name}")
    return revision, manifest


def climate_rows(report):
    rows = []
    for source in report["model_comparison"]:
        if (
            source["impact_category"],
            source["method"],
            source["indicator"],
            source["chemistry"],
        ) != ("climate change", "recipe", "midpoint", "default"):
            continue
        old, new = (1000 * float(source[f"amount_{key}"]) for key in ("old", "new"))
        if not math.isfinite(old) or not math.isfinite(new) or old <= 0:
            raise ValueError(f"Invalid comparison: {source}")
        rows.append(
            {
                "vehicle": VEHICLES[source["package"]],
                "powertrain": POWERTRAINS[source["powertrain"]],
                "manufacture_year": int(source["year"]),
                "scenario": source["scenario"],
                "previous_g_co2eq_vkm": old,
                "updated_g_co2eq_vkm": new,
                "absolute_change_g_co2eq_vkm": new - old,
                "change_percent": 100 * (new / old - 1),
            }
        )
    identities = {
        (r["vehicle"], r["powertrain"], r["manufacture_year"], r["scenario"])
        for r in rows
    }
    if len(rows) != 96 or len(identities) != len(rows):
        raise ValueError("Expected 8 vehicles × 3 years × 4 scenarios")
    return rows


def figure(rows, scenario, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
        }
    )
    fig, axes = plt.subplots(2, 2, figsize=(11.8, 7.4))
    colors = ("#A7B1BF", "#176B91")
    for ax, vehicle in zip(axes.flat, VEHICLES.values()):
        selected = [
            r
            for r in rows
            if r["vehicle"] == vehicle
            and r["manufacture_year"] == 2025
            and r["scenario"] == scenario
        ]
        assert len(selected) == 2
        for position, row in enumerate(selected):
            old, new = row["previous_g_co2eq_vkm"], row["updated_g_co2eq_vkm"]
            ax.barh(position - 0.17, old, height=0.29, color=colors[0])
            ax.barh(position + 0.17, new, height=0.29, color=colors[1])
            ax.annotate(
                f"{row['change_percent']:+.2f}%",
                (new, position + 0.17),
                xytext=(6, 0),
                textcoords="offset points",
                va="center",
                fontsize=10,
                fontweight="bold",
                color=colors[1],
            )
        ax.set_yticks([0, 1], [r["powertrain"] for r in selected])
        ax.invert_yaxis()
        ax.set_xlim(0, max(r["updated_g_co2eq_vkm"] for r in selected) * 1.23)
        ax.set_title(vehicle, loc="left", fontsize=13, fontweight="bold", pad=13)
        ax.set_xlabel("Life-cycle climate impact (g CO₂-eq / vehicle-km)", fontsize=10)
        ax.grid(axis="x", alpha=0.2)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0)
    fig.suptitle(
        f"2025 vehicles · {scenario}\nClimate impact before and after the LCA background refresh",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )
    fig.legend(
        [Patch(color=c) for c in colors],
        ["Previous bundle", "Premise 2.5.4 / ecoinvent 3.12"],
        loc="upper center",
        bbox_to_anchor=(0.5, 0.89),
        ncol=2,
        frameon=False,
    )
    fig.text(
        0.5,
        0.015,
        "Switzerland · ReCiPe midpoint, climate change · Identical vehicle assumptions\n"
        "Each panel has its own horizontal scale. Percentages compare updated with previous scores.",
        ha="center",
        fontsize=9,
        color="#475569",
    )
    fig.subplots_adjust(
        top=0.79, bottom=0.14, left=0.11, right=0.97, hspace=0.52, wspace=0.35
    )
    for extension in ("png", "pdf"):
        fig.savefig(
            output / f"climate_2025_{scenario}.{extension}", dpi=180, facecolor="white"
        )
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "docs/_static/background_refresh_20261009.json",
    )
    parser.add_argument("--previous-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    revision, manifest = verify_bundles(report, args.previous_ref)
    rows = climate_rows(report)
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / "climate_comparison.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for scenario in ("SSP2-NPi", "static"):
        figure(rows, scenario, args.output)
    summary = {
        "previous_revision": revision,
        "new_source": report["source"],
        "current_resource_hashes": manifest["resource_hashes"],
        "scope": "Same vehicle models and parameter assumptions; only the aligned A/index/B bundle changes.",
        "country": "CH",
        "functional_unit": "vkm",
        "method": "ReCiPe midpoint, climate change (excluding biogenic CO2)",
        "unchanged_physical_quantities": report["unchanged_physical_quantities"],
        "maximum_absolute_physical_difference": report[
            "maximum_absolute_physical_difference"
        ],
        "comparisons": len(rows),
        "largest_absolute_percentage_change": max(
            rows, key=lambda r: abs(r["change_percent"])
        ),
    }
    (args.output / "provenance.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            [
                r
                for r in rows
                if r["manufacture_year"] == 2025 and r["scenario"] == "SSP2-NPi"
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
