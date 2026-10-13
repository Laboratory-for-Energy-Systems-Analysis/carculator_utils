"""Read original REMIND outputs and audit vehicle intensity coverage.

The originals and installed encrypted scenarios are read only. Reports contain
names, units, coverage, hashes and normalized changes, not raw IAM time series.
Run with the Python 3.12 Premise environment (pandas, NumPy, YAML, cryptography).
"""

import argparse
import ast
import hashlib
import io
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from cryptography.fernet import Fernet

REPOSITORIES = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = Path(
    "/Users/romain/Library/CloudStorage/Dropbox/Notebooks/IAM-ecoinvent"
)
DEFAULT_OUTPUT = (
    REPOSITORIES / "carculator_utils/results/premise_original_vehicle_iam_20261013"
)
INDEX = ["Region", "Variable", "Unit"]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mappings():
    result = []
    directory = REPOSITORIES / "premise/premise/iam_variables_mapping"
    for family, filename in (
        ("car", "transport_passenger_cars.yaml"),
        ("truck", "transport_road_freight.yaml"),
    ):
        for technology, specification in yaml.safe_load(
            (directory / filename).read_text()
        ).items():
            service = specification.get("iam_aliases", {}).get("remind")
            if service is None:
                continue
            # These current REMIND mappings each refer to one technology.
            assert isinstance(service, str) and service.startswith("ES|")
            result.append(
                {
                    "family": family,
                    "technology": technology,
                    "service": service,
                    "energy": specification["energy_use_aliases"]["remind"],
                    "intensity": "Energy intensity|" + service.removeprefix("ES|"),
                }
            )
    return result


def audit_source(path, root, mapping, coverage):
    data = pd.read_csv(path, sep=";")
    assert not data.duplicated(INDEX).any(), path
    label = str(path.relative_to(root))
    eur = data.loc[data.Region == "EUR"].set_index("Variable")
    assert eur.index.is_unique, path
    intensity = data.Variable.str.startswith("Energy intensity|")
    for specification in mapping:
        variable = specification["intensity"]
        present = variable in eur.index
        row = {
            "source": label,
            "family": specification["family"],
            "technology": specification["technology"],
            "intensity_variable": variable,
            "regions_with_intensity": ";".join(
                sorted(data.loc[data.Variable == variable, "Region"].unique())
            ),
            "eur_service_present": specification["service"] in eur.index,
            "eur_requested_energy_present": specification["energy"] in eur.index,
            "eur_intensity_present": present,
        }
        if present:
            observation = eur.loc[variable]
            baseline, future = float(observation["2020"]), float(observation["2050"])
            valid = bool(
                np.isfinite([baseline, future]).all() and baseline > 0 and future > 0
            )
            row.update(unit=observation.Unit, positive_2020_and_2050=valid)
            if valid:
                row["raw_2050_over_2020_intensity"] = future / baseline
                row["raw_change_percent"] = 100 * (future / baseline - 1)
        coverage.append(row)
    return {
        "source": label,
        "sha256": sha256(path),
        "rows": len(data),
        "scenarios": sorted(data.Scenario.unique().tolist()),
        "regions": sorted(data.Region.unique().tolist()),
        "intensity_rows": int(intensity.sum()),
        "eur_intensity_rows": int((intensity & (data.Region == "EUR")).sum()),
        "intensity_units": sorted(data.loc[intensity, "Unit"].unique().tolist()),
        "extended_intensity_or_load_variables": sorted(
            {
                variable.split("|")[0]
                for variable in data.Variable.unique()
                if any(
                    part in variable.lower()
                    for part in (
                        "energy intensity sales",
                        "energy intensity (raw)",
                        "load factor",
                        "annual mileage",
                    )
                )
            }
        ),
    }


def installed_scenario():
    key = os.environ.get("PREMISE_KEY")
    if not key:
        instructions = Path("/Users/romain/.codex/skills/premise/SKILL.md").read_text()
        match = re.search(r"```text\s+([^\s]+)\s+```", instructions)
        if match is None:
            raise RuntimeError("Set PREMISE_KEY to read the installed scenario.")
        key = match.group(1)
    path = REPOSITORIES / "premise/premise/data/iam_output_files/remind_SSP2-NPi.csv"
    payload = Fernet(key.encode()).decrypt(path.read_bytes())
    return path, pd.read_csv(io.BytesIO(payload), sep=";")


def lineage(root, installed):
    packaged = installed.set_index(INDEX)
    assert packaged.index.is_unique
    records = []
    for relative in (
        "remind 3.5/REMIND_generic_SSP2-NPi2025.mif",
        "remind 3.5.2/REMIND_generic_SSP2-NPi2025.mif",
        "remind 3.5.2/allocated/REMIND_generic_SSP2-NPi2025_feedstock.mif",
        "remind 3.5.2/allocated/REMIND_generic_SSP2-NPi2025_feedstock_filtered.csv",
        "remind 3.5.2/allocated/REMIND_generic_SSP2-NPi2025_feedstock_filtered_filtered.csv",
    ):
        path = root / relative
        source = pd.read_csv(path, sep=";")
        duplicates = source.duplicated(INDEX, keep=False)
        # Do not resolve conflicting duplicates by assuming first/last/sum.
        unique = source.loc[~duplicates].set_index(INDEX)
        shared = packaged.index.intersection(unique.index)
        years = [column for column in packaged if column.isdigit() and column in unique]
        left = packaged.loc[shared, years].to_numpy(float)
        right = unique.loc[shared, years].to_numpy(float)
        equal = (left == right) | (np.isnan(left) & np.isnan(right))
        close = np.isclose(left, right, rtol=1e-10, atol=1e-12, equal_nan=True)
        differing_variables = sorted(
            set(shared[~close.all(axis=1)].get_level_values("Variable"))
        )
        records.append(
            {
                "source": relative,
                "sha256": sha256(path),
                "rows": len(source),
                "duplicate_identity_rows_excluded": int(duplicates.sum()),
                "intensity_rows": int(
                    source.Variable.str.startswith("Energy intensity|").sum()
                ),
                "packaged_rows": len(packaged),
                "common_unique_rows": len(shared),
                "years_compared": years,
                "cells_compared": equal.size,
                "exactly_equal_cells": int(equal.sum()),
                "numerically_equal_cells": int(close.sum()),
                "all_packaged_rows_and_values_match": bool(
                    len(shared) == len(packaged) and close.all()
                ),
                "nonmatching_variable_count": len(differing_variables),
                "nonmatching_variable_examples": differing_variables[:10],
            }
        )
    assert records[-1]["all_packaged_rows_and_values_match"]
    return records


def filter_evidence(root):
    path = root / "encryption/encryption.ipynb"
    notebook = json.loads(path.read_text())
    matches = []
    for index, cell in enumerate(notebook["cells"]):
        source = "".join(cell.get("source", []))
        if "l_var" not in source or "startswith" not in source:
            continue
        for statement in ast.parse(source).body:
            if isinstance(statement, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "l_var"
                for target in statement.targets
            ):
                prefixes = ast.literal_eval(statement.value)
                matches.append(
                    {
                        "cell_index_zero_based": index,
                        "kept_prefixes": prefixes,
                        "keeps_energy_intensity": any(
                            "Energy intensity|Transport".startswith(prefix)
                            for prefix in prefixes
                        ),
                    }
                )
    assert matches and not any(match["keeps_energy_intensity"] for match in matches)
    return {
        "source": str(path.relative_to(root)),
        "sha256": sha256(path),
        "matching_cells": matches,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    files = sorted((args.source / "remind 3.5.2").glob("*.mif"))
    files += [
        args.source / "remind 3.5/REMIND_generic_SSP2-NPi2025.mif",
        args.source / "old/remind 3.2/remind_SSP2-NPi.mif",
    ]
    files += sorted((args.source / "remind 3-5-MagPie").glob("*.mif"))
    coverage = []
    mapping = mappings()
    inventory = [audit_source(path, args.source, mapping, coverage) for path in files]
    packaged_path, packaged = installed_scenario()
    summary = {
        "script_sha256": sha256(Path(__file__)),
        "installed_scenario_sha256": sha256(packaged_path),
        "installed_intensity_rows": int(
            packaged.Variable.str.startswith("Energy intensity|").sum()
        ),
        "lineage": lineage(args.source, packaged),
        "filter_evidence": filter_evidence(args.source),
        "originals": inventory,
    }
    frame = pd.DataFrame(coverage)
    summaries = []
    for (source, family), subset in frame.groupby(["source", "family"], sort=False):
        summaries.append(
            {
                "source": source,
                "family": family,
                "declared_mappings": len(subset),
                "eur_intensity_present": int(subset.eur_intensity_present.sum()),
                "eur_positive_2020_and_2050": int(
                    subset.positive_2020_and_2050.eq(True).sum()
                ),
            }
        )
    args.output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output / "coverage.csv", index=False)
    pd.DataFrame(summaries).to_csv(args.output / "coverage_summary.csv", index=False)
    (args.output / "source_audit.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    print(f"Audited {len(files)} original scenario files; reports: {args.output}")
    print("Packaged scenario matches final filtered 3.5.2 values: verified")
    for record in summaries:
        if record["source"] == "remind 3.5.2/REMIND_generic_SSP2-NPi2025.mif":
            print(json.dumps(record))


if __name__ == "__main__":
    main()
