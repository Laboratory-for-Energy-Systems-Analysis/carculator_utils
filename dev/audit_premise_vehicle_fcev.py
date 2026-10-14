"""Bound FCEV correction effects in the full 2020 and 2050 Premise builds."""

import json
import math
import pickle
from collections import Counter
from pathlib import Path

from audit_premise_vehicle_battery import warning_counts
from audit_premise_vehicle_carbon import coefficients, key, write_csv
from audit_premise_vehicle_payload import digest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/premise_vehicle_fcev_20261014"
WORK = Path("/private/tmp/premise-vehicle-fcev-20261014")
OLD_OUT = ROOT / "results/premise_vehicle_plausibility_20261014/after"
OLD_WORK = Path("/private/tmp/premise-vehicle-plausibility-20261014")


def compare_models():
    old = json.loads((OLD_WORK / "probe/model_snapshot.json").read_text())
    new = json.loads((WORK / "probe/model_snapshot.json").read_text())
    fields = [
        "battery power",
        "electric energy stored",
        "battery cell mass",
        "battery BoP mass",
        "energy battery mass",
        "curb mass",
        "driving mass",
        "TtW energy",
        "fuel consumption",
        "fuel cell power",
        "battery lifetime replacements",
    ]
    rows = []
    for family in old:
        assert old[family].keys() == new[family].keys()
        for vehicle, before in old[family].items():
            after = new[family][vehicle]
            if not vehicle.endswith("|FCEV"):
                for p in fields:
                    assert math.isclose(
                        before[p], after[p], rel_tol=1e-12, abs_tol=1e-18
                    ), (family, vehicle, p)
                continue
            assert math.isclose(
                after["battery cell mass"] / after["energy battery mass"],
                after["battery cell mass share"],
                rel_tol=2e-6,
            )
            assert math.isclose(
                after["fuel cell power"] / after["fuel cell own consumption"]
                + after["battery power"],
                after["power"],
                rel_tol=2e-6,
            )
            for p in fields:
                a, b = before[p], after[p]
                rows.append(
                    dict(
                        family=family,
                        vehicle=vehicle,
                        parameter=p,
                        before=a,
                        after=b,
                        percent=(b / a - 1) * 100 if a else None,
                    )
                )
    write_csv(OUT / "model_changes.csv", rows)


def main():
    compare_models()
    differences, summary = [], {}
    for year in (2020, 2050):
        old_meta = json.loads((OLD_OUT / f"build_{year}.json").read_text())
        new_meta = json.loads((OUT / f"build_{year}.json").read_text())
        for field in (
            "iam_files",
            "fuel_properties_sha256",
            "python_sources",
            "transport_mapping_sources",
        ):
            assert new_meta[field] == old_meta[field], field
        databases = []
        for work, meta in ((OLD_WORK, old_meta), (WORK, new_meta)):
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
                spec = ds.get("vehicle inventory provenance", {})
                if isinstance(spec, str):
                    spec = json.loads(spec)
                assert (
                    spec.get("family") == "car"
                    and spec.get("model powertrain") == "FCEV"
                ), (ident, flow)
                changed.add(ident)
                differences.append(
                    dict(
                        year=year,
                        name=ds["name"],
                        location=ds["location"],
                        flow=flow[1],
                        unit=flow[4],
                        before=before,
                        after=after,
                        percent=(after / before - 1) * 100 if before else None,
                    )
                )
        before_warnings = warning_counts(OLD_OUT / f"validation_{year}.json")
        after_warnings = warning_counts(OUT / f"validation_{year}.json")
        assert new_meta["validation_errors"] == 0
        assert before_warnings == after_warnings
        summary[year] = dict(
            activities=len(new),
            exchanges=new_meta["exchanges"],
            changed_activities=len(changed),
            changed_locations=dict(Counter(k[2] for k in changed)),
            validation_errors=0,
            validation_warnings=new_meta["validation_warnings"],
            warning_identities_unchanged=True,
            all_other_coefficients_unchanged=True,
        )
    write_csv(OUT / "scenario_changes.csv", differences)
    (OUT / "change_scope_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
