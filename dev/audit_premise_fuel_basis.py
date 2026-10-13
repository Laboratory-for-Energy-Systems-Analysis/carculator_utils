"""Audit reference-energy closure, carbon provenance and isolated CNG changes."""

import csv
import hashlib
import json
import math
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "premise"))
from premise.fuels.properties import PROPERTIES_KEY, activity_key
from premise.utils import get_fuel_properties

OUT = ROOT / "results/premise_fuel_basis_20261013"
WORK = Path("/private/tmp/premise-fuel-basis-20261013")
BASELINE = Path("/private/tmp/premise-cng-routing-20261013")


def write_csv(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    fuel_specs = get_fuel_properties()
    rows, cng_rows, origins, vehicle_rows, warnings = [], [], [], [], []
    summary = {}
    for year in (2020, 2050):
        with (WORK / str(year) / "database.pickle").open("rb") as stream:
            new = pickle.load(stream)
        with (BASELINE / str(year) / "database.pickle").open("rb") as stream:
            old = pickle.load(stream)
        index = {activity_key(ds): ds for ds in new}
        baseline = {activity_key(ds): ds for ds in old}
        assert index.keys() == baseline.keys(), "Activity identities changed"
        annotated = {key: ds for key, ds in index.items() if PROPERTIES_KEY in ds}
        assert len(annotated) > 156
        unresolved = []
        for key, ds in annotated.items():
            properties = ds[PROPERTIES_KEY]
            # Read current exchanges independently. Supplier heating values come
            # from the packaged specifications, or a provider's declared output.
            factors = {}
            for component in properties["components"]:
                supplier_key = activity_key(component)
                if "technology" in component:
                    energy = float(fuel_specs[component["technology"]]["lhv"]["value"])
                    origins.append(
                        dict(
                            year=year,
                            market=ds["name"],
                            region=ds["location"],
                            supplier=component["name"],
                            technology=component["technology"],
                            non_fossil_share=component["non_fossil_share"],
                            source=component["carbon source"],
                        )
                    )
                else:
                    energy = index[supplier_key][PROPERTIES_KEY]["energy MJ per unit"]
                if supplier_key in factors:
                    assert factors[supplier_key] == energy
                factors[supplier_key] = energy
            supplied = sum(
                abs(e["amount"]) * factors[activity_key(e)]
                for e in ds["exchanges"]
                if e["type"] == "technosphere" and activity_key(e) in factors
            )
            target = properties.get(
                "upstream fuel energy MJ per unit",
                properties["reference energy MJ per unit"],
            )
            assert math.isclose(supplied, target, rel_tol=1e-12), (
                key,
                supplied,
                target,
            )
            if properties["unresolved CO2 kg per unit"] > 0:
                unresolved.append(key)
            old_energy = sum(
                abs(e["amount"]) * factors[activity_key(e)]
                for e in baseline[key]["exchanges"]
                if e["type"] == "technosphere" and activity_key(e) in factors
            )
            rows.append(
                dict(
                    year=year,
                    name=ds["name"],
                    region=ds["location"],
                    unit=ds["unit"],
                    reference_energy_MJ=target,
                    old_supplier_energy_MJ=old_energy,
                    old_energy_error_percent=100 * (old_energy / target - 1),
                    new_supplier_energy_MJ=supplied,
                    new_energy_error_percent=100 * (supplied / target - 1),
                    fossil_CO2_kg=properties["fossil CO2 kg per unit"],
                    non_fossil_CO2_kg=properties["non-fossil CO2 kg per unit"],
                    unresolved_CO2_kg=properties["unresolved CO2 kg per unit"],
                    boundary=(
                        "compression inputs"
                        if "upstream fuel energy MJ per unit" in properties
                        else "market reference output"
                    ),
                )
            )
            if "upstream fuel energy MJ per unit" in properties:
                before_inputs = [
                    e for e in baseline[key]["exchanges"] if e["type"] != "production"
                ]
                after_inputs = [e for e in ds["exchanges"] if e["type"] != "production"]

                def coefficients(exchanges):
                    result = defaultdict(float)
                    for e in exchanges:
                        result[
                            (
                                e["type"],
                                e["name"],
                                e.get("product"),
                                e.get("location"),
                                e["unit"],
                                tuple(e.get("categories", ())),
                            )
                        ] += e["amount"]
                    return result

                a, b = coefficients(before_inputs), coefficients(after_inputs)
                assert a.keys() == b.keys(), key
                assert all(
                    math.isclose(a[k], b[k], rel_tol=1e-12, abs_tol=1e-20) for k in a
                ), key
                assert properties["energy MJ per unit"] == 46.5
                cng_rows.append(
                    dict(
                        year=year,
                        region=ds["location"],
                        delivered_MJ_per_kg=46.5,
                        upstream_gas_MJ_per_kg=target,
                        difference_MJ_per_kg=target - 46.5,
                        unchanged_compression_exchanges=True,
                    )
                )
        assert not unresolved, unresolved
        for key, ds in index.items():
            if not ds["name"].startswith(
                (
                    "transport, passenger car, compressed gas,",
                    "transport, freight, lorry, compressed gas,",
                )
            ):
                continue
            for e in ds["exchanges"]:
                if (
                    e["type"] != "technosphere"
                    or e["name"]
                    != "market for natural gas, medium pressure, vehicle grade"
                ):
                    continue
                before = [
                    x
                    for x in baseline[key]["exchanges"]
                    if x["type"] == "technosphere" and x["name"] == e["name"]
                ]
                assert len(before) == 1
                assert math.isclose(
                    before[0]["amount"] * 47.5, e["amount"] * 46.5, rel_tol=1e-10
                )
                provider = index[activity_key(e)]
                assert provider[PROPERTIES_KEY]["energy MJ per unit"] == 46.5
                vehicle_rows.append(
                    dict(
                        year=year,
                        name=ds["name"],
                        region=ds["location"],
                        unit=ds["unit"],
                        old_CNG_kg=before[0]["amount"],
                        new_CNG_kg=e["amount"],
                        energy_MJ=e["amount"] * 46.5,
                    )
                )
        meta = json.loads((OUT / f"build_{year}.json").read_text())
        assert meta["validation_errors"] == 0
        summary[year] = dict(
            activities=len(new),
            annotated_suppliers=len(annotated),
            carbon_origins_unresolved=len(unresolved),
            validation_errors=meta["validation_errors"],
            validation_warnings=meta["validation_warnings"],
            cng_compression_regions=sum(r["year"] == year for r in cng_rows),
            cng_vehicle_energy_checks=sum(r["year"] == year for r in vehicle_rows),
        )
        # Compare warning reasons with the immediately preceding CNG-routing build.
        current = json.loads((OUT / f"validation_{year}.json").read_text())
        previous = json.loads(
            (
                ROOT / f"results/premise_cng_routing_20261013/validation_{year}.json"
            ).read_text()
        )
        warning_identities = {}
        for label, report in (("old", previous), ("new", current)):
            issues = [
                i
                for phase in report["phase_results"]
                for rule in phase["rule_results"]
                for i in rule["issues"]
                if i["severity"] == "warning" and not i.get("suppressed", False)
            ]
            warning_identities[label] = Counter(
                (i["rule_id"], tuple(i["activity_key"] or ())) for i in issues
            )
            counts = Counter(
                (w.get("rule_id", ""), w.get("message", "")) for w in issues
            )
            warnings.extend(
                dict(year=year, version=label, reason=k[0], message=k[1], count=v)
                for k, v in counts.items()
            )
        assert warning_identities["old"] == warning_identities["new"]
        summary[year]["warning_identities_unchanged"] = True
    first, second = [
        json.loads((OUT / f"build_{year}.json").read_text()) for year in (2020, 2050)
    ]
    for field in ("python_sources", "workbooks", "fuel_properties_sha256"):
        assert first[field] == second[field], field
    write_csv(OUT / "market_energy_and_carbon.csv", rows)
    write_csv(OUT / "cng_compression_boundaries.csv", cng_rows)
    write_csv(OUT / "carbon_origin_provenance.csv", origins)
    write_csv(OUT / "cng_vehicle_energy.csv", vehicle_rows)
    write_csv(OUT / "warning_counts.csv", warnings)
    (OUT / "verification_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
