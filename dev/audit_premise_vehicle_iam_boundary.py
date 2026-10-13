"""Audit exact car/truck IAM aliases against the controlled encrypted scenario.

Write coverage, units and normalized intensity only; keep raw IAM time series
and the decryption key out of reports and logs.
"""

import csv
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import yaml
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "premise"))
from premise.filesystem_constants import IAM_OUTPUT_DIR

OUT = ROOT / "carculator_utils/results/premise_vehicle_range_20261013"


def main():
    key = os.environ.get("PREMISE_KEY")
    if not key:
        skill = Path("/Users/romain/.codex/skills/premise/SKILL.md").read_text()
        key = re.search(r"```text\s+([^\s]+)\s+```", skill).group(1)
    source = IAM_OUTPUT_DIR / "remind_SSP2-NPi.csv"
    expected = json.loads(
        (
            ROOT
            / "carculator_utils/results/premise_vehicle_efficiency_20261013/build_2050.json"
        ).read_text()
    )["iam_files"][source.name]
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest == expected
    data = pd.read_csv(
        io.BytesIO(Fernet(key.encode()).decrypt(source.read_bytes())), sep=";"
    )
    data = data[data.Region == "EUR"].set_index("Variable")
    assert data.index.is_unique
    rows = []
    for family, filename in (
        ("car", "transport_passenger_cars.yaml"),
        ("truck", "transport_road_freight.yaml"),
    ):
        mapping = yaml.safe_load(
            (ROOT / "premise/premise/iam_variables_mapping" / filename).read_text()
        )
        for technology, spec in mapping.items():
            aliases = {
                role: spec.get(field, {}).get("remind")
                for role, field in (
                    ("service", "iam_aliases"),
                    ("energy", "energy_use_aliases"),
                )
            }
            lists = {
                role: (
                    []
                    if value is None
                    else value if isinstance(value, list) else [value]
                )
                for role, value in aliases.items()
            }
            missing = {
                role: [v for v in values if v not in data.index]
                for role, values in lists.items()
            }
            supported = all(lists.values()) and not any(missing.values())
            row = dict(
                family=family,
                technology=technology,
                has_remind_service_alias=bool(lists["service"]),
                complete_pair=supported,
            )
            for role in lists:
                row[f"{role}_aliases"] = json.dumps(lists[role])
                row[f"{role}_missing"] = json.dumps(missing[role])
                row[f"{role}_units"] = json.dumps(
                    sorted(
                        {
                            str(data.loc[v, "Unit"])
                            for v in lists[role]
                            if v in data.index
                        }
                    )
                )
            if supported:
                energy = data.loc[lists["energy"], ["2020", "2050"]].sum()
                service = data.loc[lists["service"], ["2020", "2050"]].sum()
                valid = bool((energy > 0).all() and (service > 0).all())
                for year in ("2020", "2050"):
                    row[f"positive_energy_and_service_in_{year}"] = bool(
                        energy[year] > 0 and service[year] > 0
                    )
                row["positive_energy_and_service_in_2020_and_2050"] = valid
                if valid:
                    row["2050_energy_intensity_ratio_raw"] = (
                        energy["2050"] / service["2050"]
                    ) / (energy["2020"] / service["2020"])
            rows.append(row)
    OUT.mkdir(exist_ok=True, parents=True)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (OUT / "iam_alias_coverage.csv").open("w") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)
    # Report candidate groups by names/units only; do not infer a technology
    # split from energy-carrier totals or split combined car/SUV classes.
    groups = data.loc[data.index.str.contains("Four Wheelers", regex=False)]
    names = [
        {"variable": name, "unit": row["Unit"]}
        for name, row in groups.iterrows()
        if name.startswith(("ES|", "FE|"))
    ]
    (OUT / "available_passenger_variables.json").write_text(
        json.dumps(names, indent=2) + "\n"
    )
    summary = {
        family: dict(
            total=sum(r["family"] == family for r in rows),
            declared_remind_mappings=sum(
                r["family"] == family and r["has_remind_service_alias"] for r in rows
            ),
            complete_pairs=sum(
                r["family"] == family and r["complete_pair"] for r in rows
            ),
        )
        for family in ("car", "truck")
    }
    summary.update(
        iam_sha256=digest,
        region="EUR",
        model="remind",
        pathway="SSP2-NPi",
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    (OUT / "iam_boundary_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    for family in ("car", "truck"):
        print(
            family,
            "matching service units",
            Counter(
                r["service_units"]
                for r in rows
                if r["family"] == family and r["service_units"] != "[]"
            ),
        )


if __name__ == "__main__":
    main()
