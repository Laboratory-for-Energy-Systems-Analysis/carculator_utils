"""Build an isolated scenario to verify closed-form constant-range battery accounting."""

import argparse
import hashlib
import json
import os
import pickle
import re
import sys
import time
from collections.abc import Mapping
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "premise"
DEFAULT_WORK = Path("/private/tmp/premise-vehicle-battery-simple-20261013")
DEFAULT_OUTPUT = ROOT / "results/premise_vehicle_battery_simple_20261013"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plain(value):
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, choices=(2020, 2030, 2050), required=True)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--inventory-installation", type=Path, action="append", default=[]
    )
    parser.add_argument("--write-brightway", action="store_true")
    args = parser.parse_args()
    work = args.workspace.resolve()
    output = args.output.resolve()
    installations = [p.resolve() for p in args.inventory_installation]
    if not (work / "brightway").is_dir():
        parser.error("Copy the isolated Brightway directory into WORKSPACE/brightway.")
    if (output / f"build_{args.year}.json").exists():
        parser.error("Refusing to overwrite a completed build record.")
    run = work / str(args.year)
    run.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    (run / "variables.yaml").write_text(
        "USER_DATA_BASE_DIR: " + json.dumps(str(run / "cache")) + "\n"
    )
    os.chdir(run)
    os.environ["BRIGHTWAY2_DIR"] = str(work / "brightway")
    sys.path.insert(0, str(SOURCE))
    import bw2data as bd
    import numpy as np
    from premise import NewDatabase
    from premise.filesystem_constants import IAM_OUTPUT_DIR, INVENTORY_DIR

    bd.projects.set_current("ecoinvent-3.12-cutoff")
    key = os.environ.get("PREMISE_KEY")
    if not key:
        skill = Path("/Users/romain/.codex/skills/premise/SKILL.md").read_text()
        key = re.search(r"```text\s+([^\s]+)\s+```", skill).group(1)
    scenario = {"model": "remind", "pathway": "SSP2-NPi", "year": args.year}
    baseline = json.loads(
        (
            ROOT / "results/premise_vehicle_intensity_20261013/build_2050.json"
        ).read_text()
    )
    meta = {
        "scenario": scenario,
        "source_database": "ecoinvent-3.12-cutoff",
        "biosphere": "ecoinvent-3.12-biosphere",
        "encrypted_iam": True,
        "python": sys.version,
        "numpy_runtime": np.__version__,
        "packages": {
            name: metadata.version(name)
            for name in ("premise", "bw2data", "bw2io", "bw2calc", "numpy")
        },
        "workbooks": {p.name: digest(p) for p in sorted(INVENTORY_DIR.glob("*.xlsx"))},
        "python_sources": {
            str(p.relative_to(SOURCE)): digest(p)
            for p in sorted((SOURCE / "premise").rglob("*.py"))
        },
        "build_script_sha256": digest(Path(__file__).resolve()),
        "transport_mapping_sources": {
            str(p.relative_to(SOURCE)): digest(p)
            for p in sorted(
                (SOURCE / "premise/iam_variables_mapping").glob("transport_*.yaml")
            )
        },
        "fuel_properties_sha256": digest(
            SOURCE / "premise/iam_variables_mapping/fuels.yaml"
        ),
        "persistent_user_database_written": False,
    }
    installed = json.loads(
        (
            ROOT / "results/premise_vehicle_battery_simple_20261013/installation.json"
        ).read_text()
    )
    expected_workbooks = dict(baseline["workbooks"])
    for record in installed["files"]:
        assert expected_workbooks[record["filename"]] == record["before_sha256"]
        expected_workbooks[record["filename"]] = record["after_sha256"]
    for manifest in installations:
        for record in json.loads(manifest.read_text())["files"]:
            assert expected_workbooks[record["filename"]] == record["before_sha256"]
            expected_workbooks[record["filename"]] = record["after_sha256"]
    meta["additional_inventory_installations"] = [
        {"path": str(p), "sha256": digest(p)} for p in installations
    ]
    assert meta["workbooks"] == expected_workbooks, "Unrecorded workbook changes."
    meta["baseline_audit"] = "premise_vehicle_intensity_20261013"
    assert meta["fuel_properties_sha256"] == baseline["fuel_properties_sha256"]
    meta["changed_python_sources_since_audit"] = [
        name
        for name, value in meta["python_sources"].items()
        if baseline["python_sources"].get(name) != value
    ]
    started = time.monotonic()
    ndb = NewDatabase(
        scenarios=[scenario.copy()],
        source_db=meta["source_database"],
        source_version="3.12",
        source_type="brightway",
        system_model="cutoff",
        biosphere_name=meta["biosphere"],
        key=key,
        inventory_backend="compact",
        generate_reports=False,
        keep_source_db_uncertainty=False,
        keep_imports_uncertainty=False,
        cleanup_expired_caches=False,
        use_cached_inventories=False,
        use_cached_database=False,
    )
    import premise.transport as transport_module

    timings = []
    original_sizing = transport_module.resize_regional_batteries

    def timed_sizing(transport):
        start = time.perf_counter()
        before_count = len(transport.database)
        original_sizing(transport)
        timings.append(
            {
                "family": transport.vehicle_type,
                "seconds": time.perf_counter() - start,
                "new_production_activities": len(transport.database) - before_count,
            }
        )

    transport_module.resize_regional_batteries = timed_sizing
    ndb.update()
    meta["battery_sizing_timings"] = timings
    report = ndb.get_validation_report(scenario=0)
    (output / f"validation_{args.year}.json").write_text(
        json.dumps(report.to_dict(), indent=2) + "\n"
    )
    data = plain(ndb.materialize_inventory(scenario=0))
    inventory = run / "database.pickle"
    with inventory.open("wb") as stream:
        pickle.dump(data, stream, pickle.HIGHEST_PROTOCOL)
    meta.update(
        activities=len(data),
        exchanges=sum(len(ds["exchanges"]) for ds in data),
        validation_errors=len(report.errors),
        validation_warnings=len(report.warnings),
        seconds=time.monotonic() - started,
        private_inventory_path=str(inventory),
        private_inventory_sha256=digest(inventory),
        iam_files={
            str(p.relative_to(IAM_OUTPUT_DIR)): digest(p)
            for p in sorted(IAM_OUTPUT_DIR.rglob("*"))
            if p.is_file() and "SSP2-NPi" in p.name
        },
    )
    installation = json.loads(
        (
            ROOT / "results/premise_vehicle_intensity_20261013/installation.json"
        ).read_text()
    )
    expected_iam = {
        record["filename"]: record["after_sha256"]
        for record in installation["scenarios"]
        if "SSP2-NPi" in record["filename"]
    }
    assert meta["iam_files"] == expected_iam, "Restored IAM provenance mismatch."
    (output / f"build_{args.year}.json").write_text(json.dumps(meta, indent=2) + "\n")
    report.raise_for_errors()
    if args.write_brightway:
        from verify_premise_vehicle_provenance import verify_saved

        name = f"premise-remind-SSP2-NPi-{args.year}-{work.name}"
        if name in bd.databases:
            raise ValueError(f"Refusing to overwrite {name}")
        expected = {
            (d["name"], d["reference product"], d["location"], d["unit"]): d
            for d in data
            if "vehicle inventory provenance" in d or "inventory provenance" in d
        }
        ndb.write_db_to_brightway(name=name)
        saved = verify_saved(name, expected, args.year)
        saved.update(database=name, brightway_directory=str(bd.projects.dir))
        (output / f"saved_{args.year}.json").write_text(
            json.dumps(saved, indent=2) + "\n"
        )
    print("BUILD COMPLETE", args.year, meta["activities"], flush=True)


if __name__ == "__main__":
    main()
