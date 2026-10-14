"""Explain the largest incremental FCEV changes using exchange contributions."""

import csv
import json
import math
import os

import numpy as np
from compare_premise_car_fcev_buffer import OLD, OUT, WORK
from scipy.sparse.linalg import splu


def main():
    os.environ["BRIGHTWAY2_DIR"] = str(WORK / "brightway")
    import bw2calc as bc
    import bw2data as bd

    bd.projects.set_current("ecoinvent-3.12-cutoff")
    scores = list(csv.DictReader((OUT / "incremental_ef31.csv").open()))
    selected = []
    for name in sorted({r["name"] for r in scores}):
        geography = (
            "EUR"
            if any(r["name"] == name and r["location"] == "EUR" for r in scores)
            else "RER"
        )
        relevant = [
            r for r in scores if r["name"] == name and r["location"] == geography
        ]
        largest = max(relevant, key=lambda r: abs(float(r["percent_change"])))
        selected.append(largest)
        if largest["category"] != "climate change":
            selected.append(
                next(r for r in relevant if r["category"] == "climate change")
            )
    # Also explain the largest increase, since all classwise largest absolute
    # changes happen to be decreases in this calibration.
    largest_increase = max(scores, key=lambda r: float(r["percent_change"]))
    if largest_increase not in selected:
        selected.append(largest_increase)
    values = {}
    for variant, directory in (("before", OLD), ("after", OUT)):
        name = json.loads((directory / "saved_2020.json").read_text())["database"]
        activities = {
            (a["name"], a["location"]): a
            for a in bd.Database(name)
            if any(
                (a["name"], a["location"]) == (r["name"], r["location"])
                for r in selected
            )
        }
        lca = bc.LCA(
            {next(iter(activities.values())).id: 1},
            tuple(json.loads(selected[0]["method"])),
        )
        lca.lci()
        solve_transpose = splu(lca.technosphere_matrix.T.tocsc())
        method_results = {}
        for row in selected:
            activity = activities[row["name"], row["location"]]
            method = tuple(json.loads(row["method"]))
            if method not in method_results:
                lca.switch_method(method)
                cf = np.asarray(lca.characterization_matrix.sum(axis=0)).ravel()
                direct = np.asarray(lca.biosphere_matrix.T @ cf).ravel()
                upstream = solve_transpose.solve(direct)
                method_results[method] = (cf, upstream)
            cf, upstream = method_results[method]
            # This independently solves A.T @ upstream = direct. Agreement with
            # the forward vehicle solve is checked before reporting components.
            score = upstream[lca.dicts.product[activity.id]]
            assert math.isclose(score, float(row[variant]), rel_tol=2e-6, abs_tol=1e-15)
            total = 0
            assert sum(e["amount"] for e in activity.production()) == 1
            for kind, exchanges in (
                ("technosphere", activity.technosphere()),
                ("biosphere", activity.biosphere()),
            ):
                for exc in exchanges:
                    supplier = exc.input
                    unit = (
                        upstream[lca.dicts.product[supplier.id]]
                        if kind == "technosphere"
                        else cf[lca.dicts.biosphere[supplier.id]]
                    )
                    contribution = exc["amount"] * unit
                    ident = (
                        row["name"],
                        row["location"],
                        row["category"],
                        kind,
                        supplier["name"],
                        supplier.get("location", ""),
                        str(supplier.get("categories", "")),
                    )
                    record = values.setdefault(ident, {"before": 0, "after": 0})
                    record[variant] += contribution
                    total += contribution
            assert math.isclose(total, score, rel_tol=2e-6, abs_tol=1e-15)
            for purchase in activity.technosphere():
                production = purchase.input
                if (
                    not production["name"]
                    .lower()
                    .startswith(("passenger car,", "lorry production,"))
                ):
                    continue
                subtotal = 0
                assert sum(e["amount"] for e in production.production()) == 1
                for kind, exchanges in (
                    ("technosphere", production.technosphere()),
                    ("biosphere", production.biosphere()),
                ):
                    for exc in exchanges:
                        supplier = exc.input
                        unit = (
                            upstream[lca.dicts.product[supplier.id]]
                            if kind == "technosphere"
                            else cf[lca.dicts.biosphere[supplier.id]]
                        )
                        contribution = purchase["amount"] * exc["amount"] * unit
                        ident = (
                            row["name"],
                            row["location"],
                            row["category"],
                            "manufacture/" + kind,
                            supplier["name"],
                            supplier.get("location", ""),
                            str(supplier.get("categories", "")),
                        )
                        values.setdefault(ident, {"before": 0, "after": 0})[
                            variant
                        ] += contribution
                        subtotal += contribution
                assert math.isclose(
                    subtotal,
                    purchase["amount"] * upstream[lca.dicts.product[production.id]],
                    rel_tol=2e-6,
                    abs_tol=1e-15,
                )

    rows = [
        dict(
            vehicle=k[0],
            location=k[1],
            category=k[2],
            exchange_type=k[3],
            supplier=k[4],
            supplier_location=k[5],
            categories=k[6],
            before=v["before"],
            after=v["after"],
            delta=v["after"] - v["before"],
        )
        for k, v in values.items()
    ]
    with (OUT / "incremental_ef31_contributions.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    summary = {}
    cases = (
        ("largest_decrease", min(scores, key=lambda r: float(r["percent_change"]))),
        ("largest_increase", largest_increase),
        (
            "medium_climate",
            next(
                r
                for r in scores
                if r["name"].endswith(", Medium")
                and r["location"] == "EUR"
                and r["category"] == "climate change"
            ),
        ),
    )
    for label, score in cases:
        subset = [
            r
            for r in rows
            if r["vehicle"] == score["name"]
            and r["location"] == score["location"]
            and r["category"] == score["category"]
        ]
        delta = float(score["absolute_change"])
        assert subset
        result = {"score": score}
        for nested, key in (
            (False, "root_components"),
            (True, "manufacturing_components"),
        ):
            selected_rows = [
                r
                for r in subset
                if r["exchange_type"].startswith("manufacture/") == nested
            ]
            result[key] = [
                dict(
                    supplier=r["supplier"],
                    delta=r["delta"],
                    share_of_net_delta_percent=r["delta"] / delta * 100,
                )
                for r in sorted(
                    selected_rows, key=lambda r: abs(r["delta"]), reverse=True
                )[:5]
            ]
        summary[label] = result
    (OUT / "contribution_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (OUT / "contribution_verification.json").write_text(
        json.dumps(
            {
                "selected_vehicle_indicator_pairs": len(selected),
                "databases": 2,
                "forward_and_adjoint_scores_agree": True,
                "root_and_nested_manufacture_contributions_reconcile": True,
                "matrix_factorization_reused_per_database": True,
            },
            indent=2,
        )
        + "\n"
    )
    for row in selected:
        components = sorted(
            (
                r
                for r in rows
                if r["category"] == row["category"] and r["vehicle"] == row["name"]
            ),
            key=lambda r: abs(r["delta"]),
            reverse=True,
        )
        print(
            row["name"],
            row["category"],
            [(r["supplier"], r["delta"]) for r in components[:5]],
        )


if __name__ == "__main__":
    main()
