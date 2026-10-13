"""Check restored intensity integration against complete previous scenario builds."""

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
OUT = ROOT / "results/premise_vehicle_intensity_20261013"
WORK = Path("/private/tmp/premise-vehicle-intensity-20261013")
BEFORE = Path("/private/tmp/premise-vehicle-efficiency-20261013")


def warning_counts(path):
    return Counter(
        (i["rule_id"], tuple(i["activity_key"] or ()))
        for i in issues(path)
        if i["severity"] == "warning"
    )


def main():
    changes, summaries, warning_changes = [], {}, []
    manufacturing_baseline = {}
    for year in (2020, 2050):
        record = json.loads((OUT / f"build_{year}.json").read_text())
        path = WORK / str(year) / "database.pickle"
        assert (
            hashlib.sha256(path.read_bytes()).hexdigest()
            == record["private_inventory_sha256"]
        )
        with path.open("rb") as stream:
            index = {key(d): d for d in pickle.load(stream)}
        with (BEFORE / str(year) / "database.pickle").open("rb") as stream:
            previous = {key(d): d for d in pickle.load(stream)}
        assert index.keys() == previous.keys()
        changed_activities = set()
        roundoff = changed = carbon = hydrogen = 0
        corrected_manufacture = 0
        flows = Counter()
        for identity, dataset in index.items():
            old = previous[identity]
            a, b = coefficients(old), coefficients(dataset)
            if year == 2020:
                for exchange, amount in b.items():
                    if exchange[0] == "technosphere" and exchange[2] in (
                        "truck",
                        "passenger car",
                    ):
                        manufacturing_baseline[identity, exchange] = amount
            for exchange in a.keys() | b.keys():
                before, after = a.get(exchange, 0), b.get(exchange, 0)
                if before == after:
                    continue
                if math.isclose(before, after, rel_tol=1e-9, abs_tol=1e-13):
                    roundoff += 1
                    continue
                assert year == 2050, (identity, exchange, before, after)
                assert identity[0].startswith(
                    ("transport, passenger car,", "transport, freight, lorry,")
                ), identity

                def energy_factor(ds):
                    log = ds.get("log parameters", {})
                    return log.get("efficiency change", 1) * log.get(
                        "car energy floor", {}
                    ).get("floor correction factor", 1)

                ratio = energy_factor(dataset) / energy_factor(old)
                reason = "operating energy"
                if exchange[0] == "biosphere":
                    assert exchange[1] in (
                        "Carbon dioxide, fossil",
                        "Carbon dioxide, non-fossil",
                        "Sulfur dioxide",
                        "Methane, fossil",
                        "Methane, non-fossil",
                    ), (identity, exchange)
                    if not exchange[1].startswith("Carbon dioxide"):
                        assert exchange[-1] in (("air",), ("air", "unspecified")), (
                            identity,
                            exchange,
                        )
                else:
                    assert exchange[0] == "technosphere", (identity, exchange)
                    stem = (
                        exchange[1]
                        .removeprefix("market for ")
                        .removeprefix("market group for ")
                    )
                    if (
                        exchange[2] in ("truck", "passenger car")
                        and exchange[4] == "unit"
                    ):
                        # Undo the old fuel-name substring selection of vehicle
                        # manufacture, independently checked against 2020 use.
                        ratio = 1 / energy_factor(old)
                        assert math.isclose(
                            after,
                            manufacturing_baseline[identity, exchange],
                            rel_tol=1e-9,
                            abs_tol=1e-13,
                        )
                        corrected_manufacture += 1
                        reason = "remove manufacture scaling"
                    else:
                        assert stem.startswith(
                            (
                                "petrol",
                                "gasoline",
                                "diesel",
                                "natural gas",
                                "hydrogen",
                                "electricity",
                            )
                        ), (identity, exchange)
                assert math.isclose(
                    after, before * ratio, rel_tol=1e-8, abs_tol=1e-13
                ), (identity, exchange, before, after, ratio)
                changed += 1
                changed_activities.add(identity)
                flows[exchange[1]] += 1
                changes.append(
                    dict(
                        year=year,
                        vehicle=identity[0],
                        location=identity[2],
                        flow=exchange[1],
                        exchange_type=exchange[0],
                        before=before,
                        after=after,
                        effective_energy_ratio=ratio,
                        reason=reason,
                    )
                )
            if VEHICLE_CO2_KEY in dataset:
                assert dataset[VEHICLE_CO2_KEY]["status"] == "resolved"
                expected = [0, 0]
                fuel_count = 0
                for e in dataset["exchanges"]:
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
                    fuel_count += 1
                    properties = index[key(e)].get(PROPERTIES)
                    if properties:
                        assert properties["unresolved CO2 kg per unit"] == 0
                        factors = [
                            properties[f"{origin} CO2 kg per unit"]
                            for origin in ("fossil", "non-fossil")
                        ]
                    else:
                        assert stem == "liquefied petroleum gas"
                        factors = [45.5 * 0.0631, 0]
                    for i, factor in enumerate(factors):
                        expected[i] += e["amount"] * factor
                assert fuel_count
                assert all(
                    math.isclose(x, y, rel_tol=1e-10, abs_tol=1e-13)
                    for x, y in zip(co2(dataset), expected)
                ), identity
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
        assert carbon == 495 and hydrogen == 147
        assert record["validation_errors"] == 0
        old_warnings = warning_counts(
            ROOT / f"results/premise_vehicle_efficiency_20261013/validation_{year}.json"
        )
        new_warnings = warning_counts(OUT / f"validation_{year}.json")
        for identity in old_warnings.keys() | new_warnings.keys():
            if old_warnings[identity] != new_warnings[identity]:
                warning_changes.append(
                    dict(
                        year=year,
                        rule=identity[0],
                        activity=identity[1],
                        before=old_warnings[identity],
                        after=new_warnings[identity],
                    )
                )
        summaries[year] = dict(
            activities=len(index),
            changed_exchanges=changed,
            changed_activities=len(changed_activities),
            changed_flow_counts=dict(flows),
            rounding_differences=roundoff,
            carbon_checks=carbon,
            hydrogen_checks=hydrogen,
            validation_errors=0,
            validation_warnings=record["validation_warnings"],
            warning_identities_unchanged=old_warnings == new_warnings,
            unchanged_nonfuel_emissions_and_vehicle_hardware=True,
            corrected_manufacturing_purchases=corrected_manufacture,
            recorded_efficiency_sources=dict(
                Counter(
                    ds.get("log parameters", {})
                    .get("IAM efficiency source", {})
                    .get("kind")
                    for ds in index.values()
                    if "IAM efficiency source" in ds.get("log parameters", {})
                )
            ),
        )
    write_csv(OUT / "scenario_energy_changes.csv", changes)
    (OUT / "warning_changes.json").write_text(
        json.dumps(warning_changes, indent=2) + "\n"
    )
    (OUT / "verification_summary.json").write_text(
        json.dumps(summaries, indent=2) + "\n"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
