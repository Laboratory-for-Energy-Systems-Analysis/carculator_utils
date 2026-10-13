"""Verify restored REMIND intensity factors and other IAM calculation paths."""

import contextlib
import hashlib
import io
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import yaml
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "premise"))
from premise.data_collection import IAMDataCollection

WORK = Path("/private/tmp/premise-vehicle-intensity-20261013")
OUT = ROOT / "carculator_utils/results/premise_vehicle_intensity_20261013"
ORIGINALS = Path("/Users/romain/Library/CloudStorage/Dropbox/Notebooks/IAM-ecoinvent")
IAM = ROOT / "premise/premise/data/iam_output_files"
MAPPING = ROOT / "premise/premise/iam_variables_mapping"
FAMILIES = {
    "car": ("transport_passenger_cars.yaml", "passenger_car_efficiencies"),
    "truck": ("transport_road_freight.yaml", "road_freight_efficiencies"),
}


def aliases(filename, model, field):
    return {
        technology: spec[field][model]
        for technology, spec in yaml.safe_load((MAPPING / filename).read_text()).items()
        if model in spec.get(field, {})
    }


def independent_index(values, years):
    """Reproduce the stated policy with NumPy's cumulative maximum."""
    reference = values[list(years).index(2020)]
    filled = (
        pd.Series(np.where(np.isfinite(values) & (values > 0), values, np.nan))
        .bfill()
        .ffill()
        .to_numpy()
    )
    relative = reference / filled
    relative[years > 2020] = np.maximum(relative[years > 2020], 1)
    relative[years < 2020] = np.minimum(relative[years < 2020], 1)
    return np.clip(np.maximum.accumulate(relative), 0.5, 1.25)


def check_remind(key):
    changes, summary = [], []
    installation = json.loads((OUT / "installation.json").read_text())
    cipher = Fernet(key)
    cases = []
    for record in installation["scenarios"]:
        path = IAM / record["filename"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["after_sha256"]
        previous = cipher.decrypt((WORK / "before" / path.name).read_bytes())
        current = cipher.decrypt(path.read_bytes())
        assert current.startswith(previous)
        cases.append(("remind", path.stem.removeprefix("remind_"), IAM))
    # The matching original EU21 scenario is an isolated encrypted reader case.
    # It is not installed over any existing scenario or published.
    european = WORK / "remind-eu"
    european.mkdir(exist_ok=True)
    path = european / "remind-eu_SSP2-NPi.csv"
    if not path.exists():
        original = ORIGINALS / "remind 3.5.2/REMIND_generic_SSP2-EU21-NPi2025.mif"
        path.write_bytes(cipher.encrypt(original.read_bytes()))
    cases.append(("remind-eu", "SSP2-NPi", european))

    with (WORK / "iam_collection.log").open("w") as log:
        for model, pathway, folder in cases:
            with contextlib.redirect_stdout(log):
                iam = IAMDataCollection(model, pathway, 2050, folder, key)
            for family, (mapping, attribute) in FAMILIES.items():
                actual = getattr(iam, attribute)
                service = aliases(mapping, model, "iam_aliases")
                energy = aliases(mapping, model, "energy_use_aliases")
                legacy = iam.get_iam_efficiencies(
                    iam.data, production_labels=service, energy_labels=energy
                ).clip(None, 1.25)
                sources = actual.attrs["vehicle efficiency sources"]
                count_direct = count_missing = checks = 0
                for technology, details in sources.items():
                    variable = details["intensity variable"]
                    for region, kind in details["by region"].items():
                        result = actual.sel(variables=technology, region=region)
                        assert np.isfinite(result).all() and (result > 0).all()
                        assert result.sel(year=2020).item() == 1
                        if kind == "direct intensity":
                            raw = iam.data.sel(variables=variable, region=region)
                            expected = independent_index(
                                raw.values.copy(), raw.year.values
                            )
                            np.testing.assert_allclose(
                                result.values, expected, rtol=1e-10, atol=1e-12
                            )
                            count_direct += 1
                            checks += len(expected)
                        elif kind == "unavailable":
                            np.testing.assert_array_equal(result, 1)
                            count_missing += 1
                        before = float(
                            1
                            / legacy.sel(region=region, variables=technology, year=2050)
                        )
                        after = float(1 / result.sel(year=2050))
                        changes.append(
                            {
                                "model": model,
                                "pathway": pathway,
                                "family": family,
                                "technology": technology,
                                "region": region,
                                "source": kind,
                                "old_2050_energy_factor": before,
                                "new_2050_energy_factor": after,
                            }
                        )
                summary.append(
                    {
                        "model": model,
                        "pathway": pathway,
                        "family": family,
                        "regions": len(iam.regions),
                        "direct_region_technology_pairs": count_direct,
                        "unavailable_pairs": count_missing,
                        "independent_year_checks": checks,
                        "all_2020_indices_equal_one": True,
                    }
                )
    pd.DataFrame(changes).to_csv(OUT / "iam_factor_changes.csv", index=False)
    return summary


def check_other_models():
    files = {
        "image": "image 3.4/processed/IMAGE 3.4_SSP2_M_CP_filtered.csv",
        "tiam-ucl": "TIAM-UCL/tiam-ucl_SSP2-RCP26.xlsx",
        "message": "message/message_SSP2-M.csv",
        "gcam": "GCAM/new files/gcam_GCAM_SSP2_RCP45.xlsx",
        "witch": "WITCH/witch_SSP2-Base.csv",
    }
    records = []
    for model, relative in files.items():
        path = ORIGINALS / relative
        if path.suffix == ".xlsx":
            raw = pd.read_excel(path)
        else:
            with path.open() as stream:
                header = stream.readline(1000)
            assert not header.startswith("gAAAAA")
            raw = pd.read_csv(
                path, sep=";" if header.count(";") > header.count(",") else ","
            )
        raw.columns = [str(column).lower().strip() for column in raw]
        years = [
            column for column in raw if column.isdigit() and 2005 <= int(column) <= 2100
        ]
        for family, (filename, _) in FAMILIES.items():
            service = aliases(filename, model, "iam_aliases")
            energy = aliases(filename, model, "energy_use_aliases")
            direct = aliases(filename, model, "energy_intensity_aliases")
            assert not direct
            wanted = {
                value
                for spec in [*service.values(), *energy.values()]
                for value in (spec if isinstance(spec, list) else [spec])
            }
            subset = raw.loc[raw.variable.isin(wanted)]
            if subset.empty:
                subset = raw.iloc[:1]
            melted = subset.melt(
                id_vars=["region", "variable", "unit"],
                value_vars=years,
                var_name="year",
                value_name="value",
            )
            melted.year = melted.year.astype(int)
            data = (
                melted.groupby(["region", "variable", "year"])
                .value.mean()
                .to_xarray()
                .rename(variable="variables")
                .transpose("region", "variables", "year")
            )
            iam = object.__new__(IAMDataCollection)
            iam.year, iam.min_year, iam.filepath_iam_files = (
                2050,
                int(data.year.min()),
                path,
            )
            legacy = iam.get_iam_efficiencies(
                data, production_labels=service, energy_labels=energy
            )
            current = iam.get_vehicle_efficiencies(data, service, energy, direct)
            if legacy is None:
                assert current is None
            else:
                xr.testing.assert_identical(current, legacy)
            records.append(
                {
                    "model": model,
                    "family": family,
                    "source": relative,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "service_mappings": len(service),
                    "requested_variables_present": len(wanted & set(raw.variable)),
                    "requested_variables_missing": len(wanted - set(raw.variable)),
                    "legacy_result_preserved": True,
                    "service_units": sorted(
                        set(
                            raw.loc[
                                raw.variable.isin(
                                    [
                                        v
                                        for s in service.values()
                                        for v in (s if isinstance(s, list) else [s])
                                    ]
                                ),
                                "unit",
                            ]
                        )
                    ),
                }
            )
    return records


def main():
    instructions = Path("/Users/romain/.codex/skills/premise/SKILL.md").read_text()
    key = re.search(r"```text\s+([^\s]+)\s+```", instructions).group(1).encode()
    result = {
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "remind": check_remind(key),
        "other_models": check_other_models(),
    }
    (OUT / "iam_verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        "Verified",
        sum(r["independent_year_checks"] for r in result["remind"]),
        "direct-intensity year cells and",
        len(result["other_models"]),
        "other-model/family cases",
    )


if __name__ == "__main__":
    main()
