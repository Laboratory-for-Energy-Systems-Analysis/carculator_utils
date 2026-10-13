"""Audit regenerated car workbook identities, balances and exact 3.12 links."""

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
    parser.add_argument(
        "--audit", type=Path, default=Path("results/premise_vehicle_audit_20261012")
    )
    args = parser.parse_args()
    import bw2data as bd

    bd.projects.set_current("ecoinvent-3.12-cutoff")
    data, _, caches = read_workbook(args.candidate / "lci-pass_cars.xlsx")
    assert not caches
    recipes = [
        r
        for r in csv.DictReader((args.audit / "candidate_recipes.csv").open())
        if r["family"] == "car" and r["selected_for_2020_update"] == "True"
    ]
    services = [d for d in data if d["name"].startswith("transport, passenger car,")]
    assert {identity(d) for d in services} == {identity(r) for r in recipes}
    by_name = {d["name"]: d for d in data}
    pars = {
        r["name"]: r
        for r in csv.DictReader((args.candidate / "vehicle_parameters.csv").open())
    }
    for ds in services:
        par = pars[ds["name"]]
        vehicle = next(
            e
            for e in ds["exchanges"]
            if e["type"] == "technosphere" and e["name"].startswith("Passenger car,")
        )
        assert np.isclose(
            vehicle["amount"], 1 / float(par["lifetime kilometers"]), rtol=1e-6
        )
        manufacture = by_name[vehicle["name"]]
        capacity = sum(
            e["amount"]
            for e in manufacture["exchanges"]
            if e["name"] == "market for battery capacity (MIX scenario)"
        )
        assert np.isclose(
            capacity,
            float(par["electric energy stored"])
            * (1 + float(par["battery lifetime replacements"])),
        )
        assert not any(
            e["name"] == "market for used Li-ion battery"
            for e in manufacture["exchanges"]
        )
        assert not any(
            e["name"].startswith("market for battery, Li-")
            for e in manufacture["exchanges"]
        )
        co2 = sum(
            e["amount"]
            for e in ds["exchanges"]
            if e["name"].startswith("Carbon dioxide,")
        )
        assert np.isclose(co2, float(par["reference_fossil_CO2_kg_per_vkm"]))
        assert not any(
            e["name"] == "Carbon dioxide, non-fossil" for e in ds["exchanges"]
        )
    lpg = next(d for d in services if "liquefied petroleum gas" in d["name"])
    cng = by_name[lpg["name"].replace("liquefied petroleum gas", "compressed gas")]
    assert (
        pars[lpg["name"]]["fuel_energy_MJ_per_vkm"]
        == pars[cng["name"]]["fuel_energy_MJ_per_vkm"]
    )
    assert not any(
        e["name"].startswith("Methane,") and e.get("categories") == "air"
        for e in lpg["exchanges"]
    )
    mapping = yaml.safe_load(
        (
            args.premise / "premise/iam_variables_mapping/transport_passenger_cars.yaml"
        ).read_text()
    )
    selector_counts = {
        tech: sum(matches(d["name"], spec["ecoinvent_aliases"]) for d in services)
        for tech, spec in mapping.items()
        if "ecoinvent_aliases" in spec
    }
    assert all(n == 1 for n in selector_counts.values()), selector_counts
    foreground = {identity(d) for d in data}
    assert len(foreground) == len(data)
    tech = {identity(a) for a in bd.Database("ecoinvent-3.12-cutoff")}
    capacity_data = read_workbook(
        args.premise / "premise/data/additional_inventories/lci-battery-capacity.xlsx"
    )[0]
    capacity_keys = {identity(d) for d in capacity_data}
    biosphere = {
        (a["name"], a["categories"], a["unit"])
        for a in bd.Database("ecoinvent-3.12-biosphere")
    }
    counts, missing = Counter(), Counter()
    for ds in data:
        production = [e for e in ds["exchanges"] if e["type"] == "production"]
        assert len(production) == 1 and production[0]["amount"] == 1
        assert identity(production[0]) == identity(ds)
        for e in ds["exchanges"]:
            assert np.isfinite(e["amount"])
            if e["type"] == "production":
                continue
            if e["type"] == "biosphere":
                key = (e["name"], tuple(e["categories"].split("::")), e["unit"])
                valid = key in biosphere
            else:
                key = identity(e)
                valid = key in foreground or key in tech or key in capacity_keys
            counts[e["type"]] += 1
            if not valid:
                missing[str(key)] += 1
    result = dict(
        services=len(services),
        datasets=len(data),
        exact_links=dict(counts),
        missing=dict(missing),
        selectors=selector_counts,
        lifetime_battery_carbon_lpg_checks_passed=True,
    )
    (args.candidate / "link_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    assert not missing, missing
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
