"""Check complete CNG supplier paths and preserved quantities in fresh builds."""

import csv
import hashlib
import json
import math
import pickle
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/premise_cng_routing_20261013"
WORK = Path("/private/tmp/premise-cng-routing-20261013")
PRODUCT = "natural gas, medium pressure, vehicle grade"
PRODUCTION = "natural gas production, medium pressure, vehicle grade"
MARKET = "market for natural gas, medium pressure, vehicle grade"
BASELINES = {
    2020: Path("/private/tmp/premise-trucks-regional-20261013/database.pickle"),
    2050: Path("/private/tmp/premise-vehicle-2050-audit-20261013/database_2050.pickle"),
}


def load(path):
    data = pickle.loads(path.read_bytes())
    return list(data.values()) if isinstance(data, dict) else data


def key(ds):
    return ds["name"], ds["reference product"], ds["location"], ds["unit"]


def supplier_key(exc):
    return exc["name"], exc["product"], exc["location"], exc["unit"]


def totals(ds, include_locations=False):
    result = defaultdict(float)
    for exc in ds["exchanges"]:
        if exc["type"] == "production":
            continue
        identity = (
            exc["type"],
            exc["name"],
            exc.get("product"),
            exc["unit"],
            tuple(exc.get("categories") or ()),
        )
        if include_locations:
            identity += (exc.get("location"),)
        result[identity] += exc["amount"]
    return dict(result)


def equal_amounts(left, right):
    return all(
        math.isclose(left.get(k, 0), right.get(k, 0), rel_tol=1e-10, abs_tol=1e-15)
        for k in left.keys() | right.keys()
    )


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows, vehicles, changes = [], [], []
    summary = {
        "years": {},
        "scope": "CNG routing only; blend carbon remains a later task",
    }
    for year, baseline_path in BASELINES.items():
        before = load(baseline_path)
        after = load(WORK / str(year) / "database.pickle")
        old_index = {key(ds): ds for ds in before}
        index = {key(ds): ds for ds in after}
        assert len(index) == len(after), "Duplicate activity identities"
        regions = sorted(
            ds["location"]
            for ds in after
            if ds["name"] == MARKET and ds.get("regionalized")
        )
        assert {"EUR", "USA", "IND", "CHA", "World"}.issubset(regions)
        for region in regions:
            market = index[MARKET, PRODUCT, region, "kilogram"]
            purchases = [e for e in market["exchanges"] if e["type"] == "technosphere"]
            assert len(purchases) == 1
            provider = purchases[0]
            assert supplier_key(provider) == (PRODUCTION, PRODUCT, region, "kilogram")
            assert math.isclose(provider["amount"], 1.0, rel_tol=1e-12)
            compression = index[supplier_key(provider)]
            gas = [
                e
                for e in compression["exchanges"]
                if e.get("product") == "natural gas, high pressure"
                and e["type"] == "technosphere"
            ]
            electricity = [
                e
                for e in compression["exchanges"]
                if e.get("product") == "electricity, medium voltage"
                and e["type"] == "technosphere"
            ]
            assert gas and electricity
            for exchange in gas + electricity:
                assert exchange["location"] == region
                assert supplier_key(exchange) in index
            proxy = old_index[
                PRODUCTION, PRODUCT, "CH" if region == "NEU" else "RoW", "kilogram"
            ]
            for product, unit, inputs in (
                ("natural gas, high pressure", "cubic meter", gas),
                ("electricity, medium voltage", "kilowatt hour", electricity),
            ):
                expected = sum(
                    e["amount"]
                    for e in proxy["exchanges"]
                    if e.get("product") == product and e["type"] == "technosphere"
                )
                assert all(e["unit"] == unit for e in inputs)
                assert math.isclose(
                    sum(e["amount"] for e in inputs), expected, rel_tol=1e-10
                )
            for flow in (
                "Methane, fossil",
                "Butane",
                "Ethane",
                "Propane",
                "NMVOC, non-methane volatile organic compounds",
            ):
                amount = sum(
                    e["amount"] for e in compression["exchanges"] if e["name"] == flow
                )
                expected = sum(
                    e["amount"] for e in proxy["exchanges"] if e["name"] == flow
                )
                assert math.isclose(amount, expected, rel_tol=1e-12)
            for ds in (proxy, compression):
                infrastructure = sum(
                    e["amount"]
                    for e in ds["exchanges"]
                    if e.get("product") == "natural gas service station"
                )
                assert math.isclose(infrastructure, 8.4821e-8, rel_tol=1e-10)
            rows.append(
                {
                    "year": year,
                    "region": region,
                    "market_supply_kg_per_kg": provider["amount"],
                    "compression_location": compression["location"],
                    "gas_locations": ";".join(sorted({e["location"] for e in gas})),
                    "gas_m3_per_kg": sum(e["amount"] for e in gas),
                    "electricity_locations": ";".join(
                        sorted({e["location"] for e in electricity})
                    ),
                    "compression_kwh_per_kg": sum(e["amount"] for e in electricity),
                }
            )

        for name, location, target in (
            (PRODUCTION, "CH", "NEU"),
            (PRODUCTION, "RoW", "World"),
            (MARKET, "GLO", "World"),
        ):
            original = index[name, PRODUCT, location, "kilogram"]
            supply = [e for e in original["exchanges"] if e["type"] != "production"]
            assert len(supply) == 1
            assert supplier_key(supply[0]) == (name, PRODUCT, target, "kilogram")
            assert math.isclose(supply[0]["amount"], 1.0, rel_tol=1e-12)

        counts = Counter()
        for ds in after:
            if ds["location"] not in regions or not ds["name"].startswith(
                ("transport, passenger car", "transport, freight, lorry")
            ):
                continue
            for exc in ds["exchanges"]:
                if exc["type"] != "technosphere" or exc["name"] != MARKET:
                    continue
                assert exc["location"] == ds["location"]
                assert supplier_key(exc) in index
                assert equal_amounts(
                    totals(ds), totals(old_index[key(ds)])
                ), "Vehicle quantities changed"
                family = (
                    "car"
                    if ds["name"].startswith("transport, passenger car")
                    else "truck"
                )
                counts[family] += 1
                vehicles.append(
                    {
                        "year": year,
                        "family": family,
                        "name": ds["name"],
                        "region": ds["location"],
                        "fuel_kg_per_service": exc["amount"],
                        "market_location": exc["location"],
                        "compression_location": exc["location"],
                    }
                )
        assert counts["car"] and counts["truck"]

        added = sorted(set(index) - set(old_index))
        removed = sorted(set(old_index) - set(index))
        changed = []
        non_cng_differences = []
        for identity in index.keys() & old_index.keys():
            old = totals(old_index[identity], include_locations=True)
            new = totals(index[identity], include_locations=True)
            if not equal_amounts(old, new):
                changed.append(identity)
                if identity[0] not in {MARKET, PRODUCTION}:
                    differences = [
                        (k, old.get(k, 0), new.get(k, 0))
                        for k in old.keys() | new.keys()
                        if not math.isclose(
                            old.get(k, 0),
                            new.get(k, 0),
                            rel_tol=1e-10,
                            abs_tol=1e-15,
                        )
                    ]
                    if equal_amounts(
                        totals(old_index[identity]), totals(index[identity])
                    ):
                        reason = "exchange location metadata only; quantities unchanged"
                    elif all(
                        k[0] == "biosphere"
                        and k[1] == "Carbon dioxide, non-fossil"
                        and max(abs(a), abs(b)) < 1e-13
                        for k, a, b in differences
                    ):
                        reason = "near-zero carbon reclassification roundoff"
                    else:
                        raise AssertionError(
                            ("Unexpected non-CNG change", identity, differences)
                        )
                    non_cng_differences.append(
                        {
                            "activity": identity,
                            "reason": reason,
                            "differences": sorted(differences, key=repr),
                        }
                    )
                changes.append(
                    {
                        "year": year,
                        "name": identity[0],
                        "product": identity[1],
                        "location": identity[2],
                        "unit": identity[3],
                    }
                )
        record = json.loads((OUT / f"build_{year}.json").read_text())
        summary["years"][str(year)] = {
            "regions": regions,
            "compression_chains_checked": len(regions),
            "vehicle_links_checked": dict(counts),
            "added_activities": added,
            "removed_activities": removed,
            "changed_existing_activities": len(changed),
            "non_cng_comparison_differences": non_cng_differences,
            "validation_errors": record["validation_errors"],
            "validation_warnings": record["validation_warnings"],
            "baseline_inventory_sha256": hashlib.sha256(
                baseline_path.read_bytes()
            ).hexdigest(),
        }
        assert not removed
        assert all(identity[0] == PRODUCTION for identity in added)
        assert record["validation_errors"] == 0

    write_csv(OUT / "regional_chains.csv", rows)
    write_csv(OUT / "vehicle_links.csv", vehicles)
    write_csv(OUT / "changed_activities.csv", changes)
    summary["audit_script_sha256"] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    (OUT / "verification.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
