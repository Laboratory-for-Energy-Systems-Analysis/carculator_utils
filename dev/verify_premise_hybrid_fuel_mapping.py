"""Bound the numerical effects of the missing petrol mapping correction."""

import csv
import json
import math
import pickle
from pathlib import Path

from audit_premise_vehicle_battery import warning_counts
from audit_premise_vehicle_carbon import coefficients, key, write_csv
from audit_premise_vehicle_payload import digest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/premise_vehicle_plausibility_20261014"
WORK = Path("/private/tmp/premise-vehicle-plausibility-20261014")
OLD = ROOT / "results/premise_vehicle_provenance_20261014"
BEFORE = Path("/private/tmp/premise-vehicle-provenance-20261014")


def main():
    with (OUT / "before/fuel_energy_checks.csv").open() as stream:
        failed = {
            (int(r["year"]), r["name"], r["location"]): r
            for r in csv.DictReader(stream)
            if r["passed"] == "False"
        }
    differences, summary = [], {}
    for year in (2020, 2050):
        new_meta = json.loads((OUT / f"after/build_{year}.json").read_text())
        old_meta = json.loads((OLD / f"build_{year}.json").read_text())
        for field in (
            "workbooks",
            "iam_files",
            "fuel_properties_sha256",
            "python_sources",
        ):
            assert new_meta[field] == old_meta[field], field
        assert {
            k
            for k, v in new_meta["transport_mapping_sources"].items()
            if v != old_meta["transport_mapping_sources"][k]
        } == {"premise/iam_variables_mapping/transport_passenger_cars.yaml"}
        databases = []
        for work, meta in ((BEFORE, old_meta), (WORK, new_meta)):
            path = work / str(year) / "database.pickle"
            assert digest(path) == meta["private_inventory_sha256"]
            with path.open("rb") as stream:
                databases.append({key(d): d for d in pickle.load(stream)})
        old, new = databases
        assert old.keys() == new.keys()
        changed = set()
        for ident, ds in new.items():
            a, b = coefficients(old[ident]), coefficients(ds)
            assert a.keys() == b.keys(), ident
            for flow, before in a.items():
                after = b[flow]
                if math.isclose(before, after, rel_tol=1e-12, abs_tol=1e-18):
                    continue
                changed.add(ident)
                expected = failed[year, ds["name"], ds["location"]]
                factor = float(expected["expected_MJ_per_service"]) / float(
                    expected["delivered_MJ_per_service"]
                )
                assert flow[1] in {
                    "market for petrol, low-sulfur",
                    "Carbon dioxide, fossil",
                    "Carbon dioxide, non-fossil",
                }, (ident, flow)
                assert math.isclose(after, before * factor, rel_tol=1e-9, abs_tol=1e-15)
                differences.append(
                    dict(
                        year=year,
                        name=ds["name"],
                        location=ds["location"],
                        flow=flow[1],
                        unit=flow[4],
                        before=before,
                        after=after,
                        ratio=factor,
                    )
                )
        assert {(year, k[0], k[2]) for k in changed} == {
            k for k in failed if k[0] == year
        }
        # Diagnostics may change when their hot-reference denominator changes;
        # never treat these heuristic warnings as emissions-limit failures.
        before_warnings = warning_counts(OLD / f"validation_{year}.json")
        after_warnings = warning_counts(OUT / f"after/validation_{year}.json")
        assert new_meta["validation_errors"] == 0
        summary[year] = dict(
            activities=len(new),
            changed_activities=len(changed),
            validation_errors=new_meta["validation_errors"],
            validation_warnings=new_meta["validation_warnings"],
            added_warning_instances=sum((after_warnings - before_warnings).values()),
            removed_warning_instances=sum((before_warnings - after_warnings).values()),
        )
    write_csv(OUT / "hybrid_mapping_changes.csv", differences)
    (OUT / "change_scope_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
