"""Explain the largest incremental FCEV changes using exchange contributions."""

import csv
import json
import math
import os

import numpy as np
from scipy.sparse.linalg import spsolve

from compare_premise_fcev_dc import OLD, OUT, WORK


def main():
    os.environ["BRIGHTWAY2_DIR"] = str(WORK / "brightway")
    import bw2calc as bc
    import bw2data as bd

    bd.projects.set_current("ecoinvent-3.12-cutoff")
    scores = list(csv.DictReader((OUT / "incremental_ef31.csv").open()))
    selected = [
        max(
            (
                r
                for r in scores
                if r["category"] == category
                and family in r["name"]
                and r["location"] == "EUR"
            ),
            key=lambda r: abs(float(r["percent_change"])),
        )
        for category in ("acidification", "climate change")
        for family in ("passenger car", "freight")
    ]
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
        for row in selected:
            activity = activities[row["name"], row["location"]]
            lca.switch_method(tuple(json.loads(row["method"])))
            cf = np.asarray(lca.characterization_matrix.sum(axis=0)).ravel()
            direct = np.asarray(lca.biosphere_matrix.T @ cf).ravel()
            upstream = spsolve(lca.technosphere_matrix.T.tocsc(), direct)
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
