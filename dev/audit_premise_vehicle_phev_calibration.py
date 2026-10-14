"""Bound the approved car PHEV calibration in templates and full scenarios.

Run in the Premise Python environment after both controlled builds. Proprietary
database pickles stay in the private workspace; outputs contain change audits.
"""

import csv
import json
import math
import pickle
from collections import Counter
from pathlib import Path

from audit_premise_vehicle_battery import warning_counts
from audit_premise_vehicle_carbon import coefficients, key, write_csv
from audit_premise_vehicle_workbooks import read_workbook
from premise_vehicle_provenance import digest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/premise_vehicle_phev_calibration_20261014"
WORK = Path("/private/tmp/premise-vehicle-phev-calibration-20261014")
OLD_OUT = ROOT / "results/premise_vehicle_deterioration_20261014"
OLD_WORK = Path("/private/tmp/premise-vehicle-deterioration-20261014")


def unpack(value):
    return json.loads(value) if isinstance(value, str) else value


def battery_routing():
    """Inspect explicit battery purchases in all four installed workbooks."""
    rows = []
    for family in ("pass_cars", "trucks", "buses", "two_wheelers"):
        path = (
            ROOT.parent
            / f"premise/premise/data/additional_inventories/lci-{family}.xlsx"
        )
        counts = Counter()
        for dataset in read_workbook(path)[0]:
            for exc in dataset["exchanges"]:
                if exc["type"] != "technosphere":
                    continue
                product = exc.get("reference product", exc.get("product"))
                if product == "electricity storage capacity":
                    assert exc["unit"] == "kilowatt hour"
                    counts[exc["name"], exc["unit"]] += 1
                elif exc["unit"] == "kilogram" and "battery" in exc["name"].lower():
                    assert family == "trucks" and exc["name"].startswith(
                        "lead acid battery, for lorry"
                    ), exc
                    counts[exc["name"], exc["unit"]] += 1
        rows.extend(
            dict(family=family, supplier=k[0], unit=k[1], exchanges=v)
            for k, v in sorted(counts.items())
        )
    write_csv(OUT / "battery_market_links.csv", rows)


def baseline_checks():
    before, after = [
        {
            r["name"]: r
            for r in csv.DictReader((w / "cars/vehicle_parameters.csv").open())
        }
        for w in (OLD_WORK, WORK)
    ]
    designs = json.loads((WORK / "cars/battery_sizing.json").read_text())
    old_designs = json.loads((OLD_WORK / "cars/battery_sizing.json").read_text())
    targets = json.loads(
        (
            ROOT.parent / "carculator/carculator/data/phev_2020_calibration.json"
        ).read_text()
    )["sizes"]
    assert before.keys() == after.keys()
    rows = []
    for name, row in after.items():
        if not row["powertrain"].startswith("PHEV-"):
            for field in row.keys() & before[name].keys():
                try:
                    a, b = float(before[name][field]), float(row[field])
                except ValueError:
                    assert before[name][field] == row[field]
                    continue
                assert math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-18), (name, field)
            continue
        spec, old_spec = designs[name], old_designs[name]
        target = targets[row["size"]]
        for field in ("capacity kWh", "pack mass kg"):
            assert math.isclose(spec[field], target[field], rel_tol=2e-6), (name, field)
        assert spec["density projection basis"] == "relative chemistry trend"
        assert float(row["battery lifetime replacements"]) == 0
        fuel = float(row["fuel_energy_MJ_per_vkm"])
        grid = float(row["electricity consumption"])
        energy = (
            fuel + grid * spec["charge efficiency"] * spec["charger efficiency"] * 3.6
        )
        assert math.isclose(energy, float(row["TtW energy"]) / 1000, rel_tol=2e-6), name
        record = dict(name=name, size=row["size"], powertrain=row["powertrain"])
        for field in (
            "capacity kWh",
            "pack mass kg",
            "electric range km",
            "electric share",
        ):
            record[f"before {field}"] = old_spec[field]
            record[f"after {field}"] = spec[field]
        for field in ("curb mass", "fuel_energy_MJ_per_vkm", "electricity consumption"):
            record[f"before {field}"] = float(before[name][field])
            record[f"after {field}"] = float(row[field])
        rows.append(record)
    assert len(rows) == 16
    write_csv(OUT / "baseline_changes.csv", rows)
    return dict(
        calibrated_services=len(rows),
        capacity_and_mass_match_approved_sources=True,
        fuel_plus_grid_equals_model_energy=True,
        all_other_vehicle_parameters_unchanged=True,
    )


def main():
    battery_routing()
    summary = {"baseline": baseline_checks()}
    changes, designs = [], []
    for year in (2020, 2050):
        old_meta = json.loads((OLD_OUT / f"build_{year}.json").read_text())
        new_meta = json.loads((OUT / f"build_{year}.json").read_text())
        for field in (
            "iam_files",
            "fuel_properties_sha256",
            "transport_mapping_sources",
        ):
            assert old_meta[field] == new_meta[field], field
        assert old_meta["workbooks"].keys() == new_meta["workbooks"].keys()
        assert {
            k for k, v in new_meta["workbooks"].items() if v != old_meta["workbooks"][k]
        } == {"lci-pass_cars.xlsx"}
        assert old_meta["python_sources"].keys() == new_meta["python_sources"].keys()
        assert {
            k
            for k, v in new_meta["python_sources"].items()
            if v != old_meta["python_sources"][k]
        } == {"premise/vehicle_battery.py"}
        databases = []
        for work, meta in ((OLD_WORK, old_meta), (WORK, new_meta)):
            path = work / str(year) / "database.pickle"
            assert digest(path) == meta["private_inventory_sha256"]
            with path.open("rb") as stream:
                databases.append({key(d): d for d in pickle.load(stream)})
        old, new = databases
        assert old.keys() == new.keys()
        changed, roles = set(), Counter()
        for ident, ds in new.items():
            spec = unpack(ds.get("vehicle inventory provenance", {}))
            selected = spec.get("family") == "car" and spec.get(
                "model powertrain", ""
            ).startswith("PHEV-")
            a, b = coefficients(old[ident]), coefficients(ds)
            assert a.keys() == b.keys(), ident
            for flow, before in a.items():
                after = b[flow]
                if math.isclose(before, after, rel_tol=1e-12, abs_tol=1e-18):
                    continue
                assert selected, (ident, flow)
                changed.add(ident)
                changes.append(
                    dict(
                        year=year,
                        name=ds["name"],
                        location=ds["location"],
                        role=spec["role"],
                        flow=str(flow),
                        before=before,
                        after=after,
                        percent=(after / before - 1) * 100 if before else None,
                    )
                )
            if not selected or spec.get("role") != "transport service":
                continue
            state = unpack(ds.get("premise vehicle battery sizing", {}))
            if not state:
                continue
            base = unpack(ds["vehicle battery sizing"])
            ratio = 1 if year == 2020 else 13 / 12  # NMC-622: 0.24 -> 0.26
            assert math.isclose(
                state["cell density kWh/kg"],
                base["cell density kWh/kg"] * ratio,
                rel_tol=2e-6,
            ), ident
            assert math.isclose(
                state["electric range km"], base["electric range km"], rel_tol=2e-6
            ), ident
            designs.append(
                dict(
                    year=year,
                    name=ds["name"],
                    location=ds["location"],
                    **{
                        k: state[k]
                        for k in (
                            "capacity kWh",
                            "pack mass kg",
                            "cell density kWh/kg",
                            "electric range km",
                        )
                    },
                )
            )
        for ident in changed:
            roles[unpack(new[ident]["vehicle inventory provenance"])["role"]] += 1
        old_warnings = warning_counts(OLD_OUT / f"validation_{year}.json")
        new_warnings = warning_counts(OUT / f"validation_{year}.json")
        assert new_meta["validation_errors"] == 0
        assert old_warnings == new_warnings
        summary[year] = dict(
            activities=len(new),
            exchanges=new_meta["exchanges"],
            changed_activities=len(changed),
            changed_roles=dict(roles),
            validation_errors=0,
            validation_warnings=new_meta["validation_warnings"],
            warning_identities_unchanged=True,
            all_other_coefficients_unchanged=True,
            relative_density_trend_and_range_preserved=True,
            scenario_phev_designs_checked=sum(r["year"] == year for r in designs),
        )
    write_csv(OUT / "scenario_changes.csv", changes)
    write_csv(OUT / "scenario_phev_designs.csv", designs)
    (OUT / "change_scope_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
