"""Install LPG metadata only, preserving every other field and exchange quantity."""

import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path

import openpyxl

from audit_premise_vehicle_workbooks import identity, read_workbook
from premise_vehicle_lpg_metadata import SPEC_KEY, attach_lpg_policy

ROOT = Path(__file__).resolve().parents[1]
WORK = Path("/private/tmp/premise-vehicle-lpg-20261014")
OUT = ROOT / "results/premise_vehicle_lpg_20261014"
INVENTORIES = ROOT.parent / "premise/premise/data/additional_inventories"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(value):
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items() if k != "row"}
    if isinstance(value, list):
        return [normalized(v) for v in value]
    return value


def main():
    if (OUT / "installation.json").exists():
        raise RuntimeError("Installation already recorded")
    (WORK / "candidates").mkdir(parents=True, exist_ok=True)
    records = []
    for filename, expected_count in (("lci-pass_cars.xlsx", 1), ("lci-trucks.xlsx", 4)):
        installed, candidate = INVENTORIES / filename, WORK / "candidates" / filename
        before = read_workbook(installed)[0]
        expected = deepcopy(before)
        assert not any(SPEC_KEY in ds for ds in before)
        for ds in expected:
            attach_lpg_policy(ds)
            if SPEC_KEY in ds:
                ds[SPEC_KEY] = json.dumps(ds[SPEC_KEY])
        changed = [ds for ds in expected if SPEC_KEY in ds]
        assert len(changed) == expected_count
        workbook = openpyxl.load_workbook(installed)
        for ds in sorted(changed, key=lambda d: d["row"], reverse=True):
            sheet = workbook[ds["sheet"]]
            row = ds["row"] + 1
            while str(sheet.cell(row, 1).value).lower() != "exchanges":
                if str(sheet.cell(row, 1).value).lower() == "comment":
                    sheet.cell(row, 2, ds["comment"])
                row += 1
                assert row <= sheet.max_row
            sheet.insert_rows(row)
            sheet.cell(row, 1, SPEC_KEY)
            sheet.cell(row, 2, ds[SPEC_KEY])
        workbook.save(candidate)
        workbook.close()
        actual = read_workbook(candidate)[0]
        assert {identity(d): normalized(d) for d in actual} == {
            identity(d): normalized(d) for d in expected
        }
        records.append(
            dict(
                filename=filename,
                before_sha256=digest(installed),
                after_sha256=digest(candidate),
                activities=len(actual),
                lpg_services=expected_count,
                all_exchange_fields_unchanged=True,
                only_service_comments_and_lpg_contracts_changed=True,
            )
        )
    (WORK / "before").mkdir(exist_ok=False)
    for record in records:
        installed = INVENTORIES / record["filename"]
        assert digest(installed) == record["before_sha256"]
        shutil.copy2(installed, WORK / "before" / installed.name)
        shutil.copy2(WORK / "candidates" / installed.name, installed)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = dict(
        files=records,
        installer_sha256=digest(Path(__file__)),
        generator_sources={
            name: digest(ROOT / "dev" / name)
            for name in (
                "premise_vehicle_lpg_metadata.py",
                "regenerate_premise_cars.py",
                "regenerate_premise_trucks.py",
            )
        },
    )
    (OUT / "installation.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
