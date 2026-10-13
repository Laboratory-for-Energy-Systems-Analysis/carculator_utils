"""Verify HEV storage, unchanged control vehicles, fuel CO2 and hydrogen in full scenarios."""

import csv
import hashlib
import json
import math
import pickle
from collections import Counter
from pathlib import Path

from audit_premise_vehicle_carbon import (
    PROPERTIES,
    VEHICLE_CO2_KEY,
    co2,
    coefficients,
    issues,
    key,
    write_csv,
)
from audit_premise_vehicle_hydrogen import COMPRESSION_KEY, EXPECTED, quantity

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/premise_truck_hev_storage_20261013"
WORK = Path("/private/tmp/premise-truck-hev-20261013")
BEFORE = Path("/private/tmp/premise-vehicle-replacements-20261013")


def main():
    rows, summaries = [], {}
    with (WORK / "trucks/vehicle_parameters.csv").open() as stream:
        expected_capacities = {
            row["size"]: float(row["battery_capacity_with_replacements_kWh"])
            for row in csv.DictReader(stream)
            if row["powertrain"] == "HEV-d"
        }
    for year in (2020, 2050):
        with (WORK / str(year) / "database.pickle").open("rb") as stream:
            index = {key(d): d for d in pickle.load(stream)}
        with (BEFORE / str(year) / "database.pickle").open("rb") as stream:
            previous = {key(d): d for d in pickle.load(stream)}
        assert index.keys() == previous.keys()
        changed, carbon, hydrogen, roundoff = 0, 0, 0, 0
        changed_activities = set()
        battery_purchases = 0
        max_rounding_absolute = max_rounding_relative = 0.0
        for identity_, dataset in index.items():
            a, b = coefficients(previous[identity_]), coefficients(dataset)
            for exchange in a.keys() | b.keys():
                a.setdefault(exchange, 0.0)
                b.setdefault(exchange, 0.0)
                if a[exchange] == b[exchange]:
                    continue
                if math.isclose(a[exchange], b[exchange], rel_tol=1e-6, abs_tol=1e-12):
                    roundoff += 1
                    difference = abs(a[exchange] - b[exchange])
                    max_rounding_absolute = max(max_rounding_absolute, difference)
                    if a[exchange] != 0:
                        max_rounding_relative = max(
                            max_rounding_relative, difference / abs(a[exchange])
                        )
                    continue
                assert identity_[0].startswith(
                    (
                        "lorry production, diesel hybrid,",
                        "transport, freight, lorry, diesel hybrid,",
                        "transport, freight, lorry, gasoline hybrid,",
                    )
                ), (identity_, exchange)
                changed += 1
                changed_activities.add(identity_)
                if exchange[1] == "market for battery capacity (MIX scenario)":
                    assert a[exchange] == 0 and b[exchange] > 0
                    size = identity_[0].split(", ")[-1].replace(" metric ton", "t")
                    assert math.isclose(
                        b[exchange], expected_capacities[size], rel_tol=1e-6
                    )
                    battery_purchases += 1
                rows.append(
                    dict(
                        year=year,
                        vehicle=identity_[0],
                        location=identity_[2],
                        exchange=exchange[1],
                        before=a[exchange],
                        after=b[exchange],
                    )
                )
            if VEHICLE_CO2_KEY in dataset:
                assert dataset[VEHICLE_CO2_KEY]["status"] == "resolved"
                expected = [0.0, 0.0]
                fuel_count = 0
                for exchange in dataset["exchanges"]:
                    if exchange["type"] != "technosphere":
                        continue
                    stem = (
                        exchange["name"]
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
                    fuel_count += 1
                    properties = index[key(exchange)].get(PROPERTIES)
                    if properties:
                        assert properties["unresolved CO2 kg per unit"] == 0
                        factors = (
                            properties["fossil CO2 kg per unit"],
                            properties["non-fossil CO2 kg per unit"],
                        )
                    else:
                        assert stem == "liquefied petroleum gas"
                        factors = (45.5 * 0.0631, 0)
                    for i, factor in enumerate(factors):
                        expected[i] += exchange["amount"] * factor
                assert fuel_count
                assert all(
                    math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-13)
                    for a, b in zip(co2(dataset), expected)
                ), identity_
                carbon += 1
            if COMPRESSION_KEY in dataset and not dataset.get("emptied", False):
                h2 = quantity(dataset, "hydrogen, gaseous, low pressure")
                assert h2 > 0
                assert math.isclose(
                    quantity(dataset, "electricity, low voltage") / h2,
                    EXPECTED,
                    rel_tol=1e-10,
                )
                hydrogen += 1
        assert battery_purchases == 7
        assert len(changed_activities) >= 16
        assert carbon == 495 and hydrogen == 147
        record = json.loads((OUT / f"build_{year}.json").read_text())
        assert record["validation_errors"] == 0

        def warnings(path):
            return Counter(
                (i["rule_id"], tuple(i["activity_key"] or ()))
                for i in issues(path)
                if i["severity"] == "warning"
            )

        assert warnings(OUT / f"validation_{year}.json") == warnings(
            ROOT
            / f"results/premise_vehicle_replacements_20261013/validation_{year}.json"
        )
        summaries[year] = dict(
            activities=len(index),
            changed_exchanges=changed,
            changed_activities=len(changed_activities),
            changed_battery_purchases=battery_purchases,
            rounding_differences=roundoff,
            maximum_rounding_absolute_difference=max_rounding_absolute,
            maximum_rounding_relative_difference=max_rounding_relative,
            carbon_checks=carbon,
            hydrogen_checks=hydrogen,
            validation_errors=0,
            validation_warnings=record["validation_warnings"],
            warning_identities_unchanged=True,
        )
    generation = {}
    for family, name in (("trucks", "trucks"),):
        candidate = WORK / family
        record = json.loads((candidate / "provenance.json").read_text())
        for source, expected in record["source_sha256"].items():
            path = Path(source) if Path(source).is_absolute() else ROOT.parent / source
            assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, source
        installed = (
            ROOT.parent
            / "premise/premise/data/additional_inventories"
            / f"lci-{name}.xlsx"
        )
        assert installed.read_bytes() == (candidate / installed.name).read_bytes()
        generation[family] = record
    write_csv(OUT / "scenario_exchange_changes.csv", rows)
    (OUT / "verification_summary.json").write_text(
        json.dumps(summaries, indent=2) + "\n"
    )
    (OUT / "generation_verification.json").write_text(
        json.dumps(generation, indent=2) + "\n"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
