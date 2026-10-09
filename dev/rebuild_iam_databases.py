"""Build one isolated premise background for the carculator matrix refresh.

Use a copied Brightway project and pass PREMISE_KEY through the environment.
The static database includes premise's supplementary inventories but applies
no scenario transformations. Prospective databases apply all default sectors.
Existing databases are never overwritten. See the companion matrix compiler.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import sys
import time
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str) + "\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--source-db", default="ecoinvent-3.12-cutoff")
    parser.add_argument("--biosphere", default="ecoinvent-3.12-biosphere")
    parser.add_argument("--premise-version", default="2.5.4")
    parser.add_argument("--pathway", default="SSP2-NPi")
    parser.add_argument("--year", type=int, default=2020)
    parser.add_argument("--static", action="store_true")
    parser.add_argument("--name", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--inspect-only", action="store_true")
    args = parser.parse_args()
    if not os.environ.get("PREMISE_KEY"):
        parser.error("Set PREMISE_KEY for encrypted IAM data; no plaintext fallback.")
    version = importlib.metadata.version("premise")
    if version != args.premise_version:
        parser.error(f"Expected premise {args.premise_version}, found {version}.")

    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    # Premise reads this documented configuration before initializing caches.
    # A dedicated cache avoids deleting or reusing another study's checkpoints.
    work = workspace / "work"
    work.mkdir(exist_ok=True)
    config = work / "variables.yaml"
    content = (
        "USER_DATA_BASE_DIR: " + json.dumps(str(workspace / "premise-cache")) + "\n"
    )
    if config.exists() and config.read_text() != content:
        raise ValueError(f"Conflicting cache configuration: {config}")
    config.write_text(content)
    os.chdir(work)

    import bw2data as bd

    if args.project not in bd.projects:
        raise ValueError(f"Missing project {args.project!r}; copy the source first.")
    previous = bd.projects.current
    try:
        bd.projects.set_current(args.project)
        if args.source_db not in bd.databases or args.biosphere not in bd.databases:
            raise ValueError("The exact ecoinvent source and biosphere must exist.")
        if args.name in bd.databases:
            raise ValueError(f"Refusing to overwrite existing database {args.name!r}.")

        from premise import NewDatabase
        from premise.filesystem_constants import IAM_OUTPUT_DIR, INVENTORY_DIR

        record = {
            "premise_version": version,
            "python": sys.version,
            "project": args.project,
            "source_db": args.source_db,
            "source_version": "3.12",
            "system_model": "cutoff",
            "biosphere": args.biosphere,
            "database": args.name,
            "scenario": {"model": "remind", "pathway": args.pathway, "year": args.year},
            "static": args.static,
            "inventory_backend": "compact",
            "keep_source_db_uncertainty": False,
            "keep_imports_uncertainty": False,
            "encrypted_iam": True,
            "supplementary_inventory_hashes": {
                p.name: digest(p) for p in sorted(INVENTORY_DIR.glob("*.xlsx"))
            },
        }
        reports = workspace / "database-reports"
        reports.mkdir(exist_ok=True)
        report_path = reports / (args.name + ".json")
        started = time.monotonic()
        print(
            json.dumps(
                {
                    k: v
                    for k, v in record.items()
                    if k != "supplementary_inventory_hashes"
                }
            ),
            flush=True,
        )
        ndb = NewDatabase(
            scenarios=[record["scenario"].copy()],
            source_db=args.source_db,
            source_version="3.12",
            source_type="brightway",
            system_model="cutoff",
            biosphere_name=args.biosphere,
            key=os.environ["PREMISE_KEY"],
            inventory_backend="compact",
            generate_reports=False,
            keep_source_db_uncertainty=False,
            keep_imports_uncertainty=False,
            cleanup_expired_caches=False,
        )
        if not args.static:
            ndb.update()
            validation = ndb.get_validation_report(scenario=0)
            validation.raise_for_errors()
        store = ndb.get_inventory_store(scenario=0)
        record["activity_count"] = len(store)
        record["iam_files"] = {
            str(p.relative_to(IAM_OUTPUT_DIR)): digest(p)
            for p in sorted(IAM_OUTPUT_DIR.rglob("*"))
            if p.is_file() and args.pathway in p.name
        }
        if not record["iam_files"]:
            raise ValueError(
                "No matching IAM file recorded; inspect scenario provenance."
            )
        if args.inspect_only:
            # Metadata only: no proprietary full inventories in the report.
            record["activity_labels"] = [
                [
                    a.get("name"),
                    a.get("location"),
                    a.get("unit"),
                    a.get("reference product"),
                ]
                for a in store.iter_activities()
            ]
            record["written"] = False
        else:
            ndb.write_db_to_brightway(name=args.name)
            record["written"] = args.name in bd.databases
            if not record["written"]:
                raise RuntimeError(
                    "Brightway export returned without creating the database."
                )
            record["written_activity_count"] = len(bd.Database(args.name))
        record["seconds"] = time.monotonic() - started
        write_json(report_path, record)
        print(f"Completed: {report_path}", flush=True)
    finally:
        bd.projects.set_current(previous)


if __name__ == "__main__":
    main()
