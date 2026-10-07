"""Export native 2025 input records with their per-record provenance and hashes."""

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

PACKAGES = (
    "carculator",
    "carculator_bus",
    "carculator_truck",
    "carculator_two_wheeler",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repositories-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    records, provenance = [], {}
    for package in PACKAGES:
        repo = args.repositories_root / package
        folder = repo / package / "data"
        source = folder / "default_parameters.json"
        raw = source.read_bytes()
        metadata = folder / "defaults_2025_provenance.json"
        details = json.loads(metadata.read_text())
        selected = {
            key: value
            for key, value in json.loads(raw).items()
            if value["year"] == 2025
        }
        for key, record in selected.items():
            records.append(
                dict(
                    package=package,
                    record_id=key,
                    **record,
                    provenance=details["records"][key],
                )
            )
        provenance[package] = dict(
            git_head=subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
            ).strip(),
            default_parameters_sha256=hashlib.sha256(raw).hexdigest(),
            provenance_sha256=hashlib.sha256(metadata.read_bytes()).hexdigest(),
            record_count=len(selected),
        )
    (args.output / "defaults_2025.json").write_text(
        json.dumps(records, indent=2) + "\n"
    )
    (args.output / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )
    columns = [
        "package",
        "record_id",
        "name",
        "sizes",
        "powertrain",
        "year",
        "unit",
        "amount",
        "uncertainty_type",
        "loc",
        "minimum",
        "maximum",
        "source",
        "comment",
    ]
    with (args.output / "defaults_2025.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    key: (
                        json.dumps(record[key])
                        if isinstance(record.get(key), list)
                        else record.get(key, "")
                    )
                    for key in columns
                }
            )
    print(f"Exported {len(records)} records from {len(PACKAGES)} packages")


if __name__ == "__main__":
    main()
