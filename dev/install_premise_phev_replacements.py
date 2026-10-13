"""Install freshly generated PHEV-replacement corrections with a guarded rollback."""

import csv
import hashlib
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path

from audit_premise_vehicle_workbooks import identity, read_workbook, write_csv

ROOT = Path(__file__).resolve().parents[1]
WORK = Path("/private/tmp/premise-vehicle-replacements-20261013")
OUT = ROOT / "results/premise_vehicle_replacements_20261013"
INVENTORIES = ROOT.parent / "premise/premise/data/additional_inventories"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def coefficients(dataset):
    result = defaultdict(float)
    for exchange in dataset["exchanges"]:
        result[
            (exchange["type"], identity(exchange), exchange.get("categories"))
        ] += exchange["amount"]
    return result


def main():
    OUT.mkdir(exist_ok=True)
    receipt = OUT / "workbook_installation.json"
    if receipt.exists():
        raise RuntimeError("Refusing to overwrite a completed installation")
    baseline = json.loads(
        (ROOT / "results/premise_vehicle_phev_20261013/build_2020.json").read_text()
    )
    backups = WORK / "baseline"
    backups.mkdir(exist_ok=True)
    records, changes, pending = {}, [], []
    for family, label in (("cars", "pass_cars"), ("trucks", "trucks")):
        candidate = WORK / family
        target = INVENTORIES / f"lci-{label}.xlsx"
        assert digest(target) == baseline["workbooks"][target.name]
        previous = {identity(d): d for d in read_workbook(target)[0]}
        updated = {identity(d): d for d in read_workbook(candidate / target.name)[0]}
        assert previous.keys() == updated.keys()
        material_changes, roundoff_changes, maximum_roundoff = 0, 0, 0
        for key in previous:
            a, b = coefficients(previous[key]), coefficients(updated[key])
            assert a.keys() == b.keys(), key
            for exchange in a:
                if a[exchange] == b[exchange]:
                    continue
                delta = b[exchange] - a[exchange]
                if math.isclose(a[exchange], b[exchange], rel_tol=1e-6, abs_tol=1e-12):
                    roundoff_changes += 1
                    maximum_roundoff = max(maximum_roundoff, abs(delta))
                    continue
                assert family == "trucks" and key[0].startswith(
                    "lorry production, plugin"
                )
                assert exchange[0] == "technosphere"
                assert exchange[1][0] == "market for battery capacity (MIX scenario)"
                assert b[exchange] < a[exchange]
                changes.append(
                    dict(
                        vehicle=key[0],
                        old_kWh=a[exchange],
                        new_kWh=b[exchange],
                        increase_percent=100 * delta / a[exchange],
                    )
                )
                material_changes += 1
        assert material_changes == (7 if family == "trucks" else 0)
        old_parameters = list(
            csv.DictReader((INVENTORIES / f"lci-{label}.parameters.csv").open())
        )
        new_parameters = list(
            csv.DictReader((candidate / "vehicle_parameters.csv").open())
        )
        assert [r["name"] for r in old_parameters] == [
            r["name"] for r in new_parameters
        ]
        for before, after in zip(old_parameters, new_parameters):
            for field in (
                "energy battery mass",
                "curb mass",
                "driving mass",
                "TtW energy",
                "fuel consumption",
                "electricity consumption",
            ):
                assert math.isclose(
                    float(before[field]),
                    float(after[field]),
                    rel_tol=1e-6,
                    abs_tol=1e-12,
                ), (before["name"], field)
        record = {
            "before sha256": digest(target),
            "after sha256": digest(candidate / target.name),
            "datasets": len(updated),
            "material exchange changes": material_changes,
            "float-rounding exchange changes": roundoff_changes,
            "maximum rounding absolute difference": maximum_roundoff,
            "raw model inventory sha256": digest(candidate / "raw.json"),
            "model parameters sha256": digest(candidate / "model_parameters.json"),
            "installer sha256": digest(Path(__file__)),
        }
        provenance = json.loads((candidate / "provenance.json").read_text())
        provenance["phev_replacement_correction"] = {
            **record,
            "policy": "Truck net lifetime electric energy is weighted before subtracting the first pack; cars use the approved 200000 vehicle-km and 18-year limits; each count belongs to the physical pack",
            "prior provenance sha256": digest(
                INVENTORIES / f"lci-{label}.provenance.json"
            ),
        }
        (candidate / "provenance.json").write_text(
            json.dumps(provenance, indent=2) + "\n"
        )
        files = {
            target.name: target.name,
            f"lci-{label}.parameters.csv": "vehicle_parameters.csv",
            f"lci-{label}.noise.csv": "noise_audit.csv",
            f"lci-{label}.provenance.json": "provenance.json",
        }
        record["files"] = {}
        for destination, source in files.items():
            original = INVENTORIES / destination
            backup = backups / destination
            assert not backup.exists(), backup
            shutil.copyfile(original, backup)
            record["files"][destination] = {
                "before sha256": digest(original),
                "after sha256": digest(candidate / source),
                "private backup": str(backup),
            }
            pending.append((candidate / source, original))
        records[target.name] = record
    # Verify both families before changing either installed workbook.
    for source, target in pending:
        if digest(source) != digest(target):
            shutil.copyfile(source, target)
    write_csv(OUT / "truck_lifetime_capacity_changes.csv", changes)
    receipt.write_text(json.dumps(records, indent=2) + "\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
