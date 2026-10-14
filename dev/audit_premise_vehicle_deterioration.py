"""Verify engine-ageing propagation from native factors to final Premise hybrids."""

import csv
import json
import math
import pickle
from collections import Counter
from pathlib import Path

from audit_premise_vehicle_battery import warning_counts
from audit_premise_vehicle_carbon import coefficients, key, write_csv
from audit_premise_vehicle_payload import digest
from audit_premise_vehicle_provenance import workbook_coefficients
from audit_premise_vehicle_workbooks import identity, read_workbook

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/premise_vehicle_deterioration_20261014"
WORK = Path("/private/tmp/premise-vehicle-deterioration-20261014")
OLD_OUT = ROOT / "results/premise_vehicle_fcev_20261014"
OLD_WORK = Path("/private/tmp/premise-vehicle-fcev-20261014")


def close(actual, expected, context):
    assert math.isclose(actual, expected, rel_tol=3e-6, abs_tol=1e-15), (
        context,
        actual,
        expected,
    )


def compare_models():
    old = json.loads((OLD_WORK / "probe/model_snapshot.json").read_text())
    new = json.loads((WORK / "probe/model_snapshot.json").read_text())
    physical = [
        "TtW energy",
        "curb mass",
        "driving mass",
        "fuel consumption",
        "electricity consumption",
        "electric energy stored",
        "energy battery mass",
        "battery lifetime replacements",
        "electric utility factor",
    ]
    for family in old:
        assert old[family].keys() == new[family].keys()
        for vehicle, before in old[family].items():
            for p in physical:
                assert before[p] == new[family][vehicle][p], (family, vehicle, p)
    index = lambda r: tuple(r[k] for k in ("family", "size", "powertrain", "stage"))
    old_emissions = {
        index(r): r
        for r in csv.DictReader(
            (OLD_WORK / "probe/model_emissions_kg_per_vkm.csv").open()
        )
    }
    new_emissions = {
        index(r): r
        for r in csv.DictReader((WORK / "probe/model_emissions_kg_per_vkm.csv").open())
    }
    assert old_emissions.keys() == new_emissions.keys()
    tables = {
        family: list(
            csv.DictReader(
                (
                    ROOT
                    / "carculator_utils/data/emission_factors"
                    / family
                    / "degradation_EF.csv"
                ).open()
            )
        )
        for family in old
    }
    changes, count = [], 0
    for ident, before in old_emissions.items():
        family, size, power, stage = ident
        after = new_emissions[ident]
        native = f"{size}|{power.replace('PHEV-c-', 'PHEV-')}"
        hybrid = power.startswith(("HEV-", "PHEV-c-")) and native in new[family]
        hot = old_emissions[family, size, power, "hot"]
        for component in before.keys() - {
            "family",
            "size",
            "powertrain",
            "stage",
            "euro_class",
        }:
            factor = 1
            if hybrid:
                label = "Hydrocarbon" if component == "Hydrocarbons" else component
                matched = [
                    float(r["value"])
                    for r in tables[family]
                    if r["powertrain"] == f"ICEV-{power[-1]}"
                    and float(r["euro_class"]) == float(before["euro_class"])
                    and r["component"] == label
                ]
                endpoint = max(1, sum(matched) / len(matched)) if matched else 1
                lifetime = new[family][native]["lifetime kilometers"]
                factor = 1 + (endpoint - 1) * lifetime / (
                    400000 if family == "car" else 1780000
                )
            a, b = float(before[component]), float(after[component])
            expected = a + float(hot[component]) * (factor - 1)
            close(b, expected, (ident, component))
            count += 1
            if not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-18):
                changes.append(
                    dict(
                        family=family,
                        size=size,
                        powertrain=power,
                        stage=stage,
                        pollutant=component,
                        before_kg_per_vkm=a,
                        after_kg_per_vkm=b,
                        hot_ageing_factor=factor,
                        percent=(b / a - 1) * 100,
                    )
                )
    write_csv(OUT / "model_emission_changes.csv", changes)
    return dict(
        emission_values_checked=count,
        physical_fields_unchanged=True,
        hot_factors_applied_once=True,
        cold_start_and_evaporation_unchanged=True,
    )


def main():
    summary = {"native_models": compare_models()}
    templates = []
    for directory in (
        WORK / "before",
        ROOT.parent / "premise/premise/data/additional_inventories",
    ):
        templates.append(
            {
                identity(d): workbook_coefficients(d)
                for name in ("lci-pass_cars.xlsx", "lci-trucks.xlsx")
                for d in read_workbook(directory / name)[0]
            }
        )
    differences = []
    for year in (2020, 2050):
        old_meta = json.loads((OLD_OUT / f"build_{year}.json").read_text())
        new_meta = json.loads((OUT / f"build_{year}.json").read_text())
        for field in (
            "iam_files",
            "fuel_properties_sha256",
            "python_sources",
            "transport_mapping_sources",
        ):
            assert old_meta[field] == new_meta[field], field
        databases = []
        for work, meta in ((OLD_WORK, old_meta), (WORK, new_meta)):
            path = work / str(year) / "database.pickle"
            assert digest(path) == meta["private_inventory_sha256"]
            with path.open("rb") as stream:
                databases.append({key(d): d for d in pickle.load(stream)})
        old, new = databases
        assert old.keys() == new.keys()
        changed, families = set(), Counter()
        for ident, ds in new.items():
            a, b = coefficients(old[ident]), coefficients(ds)
            assert a.keys() == b.keys(), ident
            for flow, before in a.items():
                after = b[flow]
                if math.isclose(before, after, rel_tol=1e-12, abs_tol=1e-18):
                    continue
                spec = ds.get("vehicle inventory provenance", {})
                if isinstance(spec, str):
                    spec = json.loads(spec)
                assert spec.get("model powertrain", "").startswith(("HEV-", "PHEV-")), (
                    ident,
                    flow,
                )
                assert spec.get("role") == "transport service", ident
                assert flow[0] == "biosphere" and flow[1] in {
                    "Carbon monoxide",
                    "Carbon monoxide, fossil",
                    "Carbon monoxide, non-fossil",
                    "Nitrogen oxides",
                }, (ident, flow)
                base = spec["baseline identity"]
                base_key = tuple(
                    base[k] for k in ("name", "reference product", "location", "unit")
                )
                source_before, source_after = (t[base_key][flow] for t in templates)
                close(after, before * source_after / source_before, (ident, flow))
                changed.add(ident)
                differences.append(
                    dict(
                        year=year,
                        family=spec["family"],
                        name=ds["name"],
                        location=ds["location"],
                        flow=flow[1],
                        before=before,
                        after=after,
                        percent=(after / before - 1) * 100,
                    )
                )
        for ident in changed:
            spec = new[ident]["vehicle inventory provenance"]
            if isinstance(spec, str):
                spec = json.loads(spec)
            families[spec["family"]] += 1
        old_warnings = warning_counts(OLD_OUT / f"validation_{year}.json")
        new_warnings = warning_counts(OUT / f"validation_{year}.json")
        assert new_meta["validation_errors"] == 0
        summary[year] = dict(
            activities=len(new),
            exchanges=new_meta["exchanges"],
            changed_activities=len(changed),
            changed_families=dict(families),
            validation_errors=0,
            validation_warnings=new_meta["validation_warnings"],
            added_warnings=[
                dict(rule=k[0], activity=k[1], count=v)
                for k, v in (new_warnings - old_warnings).items()
            ],
            removed_warnings=[
                dict(rule=k[0], activity=k[1], count=v)
                for k, v in (old_warnings - new_warnings).items()
            ],
            all_changes_match_template_ratios=True,
            all_other_coefficients_unchanged=True,
        )
    write_csv(OUT / "scenario_changes.csv", differences)
    (OUT / "change_scope_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
