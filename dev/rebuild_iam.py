"""Rebuild isolated premise databases, then compile a candidate A/B resource set.

Nothing is copied into package data automatically. Set PREMISE_KEY in the
environment and use a Brightway project containing a copy of ecoinvent 3.12
cutoff and its biosphere and LCIA methods. See docs/background_rebuild.rst.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PREMISE_VERSION = "2.5.4"
PREFIX = "carculator-ei312-premise254"
YEARS = (2005, 2010, 2020, 2030, 2040, 2050)
PATHWAYS = ("SSP2-NPi", "SSP2-PkBudg1000", "SSP2-PkBudg650")


def database_plan():
    yield {
        "name": PREFIX + "-static",
        "pathway": "SSP2-NPi",
        "year": 2020,
        "static": True,
    }
    for pathway in PATHWAYS:
        for year in YEARS if pathway == "SSP2-NPi" else YEARS[3:]:
            yield {
                "name": f"{PREFIX}-{pathway}-{year}",
                "pathway": pathway,
                "year": year,
                "static": False,
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--compile-only", action="store_true")
    parser.add_argument("--legacy-catalogue", type=Path)
    parser.add_argument("--legacy-39-catalogue", type=Path)
    args = parser.parse_args()
    if args.build_only and args.compile_only:
        parser.error("Choose at most one stage restriction")
    workspace = args.workspace.resolve()
    logs = workspace / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    scripts = Path(__file__).resolve().parent
    if not args.compile_only:
        for item in database_plan():
            report = workspace / "database-reports" / (item["name"] + ".json")
            if args.resume and report.exists():
                record = json.loads(report.read_text())
                if (
                    record.get("written") is True
                    and record.get("premise_version") == PREMISE_VERSION
                    and record.get("project") == args.project
                    and record.get("static") == item["static"]
                    and record.get("scenario")
                    == {
                        "model": "remind",
                        "pathway": item["pathway"],
                        "year": item["year"],
                    }
                ):
                    print(f"Already built: {item['name']}", flush=True)
                    continue
                raise ValueError(f"Incompatible/incomplete build manifest: {report}")
            command = [
                sys.executable,
                str(scripts / "rebuild_iam_databases.py"),
                "--project",
                args.project,
                "--workspace",
                str(workspace),
                "--name",
                item["name"],
                "--pathway",
                item["pathway"],
                "--year",
                str(item["year"]),
            ]
            if item["static"]:
                command.append("--static")
            print(f"Building: {item['name']}", flush=True)
            with (logs / (item["name"] + ".log")).open("w") as log:
                subprocess.run(
                    command, stdout=log, stderr=subprocess.STDOUT, check=True
                )
    if not args.build_only:
        command = [
            sys.executable,
            str(scripts / "compile_iam_matrices.py"),
            "--project",
            args.project,
            "--workspace",
            str(workspace),
        ]
        if args.legacy_catalogue:
            command.extend(["--legacy-catalogue", str(args.legacy_catalogue.resolve())])
        if args.legacy_39_catalogue:
            command.extend(
                ["--legacy-39-catalogue", str(args.legacy_39_catalogue.resolve())]
            )
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
