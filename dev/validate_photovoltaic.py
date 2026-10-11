"""Compare compact PV coefficients with independent full Brightway LCAs.

Read-only project access; outputs aggregate scores and source identities only.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from compile_iam_matrices import activity_index, load_factors, load_methods
from compile_photovoltaic import aggregate_overrides, label
from iam_matrix_tools import load_labels
from rebuild_iam import database_plan
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--iam-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    import bw2calc as bc
    import bw2data as bd

    config = json.loads((args.iam_dir / "photovoltaic.json").read_text())
    labels = load_labels(args.iam_dir / "dict_inputs_A_matrix.csv")
    aggregates = aggregate_overrides(config)
    previous = bd.projects.current
    report = {"project": args.project, "source": config["source"], "checks": []}
    try:
        bd.projects.set_current(args.project, writable=False)
        methods = load_methods(
            bd, ROOT / "carculator_utils/data/lcia/dict_impact_categories.csv"
        )
        factors = load_factors(bd, methods)
        for item in database_plan():
            index = activity_index(bd.Database(item["name"]))
            first = index[label(config, "CH")][0]
            lca = bc.LCA({first.id: 1})
            lca.lci(factorize=True)
            cf = np.zeros((len(methods), len(lca.dicts.biosphere)))
            for row, values in enumerate(factors):
                for flow, value in values.items():
                    if flow in lca.dicts.biosphere:
                        cf[row, lca.dicts.biosphere[flow]] = value
            suffix = (
                "static"
                if item["static"]
                else f"remind_{item['pathway']}_{item['year']}"
            )
            matrices = {
                method.group: sparse.load_npz(
                    args.iam_dir
                    / f"B_matrix_{method.group[0]}_{method.group[1]}_{suffix}.npz"
                ).toarray()
                for method in methods
                if method.row == 0
            }
            for country in ("CH", "CN", "US", "IN", "EU27", "GLO"):
                key = label(config, country)
                targets = aggregates.get(
                    key, {"targets": [{"label": key, "weight": 1}]}
                )["targets"]
                demand = {}
                for target in targets:
                    suppliers = index[tuple(target["label"])]
                    assert len(suppliers) == 1
                    demand[suppliers[0].id] = target["weight"]
                lca.redo_lci(demand)
                expected = cf @ np.asarray(lca.inventory.sum(axis=1)).ravel()
                column = labels.index(key)
                actual = np.array([matrices[m.group][m.row, column] for m in methods])
                np.testing.assert_allclose(
                    actual,
                    expected,
                    rtol=1e-7,
                    atol=1e-11,
                    err_msg=f"{item['name']}: {country}",
                )
                climate = next(
                    i
                    for i, m in enumerate(methods)
                    if m.group == ("ef", "midpoint")
                    and m.category.category == "climate change"
                )
                report["checks"].append(
                    {
                        "database": item["name"],
                        "label": key,
                        "source_supplier_count": len(demand),
                        "categories_checked": len(methods),
                        "g_co2eq_per_kwh_at_plant": float(actual[climate] * 1000),
                        "maximum_absolute_difference": float(
                            np.max(abs(actual - expected))
                        ),
                    }
                )
            print(f"Verified full-source PV scores: {item['name']}", flush=True)
        report["status"] = "passed"
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    finally:
        bd.projects.set_current(previous, writable=False)


if __name__ == "__main__":
    main()
