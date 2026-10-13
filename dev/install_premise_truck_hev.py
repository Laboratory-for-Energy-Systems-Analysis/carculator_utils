"""Install the HEV-only truck change after checking identities and controls."""

import csv
import json
import math
import shutil
from pathlib import Path

from audit_premise_vehicle_workbooks import identity, read_workbook, write_csv
from install_premise_phev_replacements import coefficients, digest

ROOT = Path(__file__).resolve().parents[1]
WORK = Path("/private/tmp/premise-truck-hev-20261013")
OUT = ROOT / "results/premise_truck_hev_storage_20261013"
INVENTORIES = ROOT.parent / "premise/premise/data/additional_inventories"


def main():
    candidate = WORK / "trucks"
    receipt = OUT / "workbook_installation.json"
    prior = json.loads(receipt.read_text()) if receipt.exists() else None
    baseline = json.loads(
        (
            ROOT / "results/premise_vehicle_replacements_20261013/build_2020.json"
        ).read_text()
    )
    target = INVENTORIES / "lci-trucks.xlsx"
    original_workbook = WORK / "baseline" / target.name if prior else target
    assert digest(original_workbook) == baseline["workbooks"][target.name]
    if prior:
        for name, record in prior[target.name]["files"].items():
            assert digest(INVENTORIES / name) == record["after sha256"], name
            assert digest(WORK / "baseline" / name) == record["before sha256"], name
    before = {identity(d): d for d in read_workbook(original_workbook)[0]}
    after = {identity(d): d for d in read_workbook(candidate / target.name)[0]}
    assert before.keys() == after.keys()
    changes, changed = [], set()
    for key in before:
        a, b = coefficients(before[key]), coefficients(after[key])
        for exchange in a.keys() | b.keys():
            old, new = a.get(exchange, 0), b.get(exchange, 0)
            if math.isclose(old, new, rel_tol=1e-6, abs_tol=1e-12):
                continue
            assert any(
                key[0].startswith(prefix)
                for prefix in (
                    "transport, freight, lorry, diesel hybrid,",
                    "transport, freight, lorry, gasoline hybrid,",
                    "lorry production, diesel hybrid,",
                )
            ), (key, exchange)
            if exchange not in a:
                assert exchange[1][0] == "market for battery capacity (MIX scenario)"
                assert new > 0 and key[0].startswith("lorry production,")
            assert exchange in b, (key, exchange)
            changed.add(key)
            changes.append(
                dict(vehicle=key[0], exchange=exchange[1][0], before=old, after=new)
            )
    assert (
        len(changed) == 16
    )  # nine services (including gasoline proxies), seven vehicles
    old_parameter_path = (
        WORK / "baseline" if prior else INVENTORIES
    ) / "lci-trucks.parameters.csv"
    old_parameters = list(csv.DictReader(old_parameter_path.open()))
    new_parameters = list(csv.DictReader((candidate / "vehicle_parameters.csv").open()))
    assert [p["name"] for p in old_parameters] == [p["name"] for p in new_parameters]
    parameter_changes = []
    for old, new in zip(old_parameters, new_parameters):
        if old["powertrain"] != "HEV-d":
            for label in (
                "energy battery mass",
                "curb mass",
                "TtW energy",
                "battery lifetime replacements",
            ):
                assert math.isclose(
                    float(old[label]), float(new[label]), rel_tol=1e-6, abs_tol=1e-9
                )
            continue
        assert float(old["electric energy stored"]) == 0
        assert 0 < float(new["electric energy stored"]) < 20
        assert 0 < float(new["HEV regeneration reuse fraction"]) <= 1
        parameter_changes.append(
            dict(
                name=new["name"],
                size=new["size"],
                nominal_kWh=new["electric energy stored"],
                physical_pack_kg=new["energy battery mass"],
                replacements=new["battery lifetime replacements"],
                lifetime_capacity_kWh=new["battery_capacity_with_replacements_kWh"],
                reused_braking_fraction=new["HEV regeneration reuse fraction"],
                fuel_increase_percent=100
                * (float(new["TtW energy"]) / float(old["TtW energy"]) - 1),
            )
        )
    assert len(parameter_changes) == 9
    provenance = json.loads((candidate / "provenance.json").read_text())
    for source, value in provenance["source_sha256"].items():
        path = Path(source) if Path(source).is_absolute() else ROOT.parent / source
        assert digest(path) == value, source
    backups = WORK / "baseline"
    backups.mkdir(exist_ok=True)
    record = {
        "before sha256": digest(original_workbook),
        "after sha256": digest(candidate / target.name),
        "datasets": len(after),
        "changed_activities": len(changed),
        "files": {},
    }
    pending = []
    for destination, source in {
        "lci-trucks.xlsx": "lci-trucks.xlsx",
        "lci-trucks.parameters.csv": "vehicle_parameters.csv",
        "lci-trucks.provenance.json": "provenance.json",
        "lci-trucks.noise.csv": "noise_audit.csv",
    }.items():
        original, backup = INVENTORIES / destination, backups / destination
        if not prior:
            assert not backup.exists()
            shutil.copyfile(original, backup)
        record["files"][destination] = {
            "before sha256": digest(backup),
            "after sha256": digest(candidate / source),
            "private backup": str(backup),
        }
        pending.append((candidate / source, original))
    for source, destination in pending:
        if digest(source) != digest(destination):
            shutil.copyfile(source, destination)
    write_csv(OUT / "workbook_exchange_changes.csv", changes)
    write_csv(OUT / "hev_2020_changes.csv", parameter_changes)
    receipt.write_text(json.dumps({target.name: record}, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
