"""Calculate actual Brightway LCIA scores for the public vehicle exports.

Run after audit_pipeline_spotchecks.py in the matrix-build Brightway environment.
Adds uniquely named audit databases to an EXISTING project; never overwrites
databases, methods or suppliers. All external links use exact identities.
Private input JSON contains licensed inventory information: do not publish it.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

import bw2calc as bc
import bw2data as bd
import numpy as np
from update_iam_b_matrices import load_impact_categories, mapped_methods

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "carculator-matrices-premise-2.5.4-ei312-20261009"
PREFIX = "carculator-ei312-premise254"
BIO = "ecoinvent-3.12-biosphere"


def activity_label(d):
    return (
        d["name"],
        d.get("reference product", d.get("product")),
        d["location"],
        d["unit"],
    )


def bio_label(d):
    return d["name"], tuple(d["categories"]), d["unit"]


def unique(index, label):
    found = index.get(label, [])
    if len(found) != 1:
        raise ValueError(f"Expected one exact supplier for {label}: {found}")
    return found[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--model-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--database-prefix", required=True)
    parser.add_argument(
        "--reuse-audit-databases",
        action="store_true",
        help="Reuse only after checking that stored activities/exchanges equal this export plan.",
    )
    args = parser.parse_args()
    model = json.loads(args.model_report.read_text())
    previous = bd.projects.current
    if PROJECT not in bd.projects:
        raise ValueError(f"Required project does not exist: {PROJECT}")
    bd.projects.set_current(PROJECT)
    try:
        run(args, model)
    finally:
        bd.projects.set_current(previous)


def run(args, model):
    records = model["cases"]
    exports = {
        r["id"]: json.loads((args.private_dir / (r["id"] + ".json")).read_text())
        for r in records
    }
    groups = {"static": [r for r in records if r["scenario"] == "static"]}
    # Same exported foreground against both background endpoints reproduces
    # B interpolation; changing the foreground between endpoints would not.
    for r in records:
        if r["scenario"] != "static":
            if r["year"] != 2025:
                raise ValueError(
                    "This audit's prospective endpoint weights are for 2025."
                )
            for year in [2020, 2030]:
                groups.setdefault(f"{r['scenario']}-{year}", []).append(r)
    names = [
        args.database_prefix + "-noise",
        *[args.database_prefix + "-" + g for g in groups],
    ]
    if any(n in bd.databases for n in names) and not args.reuse_audit_databases:
        raise ValueError("Audit database already exists: use a new --database-prefix.")
    for group in groups:
        if PREFIX + "-" + group not in bd.databases:
            raise ValueError(f"Missing background: {group}")
    bio_index = defaultdict(list)
    for flow in bd.Database(BIO):
        bio_index[bio_label(flow)].append(flow.key)
    noise_name = args.database_prefix + "-noise"
    noise = {}
    for data in exports.values():
        for d in data:
            for exc in d["exchanges"]:
                if exc["type"] != "biosphere":
                    continue
                label = bio_label(exc)
                if label in bio_index:
                    continue
                valid_noise = (
                    label[2] == "joule"
                    and label[1]
                    in [
                        (f"octave {i}", "day time", s)
                        for i in range(1, 9)
                        for s in ["urban", "suburban", "rural"]
                    ]
                    and label[0] == "noise, " + ", ".join(label[1])
                )
                if not valid_noise:
                    raise ValueError(f"Unmapped biosphere flow: {label}")
                key = noise_name, f"noise-{len(noise)}"
                noise[key] = dict(
                    name=label[0], categories=label[1], unit=label[2], type="emission"
                )
                bio_index[label].append(key)
    # Resolve every exchange before any database write.
    plans, targets = {}, {}
    for group, cases in groups.items():
        background = PREFIX + "-" + group
        print("Indexing", background, flush=True)
        providers = defaultdict(list)
        for act in bd.Database(background):
            providers[activity_label(act)].append(act.key)
        name = args.database_prefix + "-" + group
        linked, group_targets = {}, {}
        for record in cases:
            data = exports[record["id"]]
            foreground = defaultdict(list)
            for i, d in enumerate(data):
                foreground[activity_label(d)].append((name, record["id"] + f"-{i}"))
            group_targets[record["id"]] = unique(
                foreground, activity_label(record["export_target"])
            )
            for original in data:
                d = deepcopy(original)
                key = unique(foreground, activity_label(d))
                d["database"], d["code"] = key
                for exc in d["exchanges"]:
                    if exc["type"] == "production":
                        supplier = key
                    elif exc["type"] == "biosphere":
                        supplier = unique(bio_index, bio_label(exc))
                    elif exc["type"] == "technosphere":
                        label = activity_label(exc)
                        supplier = unique(
                            foreground if label in foreground else providers, label
                        )
                    else:
                        raise ValueError(f"Unexpected exchange type: {exc['type']}")
                    exc["input"] = supplier
                    exc["output"] = key
                linked[key] = d
        plans[name] = linked
        targets[group] = group_targets
    categories = load_impact_categories(
        ROOT / "carculator_utils/data/lcia/dict_impact_categories.csv"
    )
    methods = [
        m
        for m in mapped_methods(categories, set(bd.methods))
        if m.group == ("recipe", "midpoint")
    ]
    selected = [m for m in methods if m.brightway_method]
    report = dict(
        project=PROJECT,
        software={
            p: importlib.metadata.version(p)
            for p in ["bw2data", "bw2calc", "numpy", "scipy"]
        },
        matching="Exact name/product/location/unit for suppliers; name/categories/unit for biosphere.",
        custom_noise_flow_count=len(noise),
        excluded_methods=[
            dict(category=m.category.category, reason=m.reason)
            for m in methods
            if not m.brightway_method
        ],
        created_databases=names,
        endpoints=[],
        comparisons=[],
    )
    if args.reuse_audit_databases:
        for name, data in {noise_name: noise, **plans}.items():
            if name not in bd.databases or len(bd.Database(name)) != len(data):
                raise ValueError(f"Cannot reuse incomplete audit database: {name}")
            for key, expected in data.items():
                stored = bd.get_activity(key)
                if name == noise_name:
                    assert bio_label(stored) == bio_label(expected)
                else:
                    assert activity_label(stored) == activity_label(expected)
                project = lambda exc: (
                    exc["type"],
                    tuple(exc["input"]),
                    float(exc["amount"]),
                )
                if sorted(project(e) for e in stored.exchanges()) != sorted(
                    project(e) for e in expected.get("exchanges", [])
                ):
                    raise ValueError(f"Audit exchange contents changed: {key}")
    else:
        if noise:
            bd.Database(noise_name).write(noise)
        for name, data in plans.items():
            bd.Database(name).write(data)
    for group, group_targets in targets.items():
        print("Calculating", group, flush=True)
        first = next(iter(group_targets.values()))
        lca = bc.LCA({first: 1}, selected[0].brightway_method)
        lca.lci(factorize=True)
        for m in selected:
            lca.switch_method(m.brightway_method)
            lca.lcia()
            for case_id, key in group_targets.items():
                lca.redo_lcia({bd.get_activity(key).id: 1})
                report["endpoints"].append(
                    dict(
                        id=case_id,
                        background=PREFIX + "-" + group,
                        group=group,
                        target=key,
                        category=m.category.category,
                        method=m.brightway_method,
                        unit=bd.Method(m.brightway_method).metadata.get("unit"),
                        brightway=float(lca.score),
                    )
                )
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    for r in records:
        scores = {i["category"]: i for i in r["impacts"]}
        for m in selected:
            values = [
                e
                for e in report["endpoints"]
                if e["id"] == r["id"] and e["category"] == m.category.category
            ]
            assert len(values) == (1 if r["scenario"] == "static" else 2)
            bw = sum(e["brightway"] for e in values) / len(values)
            core, manual = (scores[m.category.category][s] for s in ["core", "manual"])
            report["comparisons"].append(
                dict(
                    id=r["id"],
                    category=m.category.category,
                    core=core,
                    manual=manual,
                    brightway=bw,
                    core_relative_difference=(core - bw) / bw if bw else None,
                    manual_relative_difference=(manual - bw) / bw if bw else None,
                    core_pass=bool(
                        np.isclose(core, bw, rtol=model["rtol"], atol=1e-10)
                    ),
                    manual_pass=bool(
                        np.isclose(manual, bw, rtol=model["rtol"], atol=1e-10)
                    ),
                )
            )
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    for c in report["comparisons"]:
        if c["category"] == "climate change":
            print(c, flush=True)


if __name__ == "__main__":
    main()
