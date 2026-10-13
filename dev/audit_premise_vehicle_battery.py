"""Independently check full builds against the preceding intensity correction."""

import hashlib
import json
import math
import pickle
from collections import Counter
from pathlib import Path

from audit_premise_vehicle_carbon import coefficients, issues, key, write_csv

ROOT = Path(__file__).resolve().parents[1]
WORK = Path("/private/tmp/premise-vehicle-battery-simple-20261013")
BEFORE = Path("/private/tmp/premise-vehicle-intensity-20261013")
OUT = ROOT / "results/premise_vehicle_battery_simple_20261013"
SPEC = "vehicle battery sizing"
STATE = "premise vehicle battery sizing"


def close(a, b):
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-13)


def expected_mass_ratio(flow, spec, state):
    product = flow[2]
    if product in {"passenger car maintenance", "assembly operation, for lorry"}:
        return state["curb mass kg"] / spec["curb mass kg"]
    if product == "road":
        return state["driving mass kg"] / spec["driving mass kg"]
    for kind in ("road", "tyre", "brake"):
        if product in {
            f"{kind} wear emissions, passenger car",
            f"{kind} wear emissions, lorry",
        }:
            delta = state["pack mass kg"] - spec["pack mass kg"]
            return sum(
                share * ((mass + delta) / mass) ** exponent
                for share, mass, exponent in spec["wear terms"][kind]
            )
    return 1


def warning_counts(path):
    return Counter(
        (i["rule_id"], tuple(i["activity_key"] or ()))
        for i in issues(path)
        if i["severity"] == "warning"
    )


def main():
    summaries, designs, changes = {}, [], []
    for year in (2020, 2030, 2050):
        meta = json.loads((OUT / f"build_{year}.json").read_text())
        path = WORK / str(year) / "database.pickle"
        assert (
            hashlib.sha256(path.read_bytes()).hexdigest()
            == meta["private_inventory_sha256"]
        )
        with path.open("rb") as stream:
            database = {key(d): d for d in pickle.load(stream)}
        baseline = None
        if year != 2030:
            with (BEFORE / str(year) / "database.pickle").open("rb") as stream:
                baseline = {key(d): d for d in pickle.load(stream)}
            assert baseline.keys() <= database.keys()
        checked = added = 0
        for identity, ds in database.items():
            if STATE not in ds or not ds["name"].startswith("transport,"):
                continue
            checked += 1
            spec = json.loads(ds[SPEC]) if isinstance(ds[SPEC], str) else ds[SPEC]
            state = ds[STATE]
            production = sum(
                e["amount"] for e in ds["exchanges"] if e["type"] == "production"
            )
            grid = (
                sum(
                    e["amount"]
                    for e in ds["exchanges"]
                    if e["type"] == "technosphere"
                    and e.get("product") == "electricity, low voltage"
                )
                / production
            )
            factor = grid / spec["grid kWh per service"]
            assert close(state["capacity kWh"], spec["capacity kWh"] * factor)
            assert close(state["replacements"], spec["replacements"])
            assert close(
                state["pack mass kg"],
                state["cell mass kg"] + state["balance of pack mass kg"],
            )
            assert math.isclose(
                state["cell mass kg"] * state["cell density kWh/kg"],
                state["capacity kWh"],
                rel_tol=2e-6,
            )
            assert close(
                state["curb mass kg"] - state["pack mass kg"],
                spec["curb mass kg"] - spec["pack mass kg"],
            )
            assert close(
                state["driving mass kg"] - state["curb mass kg"],
                spec["driving mass kg"] - spec["curb mass kg"],
            )
            load = spec.get("cargo mass kg", 1000) / 1000
            stored_per_electric_km = (
                grid
                * load
                / spec["electric share"]
                * spec["charger efficiency"]
                * spec["charge efficiency"]
            )
            actual_range = (
                state["capacity kWh"]
                * spec["depth of discharge"]
                / stored_per_electric_km
            )
            assert math.isclose(actual_range, spec["electric range km"], rel_tol=3e-6)
            if spec["family"] == "truck":
                assert state["driving mass kg"] <= spec["gross mass kg"]
                assert close(
                    state["available payload kg"],
                    spec["gross mass kg"]
                    - state["driving mass kg"]
                    + spec["cargo mass kg"],
                )
            vehicles = [
                e
                for e in ds["exchanges"]
                if e["type"] == "technosphere"
                and e["unit"] == "unit"
                and e["name"]
                .lower()
                .startswith(("passenger car,", "lorry production,"))
            ]
            assert len(vehicles) == 1
            exc = vehicles[0]
            provider_key = exc["name"], exc["product"], exc["location"], exc["unit"]
            provider = database[provider_key]
            battery = [
                e
                for e in provider["exchanges"]
                if e["type"] == "technosphere"
                and e.get("product") == "electricity storage capacity"
            ]
            assert len(battery) == 1
            assert math.isclose(
                battery[0]["amount"],
                state["capacity kWh"] * (1 + state["replacements"]),
                rel_tol=2e-6,
            )
            if year > 2020:
                assert provider["location"] == ds["location"]
                assert provider[STATE] == state
            designs.append(
                dict(
                    year=year,
                    name=ds["name"],
                    region=ds["location"],
                    powertrain=spec["powertrain"],
                    energy_factor=factor,
                    baseline_capacity_kWh=spec["capacity kWh"],
                    nominal_capacity_kWh=state["capacity kWh"],
                    pack_mass_kg=state["pack mass kg"],
                    curb_mass_kg=state["curb mass kg"],
                    electric_range_km=actual_range,
                    replacements=state["replacements"],
                )
            )
        changed = 0
        if baseline is not None:
            for identity, ds in database.items():
                if identity not in baseline:
                    assert year == 2050 and STATE in ds and ds["unit"] == "unit"
                    source_key = identity[:2] + ("RER", identity[3])
                    old = baseline[source_key]
                    added += 1
                else:
                    old = baseline[identity]
                a, b = coefficients(old), coefficients(ds)
                spec = (
                    json.loads(ds[SPEC])
                    if isinstance(ds.get(SPEC), str)
                    else ds.get(SPEC)
                )
                state = ds.get(STATE)
                expected = {}
                for flow, amount in a.items():
                    target = flow
                    ratio = 1
                    if state is not None:
                        ratio = expected_mass_ratio(flow, spec, state)
                        if ds["unit"] == "unit":
                            if flow[2] == "electricity storage capacity":
                                ratio = state["energy factor"]
                            if flow[0] == "production":
                                target = flow[:3] + (ds["location"],) + flow[4:]
                        elif (
                            flow[0] == "technosphere"
                            and flow[4] == "unit"
                            and flow[1]
                            .lower()
                            .startswith(("passenger car,", "lorry production,"))
                            and year > 2020
                        ):
                            target = flow[:3] + (ds["location"],) + flow[4:]
                    expected[target] = expected.get(target, 0) + amount * ratio
                    if target != flow or not close(amount, amount * ratio):
                        changed += 1
                        changes.append(
                            dict(
                                year=year,
                                name=ds["name"],
                                region=ds["location"],
                                flow=flow[1],
                                before=amount,
                                after=amount * ratio,
                                previous_location=flow[3],
                                new_location=target[3],
                            )
                        )
                assert expected.keys() == b.keys(), identity
                for flow in expected:
                    assert close(expected[flow], b[flow]), (
                        identity,
                        flow,
                        expected[flow],
                        b[flow],
                    )
            assert warning_counts(OUT / f"validation_{year}.json") == warning_counts(
                ROOT
                / "results/premise_vehicle_intensity_20261013"
                / f"validation_{year}.json"
            )
        assert meta["validation_errors"] == 0
        summaries[str(year)] = dict(
            services_checked=checked,
            additional_production_activities=(
                added
                if baseline
                else sum(
                    r["new_production_activities"]
                    for r in meta["battery_sizing_timings"]
                )
            ),
            explained_changed_exchanges=changed if baseline else None,
            all_inventory_differences_explained=True if baseline is not None else None,
            independent_range_mass_capacity_checks_passed=True,
            operating_energy_and_direct_emissions_unchanged=(
                True if baseline is not None else None
            ),
            validation_errors=meta["validation_errors"],
            validation_warnings=meta["validation_warnings"],
            sizing_seconds=sum(t["seconds"] for t in meta["battery_sizing_timings"]),
            build_seconds=meta["seconds"],
        )
    write_csv(OUT / "vehicle_designs.csv", designs)
    write_csv(OUT / "inventory_changes.csv", changes)
    (OUT / "verification_summary.json").write_text(
        json.dumps(summaries, indent=2) + "\n"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
