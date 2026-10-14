"""Install the FCEV battery-envelope calibration after bounding its coefficient changes."""

import csv
import json
import math
import shutil
from pathlib import Path

from audit_premise_vehicle_provenance import workbook_coefficients
from audit_premise_vehicle_workbooks import identity, read_workbook, write_csv
from premise_vehicle_provenance import digest

ROOT = Path(__file__).resolve().parents[1]
WORK = Path("/private/tmp/premise-fcev-buffer-20261014")
OUT = ROOT / "results/premise_fcev_buffer_20261014"
INVENTORIES = ROOT.parent / "premise/premise/data/additional_inventories"


def main():
    receipt = OUT / "installation.json"
    if receipt.exists():
        raise RuntimeError("Installation already recorded")
    records, sidecars, changes = [], [], []
    for family, label in (("trucks", "trucks"),):
        filename = f"lci-{label}.xlsx"
        before = {identity(d): d for d in read_workbook(INVENTORIES / filename)[0]}
        after = {identity(d): d for d in read_workbook(WORK / family / filename)[0]}
        assert before.keys() == after.keys(), "Vehicle catalogue changed"
        parameters = list(
            csv.DictReader((WORK / family / "vehicle_parameters.csv").open())
        )
        services = {r["name"] for r in parameters if r["powertrain"] == "FCEV"}
        allowed = {k for k, d in before.items() if d["name"] in services}
        for key in list(allowed):
            allowed.update(
                identity(e)
                for e in before[key]["exchanges"]
                if e["type"] == "technosphere"
                and e["unit"] == "unit"
                and e["name"]
                .lower()
                .startswith(("passenger car,", "lorry production,"))
            )
        changed = set()
        for key, ds in after.items():
            a, b = workbook_coefficients(before[key]), workbook_coefficients(ds)
            assert a.keys() == b.keys(), key
            for flow, old in a.items():
                new = b[flow]
                if math.isclose(old, new, rel_tol=1e-12, abs_tol=1e-18):
                    continue
                assert key in allowed, (key, flow)
                changed.add(key)
                changes.append(
                    dict(
                        family=family,
                        name=key[0],
                        flow=str(flow),
                        before=old,
                        after=new,
                        percent=(new / old - 1) * 100 if old else None,
                    )
                )
        assert changed == allowed and len(changed) == (14), changed
        records.append(
            dict(
                filename=filename,
                family=family,
                before_sha256=digest(INVENTORIES / filename),
                after_sha256=digest(WORK / family / filename),
                activities=len(after),
                changed_activities=len(changed),
            )
        )
        generation = json.loads(
            (WORK / family / "generation_provenance.json").read_text()
        )
        for artifact, suffix in (
            ("vehicle_parameters.csv", "parameters.csv"),
            ("noise_audit.csv", "noise.csv"),
        ):
            generation["artifacts"][artifact][
                "companion file"
            ] = f"lci-{label}.{suffix}"
        provenance = json.loads((WORK / family / "provenance.json").read_text())
        provenance["generation provenance"] = generation
        provenance.update(
            {
                "schema version": 2,
                "workbook": filename,
                "previous provenance": json.loads(
                    (INVENTORIES / f"lci-{label}.provenance.json").read_text()
                ),
            }
        )
        provenance_path = WORK / family / f"lci-{label}.provenance.json"
        provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")
        for source, suffix in (
            ("vehicle_parameters.csv", "parameters.csv"),
            ("noise_audit.csv", "noise.csv"),
            (provenance_path.name, "provenance.json"),
        ):
            name = f"lci-{label}.{suffix}"
            sidecars.append(
                dict(
                    filename=name,
                    family=family,
                    source=source,
                    before_sha256=digest(INVENTORIES / name),
                    after_sha256=digest(WORK / family / source),
                )
            )
    # All identities and coefficients are checked before any installed file changes.
    backup = WORK / "before"
    backup.mkdir(exist_ok=False)
    for record in records + sidecars:
        target = INVENTORIES / record["filename"]
        assert digest(target) == record["before_sha256"]
        shutil.copy2(target, backup / target.name)
        source = WORK / record["family"] / record.get("source", target.name)
        shutil.copy2(source, target)
        assert digest(target) == record["after_sha256"]
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / "template_changes.csv", changes)
    receipt.write_text(
        json.dumps(
            dict(
                files=records, sidecars=sidecars, script_sha256=digest(Path(__file__))
            ),
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
