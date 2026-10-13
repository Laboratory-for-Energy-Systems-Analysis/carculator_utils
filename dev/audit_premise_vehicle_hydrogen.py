"""Verify H2 compression, actual delivery boundary and numerical change scope."""

import hashlib
import json
import math
import pickle
from collections import Counter
from pathlib import Path

from audit_premise_vehicle_carbon import coefficients, issues, key, write_csv
from premise.vehicle_hydrogen import (
    BALANCE_KEY,
    COMPRESSION_KEY,
    finish_hydrogen_compression,
    prepare_hydrogen_compression,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/premise_vehicle_hydrogen_20261013"
WORK = Path("/private/tmp/premise-vehicle-hydrogen-20261013")
BEFORE = Path("/private/tmp/premise-vehicle-carbon-20261013")
EXPECTED = (
    3
    * (1.4 / 0.4)
    * (8.314462618 / 0.00201588)
    * 300
    * ((700 / 30) ** (0.4 / 1.4 / 3) - 1)
    / (0.56 * 0.92 * 3_600_000)
)


def quantity(dataset, product):
    return sum(
        e["amount"]
        for e in dataset["exchanges"]
        if e["type"] == "technosphere" and e.get("product") == product
    )


def distribution_chain(provider, index, visited=None):
    """Follow market forwarders to pipeline delivery, excluding its loss loop."""
    visited = set() if visited is None else visited
    if key(provider) in visited:
        return []
    visited.add(key(provider))
    if provider["name"] == "hydrogen supply, distributed by pipeline":
        return [provider]
    found = []
    for exc in provider["exchanges"]:
        if exc["type"] != "technosphere":
            continue
        if exc["name"] == "hydrogen supply, distributed by pipeline" or (
            exc["name"].startswith(("market for hydrogen", "market group for hydrogen"))
        ):
            found.extend(distribution_chain(index[key(exc)], index, visited))
    return found


def main():
    rows, changed, delivery, summaries = [], [], [], {}
    for year in (2020, 2050):
        with (WORK / str(year) / "database.pickle").open("rb") as stream:
            database = pickle.load(stream)
        with (BEFORE / str(year) / "database.pickle").open("rb") as stream:
            old = pickle.load(stream)
        index, baseline = {key(d): d for d in database}, {key(d): d for d in old}
        assert index.keys() == baseline.keys()
        checked = []
        seen_delivery = set()
        for identity, dataset in index.items():
            a, b = coefficients(baseline[identity]), coefficients(dataset)
            for exc in a.keys() | b.keys():
                if math.isclose(a[exc], b[exc], rel_tol=1e-11, abs_tol=1e-18):
                    continue
                assert COMPRESSION_KEY in dataset, (identity, exc, a[exc], b[exc])
                assert exc[0] == "technosphere" and exc[2] == "electricity, low voltage"
                changed.append(
                    dict(
                        year=year,
                        vehicle=dataset["name"],
                        region=dataset["location"],
                        old=a[exc],
                        new=b[exc],
                    )
                )
            if COMPRESSION_KEY not in dataset or dataset.get("emptied", False):
                continue
            specification = dataset[COMPRESSION_KEY]
            if isinstance(specification, str):
                specification = json.loads(specification)
            assert specification["inlet pressure bar"] == 30
            assert specification["tank pressure bar"] == 700
            assert math.isclose(
                specification["electricity kWh per kg H2"], EXPECTED, rel_tol=1e-12
            )
            hydrogen = quantity(dataset, "hydrogen, gaseous, low pressure")
            electricity = quantity(dataset, "electricity, low voltage")
            assert hydrogen > 0
            assert math.isclose(electricity / hydrogen, EXPECTED, rel_tol=1e-10)
            assert math.isclose(
                dataset[BALANCE_KEY]["compression electricity kWh"],
                electricity,
                rel_tol=1e-10,
            )
            previous = baseline[identity]
            assert quantity(previous, "hydrogen, gaseous, low pressure") == hydrogen
            previous_electricity = quantity(previous, "electricity, low voltage")
            for exc in dataset["exchanges"]:
                if (
                    exc["type"] != "technosphere"
                    or exc.get("product") != "hydrogen, gaseous, low pressure"
                ):
                    continue
                sources = distribution_chain(index[key(exc)], index)
                assert sources, (identity, "No pipeline delivery boundary")
                for source in sources:
                    assert "Arrives at 30 bar" in source.get("comment", ""), key(source)
                    if key(source) in seen_delivery:
                        continue
                    seen_delivery.add(key(source))
                    delivery.append(
                        dict(
                            year=year,
                            provider=source["name"],
                            region=source["location"],
                            delivered_bar=30,
                            electricity_kWh_per_kg=quantity(
                                source, "electricity, low voltage"
                            ),
                            loss_replacement_locations=";".join(
                                sorted(
                                    {
                                        e["location"]
                                        for e in source["exchanges"]
                                        if e["type"] == "technosphere"
                                        and e.get("product")
                                        == "hydrogen, gaseous, low pressure"
                                    }
                                )
                            ),
                        )
                    )
            once = coefficients(dataset)
            finish_hydrogen_compression(dataset, prepare_hydrogen_compression(dataset))
            assert coefficients(dataset) == once
            checked.append(identity)
            rows.append(
                dict(
                    year=year,
                    vehicle=dataset["name"],
                    region=dataset["location"],
                    unit=dataset["unit"],
                    hydrogen_kg=hydrogen,
                    old_electricity_kWh=previous_electricity,
                    new_electricity_kWh=electricity,
                    old_kWh_per_kg=previous_electricity / hydrogen,
                    new_kWh_per_kg=electricity / hydrogen,
                    electricity_change_percent=100
                    * (electricity / previous_electricity - 1),
                    efficiency_factor=dataset.get("log parameters", {}).get(
                        "efficiency change", 1
                    ),
                )
            )
        record = json.loads((OUT / f"build_{year}.json").read_text())
        old_warnings = Counter(
            (i["rule_id"], tuple(i["activity_key"] or ()))
            for i in issues(
                ROOT / f"results/premise_vehicle_carbon_20261013/validation_{year}.json"
            )
            if i["severity"] == "warning"
        )
        new_warnings = Counter(
            (i["rule_id"], tuple(i["activity_key"] or ()))
            for i in issues(OUT / f"validation_{year}.json")
            if i["severity"] == "warning"
        )
        assert old_warnings == new_warnings
        assert record["validation_errors"] == 0
        summaries[year] = dict(
            checked_vehicles=len(checked),
            cars=sum("passenger car" in k[0] for k in checked),
            trucks=sum("lorry" in k[0] for k in checked),
            locations=sorted({k[2] for k in checked}),
            matching_delivery_chains=len(seen_delivery),
            changes_outside_compression_electricity=0,
            validation_errors=record["validation_errors"],
            validation_warnings=record["validation_warnings"],
            warning_identities_unchanged=True,
        )
    for filename, records in (
        ("vehicle_compression_comparison.csv", rows),
        ("changed_electricity_exchanges.csv", changed),
        ("hydrogen_delivery_boundary.csv", delivery),
    ):
        write_csv(OUT / filename, records)
    for year in (2020, 2050):
        record = json.loads((OUT / f"build_{year}.json").read_text())
        for rel, expected in record["python_sources"].items():
            assert (
                hashlib.sha256((ROOT.parent / "premise" / rel).read_bytes()).hexdigest()
                == expected
            ), rel
    (OUT / "verification_summary.json").write_text(
        json.dumps(summaries, indent=2) + "\n"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
