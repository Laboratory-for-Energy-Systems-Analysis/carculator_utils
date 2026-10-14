"""Isolate the PHEV pack correction across the 16 EF 3.1 headline indicators.

The comparison is against the immediately preceding verified vehicle update,
not the original legacy vehicle workbook. One vehicle-km, RER plus EUR, 2020.
Use the private Brightway copy after both scenario exports have completed.
"""

import csv
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/premise_vehicle_phev_calibration_20261014"
OLD = ROOT / "results/premise_vehicle_deterioration_20261014"
WORK = Path("/private/tmp/premise-vehicle-phev-calibration-20261014")


def main():
    os.environ["BRIGHTWAY2_DIR"] = str(WORK / "brightway")
    import bw2calc as bc
    import bw2data as bd

    bd.projects.set_current("ecoinvent-3.12-cutoff")
    methods = sorted(
        m
        for m in bd.methods
        if m[:2] == ("ecoinvent-3.12", "EF v3.1")
        and not m[2].startswith("climate change:")
        and ", organics" not in m[2]
        and ", inorganics" not in m[2]
    )
    assert len(methods) == 16
    results, counts = {}, {}
    for variant, directory in (("before", OLD), ("after", OUT)):
        database = json.loads((directory / "saved_2020.json").read_text())["database"]
        selected = {}
        for activity in bd.Database(database):
            if activity.get("location") not in {"EUR", "RER"}:
                continue
            provenance = activity.get("vehicle inventory provenance", {})
            if isinstance(provenance, str):
                provenance = json.loads(provenance)
            if (
                provenance.get("family") == "car"
                and provenance.get("model powertrain", "").startswith("PHEV-")
                and provenance.get("role") == "transport service"
            ):
                ident = tuple(
                    activity[k]
                    for k in ("name", "reference product", "location", "unit")
                )
                assert ident not in selected
                assert activity["unit"] == "kilometer"
                selected[ident] = activity
        counts[variant] = len(selected)
        assert sum(k[2] == "RER" for k in selected) == 16
        assert any(k[2] == "EUR" for k in selected)
        results[variant] = {}
        lca = bc.LCA({next(iter(selected.values())).id: 1}, methods[0])
        lca.lci()
        lca.lcia()
        for ident, activity in sorted(selected.items()):
            lca.redo_lci({activity.id: 1})
            for method in methods:
                lca.switch_method(method)
                lca.lcia()
                assert math.isfinite(lca.score)
                results[variant][ident, method] = lca.score
        print(variant, len(selected), "PHEVs calculated", flush=True)
    assert results["before"].keys() == results["after"].keys()
    rows = []
    for (ident, method), before in results["before"].items():
        after = results["after"][ident, method]
        rows.append(
            dict(
                name=ident[0],
                location=ident[2],
                functional_unit="one vehicle-kilometre",
                category=method[2],
                method=json.dumps(method),
                unit=bd.methods[method]["unit"],
                before=before,
                after=after,
                absolute_change=after - before,
                percent_change=(after / before - 1) * 100 if before else None,
            )
        )
    with (OUT / "incremental_ef31.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    summary = dict(
        comparison="Approved PHEV calibration versus preceding deterioration-corrected vehicles",
        legacy_workbook_comparison=False,
        year=2020,
        scenario="REMIND SSP2-NPi",
        source="ecoinvent 3.12 cutoff",
        selected_counts=counts,
        categories=len(methods),
        paired_scores=len(rows),
        persistent_user_project_modified=False,
        category_ranges={
            category: dict(
                min_percent=min(
                    r["percent_change"] for r in rows if r["category"] == category
                ),
                max_percent=max(
                    r["percent_change"] for r in rows if r["category"] == category
                ),
            )
            for category in sorted({r["category"] for r in rows})
        },
    )
    (OUT / "incremental_ef31_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
