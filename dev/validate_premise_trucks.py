"""Check truck workbook coverage, balances and exact ecoinvent 3.12 links."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
import yaml

from audit_premise_vehicle_workbooks import identity, matches, read_workbook


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--premise", type=Path, required=True)
    args = parser.parse_args()
    import bw2data as bd

    bd.projects.set_current("ecoinvent-3.12-cutoff")
    data, _, caches = read_workbook(args.candidate / "lci-trucks.xlsx")
    assert not caches
    root = Path(__file__).resolve().parents[1]
    recipes = [
        r
        for r in csv.DictReader(
            (
                root / "results/premise_vehicle_audit_20261012/candidate_recipes.csv"
            ).open()
        )
        if r["family"] == "truck"
    ]
    services = [d for d in data if d["name"].startswith("transport, freight, lorry,")]
    assert {identity(d) for d in services} == {identity(r) for r in recipes}
    by_name = {d["name"]: d for d in data}
    parameters = {
        r["name"]: r
        for r in csv.DictReader((args.candidate / "vehicle_parameters.csv").open())
    }
    balances = []
    for ds in services:
        p = parameters[ds["name"]]
        load = float(p["cargo mass"]) / 1000
        assert p["cycle"] == "Regional delivery"
        if p["powertrain"] != "PHEV-d":
            assert float(p["target range"]) == 400
        vehicle = next(
            e
            for e in ds["exchanges"]
            if e["type"] == "technosphere" and e["name"].startswith("lorry production,")
        )
        np.testing.assert_allclose(
            vehicle["amount"], 1 / (load * float(p["lifetime kilometers"])), rtol=1e-6
        )
        manufacture = by_name[vehicle["name"]]
        capacity = sum(
            e["amount"]
            for e in manufacture["exchanges"]
            if e["name"] == "market for battery capacity (MIX scenario)"
        )
        np.testing.assert_allclose(
            capacity,
            float(p["nominal battery capacity kWh"])
            * (1 + float(p["battery lifetime replacements"])),
            rtol=1e-6,
        )
        assert not any(
            e["name"].startswith("market for battery, Li-")
            or e["name"] == "market for used Li-ion battery"
            for e in manufacture["exchanges"]
        )
        co2 = sum(
            e["amount"]
            for e in ds["exchanges"]
            if e["name"].startswith("Carbon dioxide,")
        )
        np.testing.assert_allclose(
            co2, float(p["reference_fossil_CO2_kg_per_tkm"]), rtol=1e-6, atol=1e-14
        )
        electricity = sum(
            e["amount"]
            for e in ds["exchanges"]
            if e["name"] == "market group for electricity, low voltage"
        )
        np.testing.assert_allclose(
            electricity,
            float(p["electricity consumption"]) / load
            + float(p["h2_compression_kWh_per_tkm"]),
            rtol=1e-6,
            atol=1e-14,
        )
        if p["powertrain"] == "BEV":
            np.testing.assert_allclose(
                float(p["electric energy stored"]) * float(p["battery DoD"]),
                400 * float(p["TtW energy"]) / 3600,
                rtol=1e-6,
            )
        if "liquefied petroleum gas" in ds["name"]:
            assert not any(
                e["name"].startswith("Methane,") and e.get("categories") == "air"
                for e in ds["exchanges"]
            )
        if p["proxy"] == "True":
            target = (
                ds["name"]
                .replace("liquefied petroleum gas", "compressed gas")
                .replace("gasoline", "diesel")
            )
            assert (
                p["fuel_energy_MJ_per_tkm"]
                == parameters[target]["fuel_energy_MJ_per_tkm"]
            )
        balances.append(
            dict(
                name=ds["name"],
                lifetime_allocation=True,
                grid_purchase=True,
                battery_capacity=True,
                carbon=True,
            )
        )
    mapping = yaml.safe_load(
        (
            args.premise / "premise/iam_variables_mapping/transport_road_freight.yaml"
        ).read_text()
    )
    selectors = {
        name: sum(matches(d["name"], value["ecoinvent_aliases"]) for d in services)
        for name, value in mapping.items()
        if "ecoinvent_aliases" in value
    }
    assert all(count == 1 for count in selectors.values()), selectors
    foreground = {identity(d) for d in data}
    assert len(foreground) == len(data)
    tech = {identity(a) for a in bd.Database("ecoinvent-3.12-cutoff")}
    capacities = {
        identity(d)
        for d in read_workbook(
            args.premise
            / "premise/data/additional_inventories/lci-battery-capacity.xlsx"
        )[0]
    }
    biosphere = {
        (a["name"], a["categories"], a["unit"])
        for a in bd.Database("ecoinvent-3.12-biosphere")
    }
    missing, counts = Counter(), Counter()
    for ds in data:
        prod = [e for e in ds["exchanges"] if e["type"] == "production"]
        assert (
            len(prod) == 1
            and prod[0]["amount"] == 1
            and identity(prod[0]) == identity(ds)
        )
        for exc in ds["exchanges"]:
            assert np.isfinite(exc["amount"])
            assert exc["unit"] != "joule"
            if exc["type"] == "production":
                continue
            if exc["type"] == "biosphere":
                key = (exc["name"], tuple(exc["categories"].split("::")), exc["unit"])
                valid = key in biosphere
            else:
                key = identity(exc)
                valid = key in foreground or key in tech or key in capacities
            counts[exc["type"]] += 1
            if not valid:
                missing[str(key)] += 1
    result = dict(
        services=len(services),
        datasets=len(data),
        selectors=selectors,
        exact_links=dict(counts),
        missing=dict(missing),
        balances=balances,
    )
    (args.candidate / "link_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    assert not missing, missing
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"selectors", "balances"}},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
