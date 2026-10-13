"""Install sizing metadata only after proving all existing workbook data identical."""

import hashlib
import json
import shutil
from pathlib import Path

from audit_premise_vehicle_workbooks import identity, read_workbook
from premise_vehicle_battery_metadata import SPEC_KEY

ROOT = Path(__file__).resolve().parents[1]
WORK = Path("/private/tmp/premise-vehicle-battery-simple-20261013")
OUT = ROOT / "results/premise_vehicle_battery_simple_20261013"
INVENTORIES = ROOT.parent / "premise/premise/data/additional_inventories"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def existing_fields(dataset):
    return {
        key: [existing_fields(e) for e in value] if key == "exchanges" else value
        for key, value in dataset.items()
        if key not in {"row", SPEC_KEY}
    }


def main():
    manifest = OUT / "installation.json"
    if manifest.exists():
        raise RuntimeError("Installation already recorded")
    records = []
    for family, filename in (
        ("cars", "lci-pass_cars.xlsx"),
        ("trucks", "lci-trucks.xlsx"),
    ):
        installed, generated = INVENTORIES / filename, WORK / family / filename
        before = read_workbook(installed)[0]
        after = read_workbook(generated)[0]
        assert {identity(d): existing_fields(d) for d in before} == {
            identity(d): existing_fields(d) for d in after
        }, "Existing inventories or metadata changed"
        assert not any(SPEC_KEY in d for d in before)
        records.append(
            {
                "family": family,
                "filename": filename,
                "before_sha256": digest(installed),
                "after_sha256": digest(generated),
                "activities": len(after),
                "sizing_contracts": sum(SPEC_KEY in d for d in after),
                "all_existing_fields_and_exchanges_identical": True,
            }
        )
    backup = WORK / "before"
    backup.mkdir(exist_ok=False)
    for record in records:
        installed = INVENTORIES / record["filename"]
        assert digest(installed) == record["before_sha256"]
        shutil.copy2(installed, backup / installed.name)
        shutil.copy2(WORK / record["family"] / installed.name, installed)
    OUT.mkdir(exist_ok=True, parents=True)
    manifest.write_text(
        json.dumps(
            {
                "script_sha256": digest(Path(__file__)),
                "files": records,
                "generation_scripts": {
                    p.name: digest(p)
                    for p in (
                        ROOT / "dev/premise_vehicle_battery_metadata.py",
                        ROOT / "dev/regenerate_premise_cars.py",
                        ROOT / "dev/regenerate_premise_trucks.py",
                    )
                },
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(records))


if __name__ == "__main__":
    main()
