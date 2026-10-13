"""Install only the approved H2-pressure adaptation and explicit compression role."""

import copy
import csv
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

from audit_premise_vehicle_workbooks import identity, read_workbook, write_csv
from regenerate_premise_cars import (
    HYDROGEN_COMPRESSION_KEY,
    hydrogen_compression_specification,
    write_workbook,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
INVENTORIES = ROOT.parent / "premise/premise/data/additional_inventories"
OUT = ROOT / "results/premise_vehicle_hydrogen_20261013"
PRIVATE = Path("/private/tmp/premise-vehicle-hydrogen-20261013/baseline")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def comparable(value):
    if isinstance(value, dict):
        return {
            k: comparable(v)
            for k, v in value.items()
            if k not in {"row", "sheet", "workbook", "database"}
        }
    if isinstance(value, list):
        return [comparable(v) for v in value]
    return value


def assert_equivalent(left, right):
    if isinstance(left, dict):
        assert left.keys() == right.keys()
        for key in left:
            assert_equivalent(left[key], right[key])
    elif isinstance(left, list):
        assert len(left) == len(right)
        for a, b in zip(left, right):
            assert_equivalent(a, b)
    elif isinstance(left, float):
        assert math.isclose(left, right, rel_tol=1e-14, abs_tol=1e-18), (left, right)
    else:
        assert left == right, (left, right)


def main():
    from carculator_utils.inventory import hydrogen_compression_electricity

    OUT.mkdir(exist_ok=True)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    receipt = OUT / "workbook_installation.json"
    if receipt.exists():
        raise RuntimeError(
            "Completed installation receipt exists; refusing to overwrite"
        )
    specification = hydrogen_compression_specification()
    old_intensity = hydrogen_compression_electricity(25, 700)
    new_intensity = specification["electricity kWh per kg H2"]
    rows, records = [], {}
    for family in ("pass_cars", "trucks"):
        path = INVENTORIES / f"lci-{family}.xlsx"
        baseline = PRIVATE / path.name
        if not baseline.exists():
            shutil.copyfile(path, baseline)
        before_hash = digest(baseline)
        before = read_workbook(baseline)[0]
        after = copy.deepcopy(before)
        expected = {}
        for dataset in after:
            if not dataset["name"].startswith("transport,"):
                continue
            hydrogen = [
                e
                for e in dataset["exchanges"]
                if e["type"] == "technosphere"
                and e.get("reference product") == specification["hydrogen product"]
            ]
            if not hydrogen:
                continue
            assert len(hydrogen) == 1 and hydrogen[0]["unit"] == "kilogram"
            electricity = [
                e
                for e in dataset["exchanges"]
                if e["type"] == "technosphere"
                and e.get("reference product") == specification["electricity product"]
            ]
            assert len(electricity) == 1
            exchange = electricity[0]
            assert "compression" in exchange.get("comment", "").lower()
            assert math.isclose(
                exchange["amount"] / hydrogen[0]["amount"], old_intensity, rel_tol=1e-6
            )
            old_amount = exchange["amount"]
            exchange["amount"] = hydrogen[0]["amount"] * new_intensity
            exchange["comment"] = (
                f"Hydrogen tank compression, 30 to 700 bar: {new_intensity:.12g} kWh/kg H2; "
                "model compressor assumptions and documented Premise pipeline delivery pressure."
            )
            dataset[HYDROGEN_COMPRESSION_KEY] = json.dumps(specification)
            expected[dataset["name"]] = exchange["amount"]
            rows.append(
                dict(
                    workbook=path.name,
                    vehicle=dataset["name"],
                    unit=dataset["unit"],
                    hydrogen_kg=hydrogen[0]["amount"],
                    old_electricity_kWh=old_amount,
                    new_electricity_kWh=exchange["amount"],
                    old_kWh_per_kg=old_intensity,
                    new_kWh_per_kg=new_intensity,
                )
            )
        assert expected
        write_workbook(path, after)
        parsed = read_workbook(path)[0]
        assert len(parsed) == len(before)
        for a, b, planned in zip(before, parsed, after):
            assert identity(a) == identity(b)
            assert_equivalent(comparable(planned), comparable(b))
            if a["name"] not in expected:
                assert comparable(a) == comparable(b)
        parameters = INVENTORIES / f"lci-{family}.parameters.csv"
        parameters_hash = digest(parameters)
        if family == "trucks":
            with parameters.open() as stream:
                values = list(csv.DictReader(stream))
            for row in values:
                if row["name"] in expected:
                    row["h2_compression_kWh_per_tkm"] = expected[row["name"]]
            write_csv(parameters, values)
        provenance_path = INVENTORIES / f"lci-{family}.provenance.json"
        provenance = json.loads(provenance_path.read_text())
        provenance["sha256"] = digest(path)
        provenance["hydrogen_compression_adaptation"] = {
            **specification,
            "previous generic inlet pressure bar": 25,
            "previous electricity kWh per kg H2": old_intensity,
            "previous workbook sha256": before_hash,
            "services updated": len(expected),
            "installer sha256": digest(Path(__file__)),
            "policy": "Only compression electricity and its metadata change; hydrogen and hardware unchanged",
        }
        provenance_path.write_text(json.dumps(provenance, indent=2) + "\n")
        records[path.name] = {
            "before sha256": before_hash,
            "after sha256": digest(path),
            "services updated": len(expected),
            "parameters before sha256": parameters_hash,
            "parameters after sha256": digest(parameters),
        }
    write_csv(OUT / "template_compression_changes.csv", rows)
    receipt.write_text(json.dumps(records, indent=2) + "\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
