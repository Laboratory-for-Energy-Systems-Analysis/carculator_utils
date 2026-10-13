"""Verify the approved Large Car efficiency proxy without sharing fleet volumes."""

import contextlib
import hashlib
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import yaml

from audit_premise_vehicle_intensity import (
    IAM,
    MAPPING,
    FAMILIES,
    IAMDataCollection,
    aliases,
    check_other_models,
    independent_index,
)
from audit_premise_vehicle_carbon import write_csv

ROOT = Path(__file__).resolve().parents[1]
WORK = Path("/private/tmp/premise-large-car-proxy-20261013")
OUT = ROOT / "results/premise_large_car_proxy_20261013"
SOURCE = ROOT.parent / "premise"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)
    filename = "transport_passenger_cars.yaml"
    old_mapping = yaml.safe_load(
        subprocess.check_output(
            ["git", "show", f"a83d23e:premise/iam_variables_mapping/{filename}"],
            cwd=SOURCE,
        )
    )
    mapping = yaml.safe_load((MAPPING / filename).read_text())
    assert {
        k: {f: v for f, v in entry.items() if f != "energy_intensity_fallback_aliases"}
        for k, entry in mapping.items()
    } == old_mapping
    assert sum("energy_intensity_fallback_aliases" in e for e in mapping.values()) == 5
    skill = Path("/Users/romain/.codex/skills/premise/SKILL.md").read_text()
    key = re.search(r"```text\s+([^\s]+)\s+```", skill).group(1).encode()
    installed = json.loads(
        (
            ROOT / "results/premise_vehicle_intensity_20261013/installation.json"
        ).read_text()
    )
    cases = [
        ("remind", r["filename"].removeprefix("remind_").removesuffix(".csv"), IAM)
        for r in installed["scenarios"]
    ]
    cases.append(
        (
            "remind-eu",
            "SSP2-NPi",
            Path("/private/tmp/premise-vehicle-intensity-20261013/remind-eu"),
        )
    )
    summaries, rows = [], []
    for model, pathway, folder in cases:
        with (
            (WORK / f"iam-{model}-{pathway}.log").open("w") as stream,
            contextlib.redirect_stdout(stream),
        ):
            iam = IAMDataCollection(model, pathway, 2050, folder, key)
        counts = dict(
            proxy_pairs=0, native_pairs_preserved=0, independent_proxy_year_checks=0
        )
        for family, (mapping_file, attr) in FAMILIES.items():
            service = aliases(mapping_file, model, "iam_aliases")
            energy = aliases(mapping_file, model, "energy_use_aliases")
            native = aliases(mapping_file, model, "energy_intensity_aliases")
            actual = getattr(iam, attr)
            before = iam.get_vehicle_efficiencies(
                iam.data, service, energy, native
            ).clip(None, 1.25)
            sources = actual.attrs["vehicle efficiency sources"]
            for technology, detail in sources.items():
                for region, kind in detail["by region"].items():
                    result = actual.sel(variables=technology, region=region)
                    old = before.sel(variables=technology, region=region)
                    assert result.sel(year=2020).item() == 1
                    if kind != "proxy intensity":
                        np.testing.assert_array_equal(result.values, old.values)
                        counts["native_pairs_preserved"] += 1
                        continue
                    assert family == "car" and technology.endswith(", large")
                    assert (
                        before.attrs["vehicle efficiency sources"][technology][
                            "by region"
                        ][region]
                        == "unavailable"
                    )
                    variable = detail["fallback intensity variable"]
                    assert variable == detail["intensity variable"].replace(
                        "|Large Car|", "|Large Car and SUV|"
                    )
                    raw = iam.data.sel(variables=variable, region=region)
                    expected = independent_index(raw.values.copy(), raw.year.values)
                    np.testing.assert_allclose(
                        result.values, expected, rtol=1e-10, atol=1e-12
                    )
                    counts["proxy_pairs"] += 1
                    counts["independent_proxy_year_checks"] += len(expected)
                    rows.append(
                        dict(
                            model=model,
                            pathway=pathway,
                            technology=technology,
                            region=region,
                            native_variable=detail["intensity variable"],
                            proxy_variable=variable,
                            baseline_factor=1,
                            energy_factor_2030=float(1 / result.sel(year=2030)),
                            energy_factor_2050=float(1 / result.sel(year=2050)),
                        )
                    )
        assert counts["proxy_pairs"] == (40 if model == "remind" else 100)
        summaries.append(
            dict(
                model=model,
                pathway=pathway,
                **counts,
                encrypted_iam_sha256=digest(folder / f"{model}_{pathway}.csv"),
            )
        )
    result = dict(
        cases=summaries,
        other_models=check_other_models(),
        fleet_energy_and_inventory_mappings_unchanged=True,
        baseline_mapping_commit="a83d23e",
        mapping_sha256=digest(MAPPING / filename),
        audit_script_sha256=digest(Path(__file__)),
        data_collection_sha256=digest(SOURCE / "premise/data_collection.py"),
    )
    write_csv(OUT / "proxy_factors.csv", rows)
    (OUT / "iam_verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(summaries, indent=2))
    print("Other-model/family calculations preserved:", len(result["other_models"]))


if __name__ == "__main__":
    main()
