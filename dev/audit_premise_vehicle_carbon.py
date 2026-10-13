"""Independent final-link CO2 audit and change-scope check for cars/trucks."""

import csv
import hashlib
import json
import math
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "premise"
sys.path.insert(0, str(SOURCE))
from premise.fuels.carbon import VEHICLE_CO2_KEY, update_vehicle_fuel_co2

OUT = ROOT / "results/premise_vehicle_carbon_20261013"
WORK = Path("/private/tmp/premise-vehicle-carbon-20261013")
BEFORE = Path("/private/tmp/premise-fuel-basis-20261013")
PROPERTIES = "premise fuel properties"
TRANSFER = "premise fuel CO2 reclassification"


def key(ds):
    return (
        ds["name"],
        ds.get("reference product", ds.get("product")),
        ds["location"],
        ds["unit"],
    )


def co2(ds):
    return tuple(
        sum(
            e["amount"]
            for e in ds["exchanges"]
            if e["type"] == "biosphere"
            and e["name"] == name
            and e.get("categories", [None])[0] == "air"
            and e["amount"] >= 0
        )
        for name in ("Carbon dioxide, fossil", "Carbon dioxide, non-fossil")
    )


def coefficients(ds):
    result = defaultdict(float)
    for e in ds["exchanges"]:
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


def write_csv(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)


def issues(path):
    report = json.loads(path.read_text())
    return [
        i
        for phase in report["phase_results"]
        for rule in phase["rule_results"]
        for i in rule["issues"]
        if not i["suppressed"]
    ]


def main():
    rows, changes, ledger_rows, summaries = [], [], [], {}
    for year in (2020, 2050):
        with (WORK / str(year) / "database.pickle").open("rb") as stream:
            database = pickle.load(stream)
        with (BEFORE / str(year) / "database.pickle").open("rb") as stream:
            old = pickle.load(stream)
        index, baseline = {key(d): d for d in database}, {key(d): d for d in old}
        assert index.keys() == baseline.keys()
        changed_vehicles = set()
        nonvehicle_changes = []
        for identity, ds in index.items():
            is_vehicle = ds["name"].startswith(
                ("transport, passenger car,", "transport, freight, lorry,")
            )
            a, b = coefficients(baseline[identity]), coefficients(ds)
            for exchange in a.keys() | b.keys():
                if math.isclose(a[exchange], b[exchange], rel_tol=1e-11, abs_tol=1e-18):
                    continue
                if (
                    is_vehicle
                    and exchange[0] == "biosphere"
                    and exchange[1]
                    in ("Carbon dioxide, fossil", "Carbon dioxide, non-fossil")
                    and exchange[5][0] == "air"
                ):
                    changed_vehicles.add(identity)
                    changes.append(
                        dict(
                            year=year,
                            vehicle=ds["name"],
                            region=ds["location"],
                            flow=exchange[1],
                            categories="::".join(exchange[5]),
                            old=a[exchange],
                            new=b[exchange],
                        )
                    )
                else:
                    nonvehicle_changes.append(
                        (identity, exchange, a[exchange], b[exchange])
                    )
            if not is_vehicle:
                continue
            if VEHICLE_CO2_KEY not in ds:
                # Forwarders and noncombustion vehicles have no direct fuel CO2.
                continue
            status = ds[VEHICLE_CO2_KEY]
            assert status["status"] == "resolved", (identity, status)
            expected_fossil = expected_bio = 0.0
            fuel_count = 0
            for e in ds["exchanges"]:
                if e["type"] != "technosphere":
                    continue
                stem = (
                    e["name"]
                    .removeprefix("market for ")
                    .removeprefix("market group for ")
                )
                if not stem.startswith(
                    (
                        "petrol",
                        "gasoline",
                        "diesel",
                        "natural gas",
                        "liquefied petroleum gas",
                    )
                ):
                    continue
                provider = index[key(e)]
                p = provider.get(PROPERTIES)
                if p is None:
                    assert stem == "liquefied petroleum gas" and e["unit"] == "kilogram"
                    fossil, bio = 45.5 * 0.0631, 0
                else:
                    assert (
                        p["reference unit"] == e["unit"]
                        and p["unresolved CO2 kg per unit"] == 0
                    )
                    fossil, bio = (
                        p["fossil CO2 kg per unit"],
                        p["non-fossil CO2 kg per unit"],
                    )
                expected_fossil += e["amount"] * fossil
                expected_bio += e["amount"] * bio
                fuel_count += 1
            assert fuel_count > 0
            actual, prior = co2(ds), co2(baseline[identity])
            expected = expected_fossil, expected_bio
            assert all(
                math.isclose(x, y, rel_tol=1e-10, abs_tol=1e-13)
                for x, y in zip(actual, expected)
            ), (identity, actual, expected)
            total, previous_total = sum(actual), sum(prior)
            transferred = sum(
                sum(e.get(TRANSFER, {}).values())
                for e in ds["exchanges"]
                if e["name"] == "Carbon dioxide, fossil"
            )
            assert math.isclose(transferred, expected_bio, rel_tol=1e-10, abs_tol=1e-13)
            rows.append(
                dict(
                    year=year,
                    vehicle=ds["name"],
                    region=ds["location"],
                    unit=ds["unit"],
                    old_fossil_CO2=prior[0],
                    old_non_fossil_CO2=prior[1],
                    new_fossil_CO2=actual[0],
                    new_non_fossil_CO2=actual[1],
                    expected_fossil_CO2=expected[0],
                    expected_non_fossil_CO2=expected[1],
                    old_non_fossil_share=(
                        prior[1] / previous_total if previous_total else 0
                    ),
                    new_non_fossil_share=actual[1] / total if total else 0,
                    total_CO2_change_percent=(
                        100 * (total / previous_total - 1) if previous_total else None
                    ),
                    old_split_mismatch=not all(
                        math.isclose(x, y, rel_tol=1e-8, abs_tol=1e-12)
                        for x, y in zip(prior, expected)
                    ),
                    updated_transfer_kg=transferred,
                )
            )
            old_transfers = sum(
                sum(e.get(TRANSFER, {}).values())
                for e in baseline[identity]["exchanges"]
                if e["name"] == "Carbon dioxide, fossil"
            )
            ledger_rows.append(
                dict(
                    year=year,
                    vehicle=ds["name"],
                    region=ds["location"],
                    old_recorded_transfer_kg=old_transfers,
                    old_non_fossil_CO2_kg=prior[1],
                    corrected_transfer_kg=transferred,
                )
            )
        assert not nonvehicle_changes, nonvehicle_changes[:5]
        # Exact repeatability of the dedicated CO2 correction on the complete
        # materialized inventory, not just a toy dataset.
        before_repeat = {
            key(d): hashlib.sha256(pickle.dumps(d)).hexdigest()
            for d in database
            if VEHICLE_CO2_KEY in d
        }
        update_vehicle_fuel_co2(database, "3.12")
        after_repeat = {
            key(d): hashlib.sha256(pickle.dumps(d)).hexdigest()
            for d in database
            if VEHICLE_CO2_KEY in d
        }
        assert before_repeat == after_repeat
        selected = [r for r in rows if r["year"] == year]
        builds = json.loads((OUT / f"build_{year}.json").read_text())
        old_warnings = Counter(
            (i["rule_id"], tuple(i["activity_key"] or ()))
            for i in issues(
                ROOT / f"results/premise_fuel_basis_20261013/validation_{year}.json"
            )
            if i["severity"] == "warning"
        )
        new_warnings = Counter(
            (i["rule_id"], tuple(i["activity_key"] or ()))
            for i in issues(OUT / f"validation_{year}.json")
            if i["severity"] == "warning"
        )
        assert old_warnings == new_warnings
        assert builds["validation_errors"] == 0
        summaries[year] = dict(
            checked_vehicles=len(selected),
            regions=sorted({r["region"] for r in selected}),
            previous_mismatches=sum(r["old_split_mismatch"] for r in selected),
            remaining_mismatches=0,
            changed_vehicles=len(changed_vehicles),
            changes_outside_vehicle_CO2=0,
            idempotent_vehicles=len(before_repeat),
            unresolved=0,
            validation_errors=builds["validation_errors"],
            validation_warnings=builds["validation_warnings"],
            warning_identities_unchanged=True,
        )
    builds = [json.loads((OUT / f"build_{y}.json").read_text()) for y in (2020, 2050)]
    for field in ("python_sources", "workbooks", "fuel_properties_sha256"):
        assert builds[0][field] == builds[1][field]
    write_csv(OUT / "vehicle_carbon_comparison.csv", rows)
    write_csv(OUT / "changed_CO2_exchanges.csv", changes)
    write_csv(OUT / "transfer_bookkeeping.csv", ledger_rows)
    (OUT / "verification_summary.json").write_text(
        json.dumps(summaries, indent=2) + "\n"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
