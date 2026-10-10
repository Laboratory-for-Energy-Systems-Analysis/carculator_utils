"""Reproduce the exact Ethylene extension from the B-matrix source project.

Run with a Brightway environment containing the existing ecoinvent 3.12 project:
``python dev/extract_ethylene_factors.py --output /tmp/ethylene.json``.
Reads source databases/methods; never creates or changes database contents.
"""

import argparse
import json
from datetime import date
from pathlib import Path

from update_iam_b_matrices import (
    BIOSPHERE_DB,
    PROJECT,
    load_impact_categories,
    mapped_methods,
    validate_method_units,
)


def extract():
    import bw2data as bd

    if PROJECT not in bd.projects:
        raise ValueError(f"Existing source project required: {PROJECT}")
    bd.projects.set_current(PROJECT)
    compartments = (
        "urban air close to ground",
        "non-urban air or from high stacks",
        "low population density, long-term",
    )
    flows = []
    for compartment in compartments:
        matches = [
            flow
            for flow in bd.Database(BIOSPHERE_DB)
            if flow["name"] == "Ethylene"
            and flow.get("categories") == ("air", compartment)
            and flow["unit"] == "kilogram"
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one Ethylene flow in {compartment}: {len(matches)}"
            )
        flows.append(matches[0])
    report = {
        "source_project": PROJECT,
        "biosphere_database": BIOSPHERE_DB,
        "retrieved": date.today().isoformat(),
        "flows": [
            {
                "label": ["Ethylene", list(flow["categories"]), "kilogram"],
                "source_key": flow.key,
                "factors": {},
            }
            for flow in flows
        ],
    }
    categories = load_impact_categories(
        Path(__file__).resolve().parents[1]
        / "carculator_utils/data/lcia/dict_impact_categories.csv"
    )
    entries = mapped_methods(categories, set(bd.methods))
    validate_method_units(entries, bd.methods)
    cache = {}
    identities = {flow.key for flow in flows} | {flow.id for flow in flows}
    for entry in entries:
        method = entry.brightway_method
        if method and method not in cache:
            cache[method] = {}
            for row in bd.Method(method).load():
                if row[0] in identities:
                    if len(row) != 2:
                        raise ValueError(f"Unexpected regionalized factor: {row}")
                    amount = row[1]["amount"] if isinstance(row[1], dict) else row[1]
                    cache[method][row[0]] = float(amount)
        for flow, record in zip(flows, report["flows"]):
            factors = cache.get(method, {})
            record["factors"].setdefault(":".join(entry.group), {})[
                entry.category.category
            ] = {
                "amount": factors.get(flow.key, factors.get(flow.id, 0)),
                "method": method,
                "has_explicit_factor": flow.key in factors or flow.id in factors,
                "unit": entry.category.unit,
                "status": entry.reason,
            }
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(extract(), indent=2) + "\n", encoding="utf-8")
