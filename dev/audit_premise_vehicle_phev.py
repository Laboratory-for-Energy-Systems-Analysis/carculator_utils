"""Verify PHEV purchases and unchanged operating inventories in full scenarios."""

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
from audit_premise_vehicle_workbooks import identity, read_workbook
from install_premise_phev_capacity import coefficients as workbook_coefficients

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/premise_vehicle_phev_20261013"
WORK = Path("/private/tmp/premise-vehicle-phev-20261013")
BEFORE = Path("/private/tmp/premise-vehicle-hydrogen-20261013")


def main():
    rows, summaries = [], {}
    with (OUT / "car_battery_capacity_changes.csv").open() as stream:
        expected_capacities = {
            r["vehicle"]: float(r["new_kWh"]) for r in csv.DictReader(stream)
        }
    for year in (2020, 2050):
        with (WORK / str(year) / "database.pickle").open("rb") as stream:
            index = {key(d): d for d in pickle.load(stream)}
        with (BEFORE / str(year) / "database.pickle").open("rb") as stream:
            previous = {key(d): d for d in pickle.load(stream)}
        assert index.keys() == previous.keys()
        changed, carbon, hydrogen, roundoff = 0, 0, 0, 0
        max_rounding_absolute = max_rounding_relative = 0.0
        for identity_, dataset in index.items():
            a, b = coefficients(previous[identity_]), coefficients(dataset)
            assert a.keys() == b.keys(), identity_
            for exchange in a:
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
                assert identity_[0].startswith("Passenger car, plugin"), identity_
                assert (
                    exchange[1] == "market for battery capacity (MIX scenario)"
                ), exchange
                assert b[exchange] > a[exchange]
                assert math.isclose(
                    b[exchange], expected_capacities[identity_[0]], rel_tol=1e-12
                )
                changed += 1
                rows.append(
                    dict(
                        year=year,
                        vehicle=identity_[0],
                        location=identity_[2],
                        before_kWh=a[exchange],
                        after_kWh=b[exchange],
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
        assert changed == 16
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
            ROOT / f"results/premise_vehicle_hydrogen_20261013/validation_{year}.json"
        )
        summaries[year] = dict(
            activities=len(index),
            changed_battery_purchases=changed,
            rounding_differences=roundoff,
            maximum_rounding_absolute_difference=max_rounding_absolute,
            maximum_rounding_relative_difference=max_rounding_relative,
            carbon_checks=carbon,
            hydrogen_checks=hydrogen,
            validation_errors=0,
            validation_warnings=record["validation_warnings"],
            warning_identities_unchanged=True,
        )
    # Re-run the adapters from fresh final models after correcting purchase costs.
    # They must reproduce the already-built physical inventory and assumptions.
    replay = {}
    for family, name in (("cars", "pass_cars"), ("trucks", "trucks")):
        original, final = WORK / family, WORK / f"final-{family}"
        for filename in (
            "model_parameters.json",
            "vehicle_parameters.csv",
            "noise_audit.csv",
        ):
            assert (original / filename).read_bytes() == (
                final / filename
            ).read_bytes(), filename
        first = {
            identity(d): d for d in read_workbook(original / f"lci-{name}.xlsx")[0]
        }
        second = {identity(d): d for d in read_workbook(final / f"lci-{name}.xlsx")[0]}
        assert first.keys() == second.keys()
        for ident in first:
            assert workbook_coefficients(first[ident]) == workbook_coefficients(
                second[ident]
            )
            assert first[ident].get("comment") == second[ident].get("comment")
        replay[family] = dict(
            datasets=len(first),
            exact_physical_reproduction=True,
            final_model_generation=json.loads((final / "provenance.json").read_text()),
            raw_sha256=hashlib.sha256((final / "raw.json").read_bytes()).hexdigest(),
        )
    write_csv(OUT / "scenario_battery_capacity_changes.csv", rows)
    (OUT / "verification_summary.json").write_text(
        json.dumps(summaries, indent=2) + "\n"
    )
    (OUT / "final_model_reproduction.json").write_text(
        json.dumps(replay, indent=2) + "\n"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
