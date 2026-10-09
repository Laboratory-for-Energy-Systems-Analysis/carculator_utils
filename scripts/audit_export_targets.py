"""Audit pre-generated Brightway exports against existing destination databases.

Run in the destination Brightway environment. Input is JSON: a list of records
with ``package``, ``version`` and ``data`` (the bw2io export's activity list).
No database contents are created or modified. Output reports exact matches and
unresolved identities; it does not claim cross-version LCIA equivalence.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def audit(records):
    import bw2data as bd

    previous = bd.projects.current
    reports = []
    try:
        for version in sorted({record["version"] for record in records}):
            project = f"ecoinvent-{version}-cutoff"
            if project not in bd.projects:
                raise ValueError(f"Existing destination project required: {project}")
            bd.projects.set_current(project)
            biosphere_name = f"ecoinvent-{version}-biosphere"
            if project not in bd.databases or biosphere_name not in bd.databases:
                raise ValueError(
                    f"Exact destination databases required: {project}, {biosphere_name}"
                )
            technology, biosphere = defaultdict(list), defaultdict(list)
            for activity in bd.Database(project):
                technology[
                    (
                        activity["name"],
                        activity.get("reference product"),
                        activity.get("location"),
                        activity["unit"],
                    )
                ].append(activity.key)
            for flow in bd.Database(biosphere_name):
                biosphere[
                    (flow["name"], tuple(flow.get("categories", ())), flow["unit"])
                ].append(flow.key)
            for record in records:
                if record["version"] != version:
                    continue
                data = record["data"]
                foreground = {
                    (a["name"], a["reference product"], a["location"], a["unit"])
                    for a in data
                }
                counts, unresolved = Counter(), {}
                for activity in data:
                    for exchange in activity["exchanges"]:
                        if exchange["type"] == "production":
                            continue
                        if exchange["type"] == "technosphere":
                            key = (
                                exchange["name"],
                                exchange.get(
                                    "reference product", exchange.get("product")
                                ),
                                exchange.get("location"),
                                exchange["unit"],
                            )
                            if key in foreground:
                                counts["foreground"] += 1
                                continue
                            matches = technology.get(key, [])
                        else:
                            key = (
                                exchange["name"],
                                tuple(exchange.get("categories", ())),
                                exchange["unit"],
                            )
                            matches = biosphere.get(key, [])
                        if len(matches) == 1:
                            counts[exchange["type"]] += 1
                        elif exchange["amount"] != 0:
                            unresolved[str(key)] = {
                                "type": exchange["type"],
                                "matches": len(matches),
                            }
                reports.append(
                    {
                        "package": record["package"],
                        "version": version,
                        "project": project,
                        "biosphere_database": biosphere_name,
                        "matched": dict(counts),
                        "unresolved": unresolved,
                    }
                )
    finally:
        bd.projects.set_current(previous)
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = audit(json.loads(args.input.read_text()))
    args.output.write_text(json.dumps(reports, indent=2) + "\n")
    print([(r["package"], r["version"], len(r["unresolved"])) for r in reports])
