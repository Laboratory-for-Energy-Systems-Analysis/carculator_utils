"""Stage temporal energy assumptions without changing the 2025 anchors.

The output is reviewed before copying into the four vehicle repositories.
Original affected records and their ordering are retained in packaged provenance.
"""

import argparse
import copy
import hashlib
import json
from collections import defaultdict
from itertools import product
from pathlib import Path

PACKAGES = (
    "carculator",
    "carculator_bus",
    "carculator_truck",
    "carculator_two_wheeler",
)
LOSS_PARAMETERS = {
    "battery charge efficiency",
    "battery discharge efficiency",
    "charger efficiency",
}
GROUP = "13m-city-bev-base-auxiliary-transfer"


def cells(record):
    return product(
        [record["name"]], record["sizes"], record["powertrain"], [record["year"]]
    )


def effective(records):
    result = {}
    for key, record in records.items():
        for cell in cells(record):
            result.setdefault(cell, (key, record))
    return result


def rebase_loss(anchor, previous, reference):
    """Retain relative losses, with a constant prior when no loss trend exists."""
    if (
        previous is None
        or reference is None
        or not 0 < previous <= 1
        or not 0 < reference < 1
    ):
        return anchor, "constant prior; missing, zero or ideal legacy efficiency"
    value = 1 - (1 - anchor) * (1 - previous) / (1 - reference)
    if not 0 < value <= 1:
        raise ValueError(f"Nonphysical rebased efficiency: {value}")
    return value, "relative legacy loss trend rebased on 2025 component prior"


def harmonize(records, provenance):
    """Return revised records and an auditable, reversible change manifest."""
    if any(k.startswith("temporal-") for k in records):
        raise ValueError(
            "Already harmonized; use the archived original records to regenerate."
        )
    index = effective(records)
    years = sorted({r["year"] for r in records.values()})
    anchors = {
        k: records[k]
        for k, p in provenance["records"].items()
        if k in records and not p.get("endpoint_records")
    }
    supported = LOSS_PARAMETERS | {
        "electric motor efficiency",
        "electric transmission efficiency",
        "electric motor power share",
        "combustion power share",
        "auxiliary power base demand",
    }
    for key, anchor in anchors.items():
        if anchor["year"] != 2025 or anchor["name"] not in supported:
            raise ValueError(f"No temporal policy defined for {key!r}.")
    modifications, details = {}, {}
    for anchor_key, anchor in anchors.items():
        name = anchor["name"]
        for size, pt in product(anchor["sizes"], anchor["powertrain"]):

            def legacy(year):
                item = index.get((name, size, pt, year))
                # Depleted PHEV storage shares the charge-depleting battery.
                if (
                    item is None
                    and name == "battery discharge efficiency"
                    and pt in {"PHEV-c-p", "PHEV-c-d"}
                ):
                    item = index.get((name, size, "PHEV-e", year))
                return item

            endpoints = [legacy(y) for y in (2020, 2030)]
            reference = (
                sum(r[1]["amount"] for r in endpoints) / 2 if all(endpoints) else None
            )
            for year in years:
                if year == 2025 or (
                    name == "auxiliary power base demand" and year < 2020
                ):
                    continue
                prior = legacy(year)
                amount, method = (
                    anchor["amount"],
                    "constant 2025 component or architecture prior",
                )
                if name in LOSS_PARAMETERS:
                    amount, method = rebase_loss(
                        amount, prior[1]["amount"] if prior else None, reference
                    )
                elif name == "auxiliary power base demand":
                    method = "2020 test transfer, held constant thereafter; engineering uncertainty shared across years"
                record = copy.deepcopy(anchor)
                record.update(
                    year=year,
                    amount=amount,
                    loc=amount,
                    comment=anchor.get("comment", "")
                    + " Temporal extension: "
                    + method
                    + ". See temporal_energy_provenance.json.",
                )
                if name == "auxiliary power base demand":
                    record["uncertainty_group"] = GROUP
                cell = name, size, pt, year
                modifications[cell] = record
                details[cell] = {
                    "anchor_record": anchor_key,
                    "method": method,
                    "legacy_record": prior[0] if prior else None,
                    "legacy_2025_reference": (
                        reference if name in LOSS_PARAMETERS else None
                    ),
                }
    # Remove only modified Cartesian cells, preserving legacy first-entry ordering.
    revised, originals, added = {}, {}, []
    for key, record in records.items():
        if not any(cell in modifications for cell in cells(record)):
            revised[key] = copy.deepcopy(record)
            continue
        originals[key] = record
        remaining = defaultdict(list)
        for size in record["sizes"]:
            pts = tuple(
                pt
                for pt in record["powertrain"]
                if (record["name"], size, pt, record["year"]) not in modifications
            )
            if pts:
                remaining[pts].append(size)
        for n, (pts, sizes) in enumerate(remaining.items()):
            newkey = f"temporal-remainder-{key}-{n}"
            revised[newkey] = dict(record, sizes=sizes, powertrain=list(pts))
            added.append(newkey)
    # Group identical values/provenance, then form rectangles without adding cells.
    grouped = defaultdict(list)
    for cell, record in modifications.items():
        body = {k: v for k, v in record.items() if k not in {"sizes", "powertrain"}}
        grouped[json.dumps([body, details[cell]], sort_keys=True)].append(cell)
    changes = {}
    for signature, group_cells in grouped.items():
        body, detail = json.loads(signature)
        by_size = defaultdict(list)
        for _, size, pt, _ in group_cells:
            by_size[size].append(pt)
        rectangles = defaultdict(list)
        for size, pts in by_size.items():
            rectangles[tuple(sorted(pts))].append(size)
        for pts, sizes in rectangles.items():
            key = f'temporal-{len(changes):04d}-{body["year"]}-{body["name"]}'
            revised[key] = dict(body, sizes=sorted(sizes), powertrain=list(pts))
            changes[key] = detail
            added.append(key)
    for key, record in revised.items():
        if (
            record["year"] == 2025
            and record["name"] == "auxiliary power base demand"
            and key in anchors
        ):
            originals[key] = records[key]
            record["uncertainty_group"] = GROUP
    before, after = index, effective(revised)
    for cell, (_, record) in before.items():
        if cell not in modifications:
            left = {k: v for k, v in record.items() if k not in {"sizes", "powertrain"}}
            right = {
                k: v
                for k, v in after[cell][1].items()
                if k not in {"sizes", "powertrain", "uncertainty_group"}
            }
            if left != right:
                raise AssertionError(f"Unintended change: {cell}")
    for cell, record in modifications.items():
        if after[cell][1]["amount"] != record["amount"]:
            raise AssertionError(f"Shadowed change: {cell}")
    manifest = dict(
        schema_version=1,
        policy="Preserve 2025 anchors; rebase storage/charger losses; constant explicit component/architecture priors; 13m-city BEV auxiliaries 8.3 kW from 2020 onward.",
        uncertainty="Bus transfer uses one shared triangular draw across modern years; not an empirical confidence interval. Component priors and historical trend transfers are engineering assumptions.",
        original_key_order=list(records),
        original_records=originals,
        added_records=added,
        records=changes,
        changed_or_added_cells=len(modifications),
    )
    return revised, manifest


def restore(records, manifest):
    """Recover the exact original record mapping for audit comparisons."""
    merged = {k: v for k, v in records.items() if k not in manifest["added_records"]}
    merged.update(manifest["original_records"])
    return {key: merged[key] for key in manifest["original_key_order"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repositories-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    for package in PACKAGES:
        folder = args.repositories_root / package / package / "data"
        raw = (folder / "default_parameters.json").read_bytes()
        records = json.loads(raw)
        revised, manifest = harmonize(
            records, json.loads((folder / "defaults_2025_provenance.json").read_text())
        )
        assert restore(revised, manifest) == records
        manifest["original_file_sha256"] = hashlib.sha256(raw).hexdigest()
        dest = args.output / package
        dest.mkdir()
        (dest / "default_parameters.json").write_text(
            json.dumps(revised, indent=4) + "\n"
        )
        (dest / "temporal_energy_provenance.json").write_text(
            json.dumps(manifest, indent=2) + "\n"
        )
        print(
            package,
            manifest["changed_or_added_cells"],
            "cells;",
            len(manifest["records"]),
            "new records",
        )


if __name__ == "__main__":
    main()
