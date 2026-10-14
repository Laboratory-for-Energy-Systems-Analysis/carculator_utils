"""Read back provenance and operating-energy suppliers from an isolated Brightway DB."""

import math

FIELDS = (
    "source",
    "model",
    "model version",
    "model publication",
    "vehicle inventory provenance",
    "inventory provenance",
    "premise vehicle provenance",
    "premise vehicle battery sizing",
    "vehicle battery sizing",
    "vehicle lpg policy",
)


def verify_saved(name, expected, year):
    import bw2calc as bc
    import bw2data as bd

    found, energy_checks, examples = set(), 0, []
    method = next(
        m
        for m in bd.methods
        if m[:3] == ("ecoinvent-3.12", "EF v3.1", "climate change")
    )
    for activity in bd.Database(name):
        identity = tuple(
            activity.get(k) for k in ("name", "reference product", "location", "unit")
        )
        if identity not in expected:
            continue
        found.add(identity)
        original = expected[identity]
        for field in FIELDS:
            assert activity.get(field) == original.get(field), (identity, field)
        state = activity.get("premise vehicle provenance", {})
        if state.get("operating energy inputs"):
            actual = {}
            for exc in activity.technosphere():
                supplier = exc.input
                key = tuple(
                    supplier.get(k)
                    for k in ("name", "reference product", "location", "unit")
                )
                actual[key] = actual.get(key, 0) + exc["amount"]
            wanted = {}
            for exc in state["operating energy inputs"]:
                key = tuple(exc[k] for k in ("name", "product", "location", "unit"))
                wanted[key] = wanted.get(key, 0) + exc["amount"]
            for key, amount in wanted.items():
                assert math.isclose(actual[key], amount, rel_tol=1e-12, abs_tol=1e-18)
                energy_checks += 1
        if identity[2] == "EUR" and identity[0] in {
            "transport, passenger car, battery electric, Medium",
            "transport, freight, lorry, battery electric, 40 metric ton",
        }:
            examples.append(activity)
    assert found == expected.keys(), expected.keys() - found
    assert len(examples) == 2, [a["name"] for a in examples]
    lca, scores = None, []
    for activity in examples:
        if lca is None:
            lca = bc.LCA({activity.id: 1}, method)
            lca.lci()
            lca.lcia()
        else:
            lca.redo_lcia({activity.id: 1})
        assert math.isfinite(lca.score) and lca.score > 0
        scores.append(
            dict(
                name=activity["name"],
                location="EUR",
                unit=activity["unit"],
                year=year,
                score=lca.score,
                method=method,
            )
        )
    return dict(
        metadata_activities=len(found),
        metadata_fields=list(FIELDS),
        operating_energy_links_checked=energy_checks,
        metadata_exactly_preserved=True,
        smoke_scores=scores,
        persistent_user_database_written=False,
    )
