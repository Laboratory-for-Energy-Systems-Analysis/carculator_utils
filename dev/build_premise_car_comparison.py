"""Build one full, isolated REMIND SSP2-NPi 2020 comparison database.

Run once for old cars and once for regenerated cars, with separate premise source
trees and caches. BRIGHTWAY2_DIR must point to an isolated project copy.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--premise-source", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--variant", choices=("old", "new"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", default="20261012-final")
    args = parser.parse_args()
    if not os.environ.get("BRIGHTWAY2_DIR") or not os.environ.get("PREMISE_KEY"):
        parser.error(
            "Set BRIGHTWAY2_DIR to isolated copy and PREMISE_KEY to encrypted IAM key."
        )
    source = args.premise_source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    work = args.workspace.resolve() / args.variant
    work.mkdir(parents=True, exist_ok=True)
    (work / "variables.yaml").write_text(
        "USER_DATA_BASE_DIR: " + json.dumps(str(work / "cache")) + "\n"
    )
    os.chdir(work)
    sys.path.insert(0, str(source))
    import bw2data as bd
    from premise import NewDatabase
    from premise.filesystem_constants import IAM_OUTPUT_DIR, INVENTORY_DIR

    bd.projects.set_current("ecoinvent-3.12-cutoff")
    name = f"premise-remind-SSP2-NPi-2020-cars-{args.variant}-{args.run_id}"
    if name in bd.databases:
        raise ValueError(f"Refusing to overwrite {name}")
    record = dict(
        variant=args.variant,
        project=bd.projects.current,
        brightway_directory=str(bd.projects.dir),
        database=name,
        source_database="ecoinvent-3.12-cutoff",
        biosphere="ecoinvent-3.12-biosphere",
        scenario={"model": "remind", "pathway": "SSP2-NPi", "year": 2020},
        premise_source=str(source),
        encrypted_iam=True,
        workbooks={p.name: digest(p) for p in sorted(INVENTORY_DIR.glob("*.xlsx"))},
    )
    started = time.monotonic()
    ndb = NewDatabase(
        scenarios=[record["scenario"].copy()],
        source_db=record["source_database"],
        source_version="3.12",
        source_type="brightway",
        system_model="cutoff",
        biosphere_name=record["biosphere"],
        key=os.environ["PREMISE_KEY"],
        inventory_backend="compact",
        generate_reports=False,
        keep_source_db_uncertainty=False,
        keep_imports_uncertainty=False,
        cleanup_expired_caches=False,
        use_cached_inventories=False,
        use_cached_database=False,
    )
    ndb.update()
    report = ndb.get_validation_report(scenario=0)
    (output / f"{args.variant}_validation.json").write_text(
        json.dumps(report.to_dict(), indent=2) + "\n"
    )
    record["validation_errors"] = len(report.errors)
    record["validation_warnings"] = len(report.warnings)
    report.raise_for_errors()
    store = ndb.get_inventory_store(scenario=0)
    record["activity_count"] = len(store)
    record["iam_files"] = {
        str(p.relative_to(IAM_OUTPUT_DIR)): digest(p)
        for p in sorted(IAM_OUTPUT_DIR.rglob("*"))
        if p.is_file() and "SSP2-NPi" in p.name
    }
    ndb.write_db_to_brightway(name=name)
    record["written_activity_count"] = len(bd.Database(name))
    record["seconds"] = time.monotonic() - started
    (output / f"{args.variant}_build.json").write_text(
        json.dumps(record, indent=2) + "\n"
    )
    print("BUILD COMPLETE", name, record["seconds"], flush=True)


if __name__ == "__main__":
    main()
