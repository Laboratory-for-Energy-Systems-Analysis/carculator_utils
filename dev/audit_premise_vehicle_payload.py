"""Check fixed-utilization BEV trucks against the preceding constant-load builds."""

import hashlib
import json
import math
import pickle
from pathlib import Path
from xml.etree import ElementTree

from audit_premise_vehicle_battery import close, warning_counts
from audit_premise_vehicle_carbon import coefficients, key, write_csv

ROOT = Path(__file__).resolve().parents[1]
WORK = Path("/private/tmp/premise-vehicle-payload-20261013")
BEFORE = Path("/private/tmp/premise-vehicle-battery-simple-20261013")
OUT = ROOT / "results/premise_vehicle_payload_20261013"
OLD_OUT = ROOT / "results/premise_vehicle_battery_simple_20261013"
SOURCE = ROOT.parent / "premise"
SPEC = "vehicle battery sizing"
STATE = "premise vehicle battery sizing"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_database(workspace, year, meta):
    path = workspace / str(year) / "database.pickle"
    assert digest(path) == meta["private_inventory_sha256"]
    with path.open("rb") as stream:
        return {key(d): d for d in pickle.load(stream)}


def grid_per_service(dataset):
    return sum(
        e["amount"]
        for e in dataset["exchanges"]
        if e["type"] == "technosphere"
        and e.get("product") == "electricity, low voltage"
    ) / sum(e["amount"] for e in dataset["exchanges"] if e["type"] == "production")


def main():
    designs, changes, summaries = [], [], {}
    for year in (2020, 2030, 2050):
        meta = json.loads((OUT / f"build_{year}.json").read_text())
        old_meta = json.loads((OLD_OUT / f"build_{year}.json").read_text())
        for field in ("workbooks", "iam_files", "fuel_properties_sha256"):
            assert meta[field] == old_meta[field], field
        assert {
            name
            for name, value in meta["python_sources"].items()
            if old_meta["python_sources"].get(name) != value
        } == {"premise/vehicle_battery.py"}
        for name, value in meta["python_sources"].items():
            assert digest(SOURCE / name) == value, name
        database = load_database(WORK, year, meta)
        baseline = load_database(BEFORE, year, old_meta)
        assert baseline.keys() == database.keys()
        checked = changed = 0
        for identity, ds in database.items():
            old = baseline[identity]
            a, b = coefficients(old), coefficients(ds)
            assert a.keys() == b.keys(), identity
            spec = ds.get(SPEC)
            spec = json.loads(spec) if isinstance(spec, str) else spec
            state = ds.get(STATE)
            bev_truck = (
                state
                and spec["family"] == "truck"
                and spec["powertrain"] == "BEV"
                and ds["unit"] == "ton kilometer"
            )
            normalization, new_driving, old_driving = 1, None, None
            if bev_truck:
                checked += 1
                old_state = old[STATE]
                # Capacity, physical pack and IAM per-vkm energy target stay identical.
                for field in (
                    "capacity kWh",
                    "pack mass kg",
                    "curb mass kg",
                    "energy factor",
                    "cell density kWh/kg",
                    "replacements",
                ):
                    assert close(state[field], old_state[field]), (identity, field)
                passengers = (
                    spec["driving mass kg"]
                    - spec["curb mass kg"]
                    - spec["cargo mass kg"]
                )
                base_available = (
                    spec["gross mass kg"] - spec["curb mass kg"] - passengers
                )
                utilization = spec["cargo mass kg"] / base_available
                available = spec["gross mass kg"] - state["curb mass kg"] - passengers
                cargo = available * utilization
                new_driving = state["curb mass kg"] + passengers + cargo
                old_driving = old_state["driving mass kg"]
                assert close(state["cargo mass kg"], cargo)
                assert close(state["available payload kg"], available)
                assert close(state["capacity utilization"], utilization)
                assert close(state["driving mass kg"], new_driving)
                assert new_driving <= spec["gross mass kg"]
                normalization = old_state["cargo mass kg"] / cargo
                assert close(state["payload normalization factor"], normalization)
                per_km = grid_per_service(ds) * cargo / 1000
                assert close(
                    per_km, grid_per_service(old) * spec["cargo mass kg"] / 1000
                )
                actual_range = (
                    state["capacity kWh"]
                    * spec["depth of discharge"]
                    / (per_km * spec["charger efficiency"] * spec["charge efficiency"])
                )
                assert math.isclose(
                    actual_range, spec["electric range km"], rel_tol=3e-6
                )
                vehicles = [
                    e
                    for e in ds["exchanges"]
                    if e["type"] == "technosphere"
                    and e["unit"] == "unit"
                    and e["name"].startswith("lorry production,")
                ]
                assert len(vehicles) == 1
                exc = vehicles[0]
                output = sum(
                    e["amount"] for e in ds["exchanges"] if e["type"] == "production"
                )
                assert math.isclose(
                    exc["amount"] / output,
                    1 / (spec["lifetime km"] * cargo / 1000),
                    rel_tol=3e-6,
                )
                provider = database[
                    (exc["name"], exc["product"], exc["location"], exc["unit"])
                ]
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
                    assert provider[STATE] == state
                designs.append(
                    dict(
                        year=year,
                        name=ds["name"],
                        region=ds["location"],
                        baseline_cargo_kg=spec["cargo mass kg"],
                        cargo_kg=cargo,
                        baseline_available_payload_kg=base_available,
                        available_payload_kg=available,
                        capacity_utilization=utilization,
                        per_tkm_multiplier=normalization,
                        capacity_kWh=state["capacity kWh"],
                        pack_mass_kg=state["pack mass kg"],
                        driving_mass_kg=new_driving,
                        range_km=actual_range,
                    )
                )
            for flow, amount in a.items():
                ratio = 1
                if bev_truck and flow[0] != "production":
                    ratio = normalization
                    if flow[2] == "road" and flow[4] == "meter-year":
                        ratio *= new_driving / old_driving
                    for wear in ("road", "brake", "tyre"):
                        if flow[2] == f"{wear} wear emissions, lorry":

                            def mass_power(driving):
                                return sum(
                                    share
                                    * (1 + (driving - spec["driving mass kg"]) / mass)
                                    ** power
                                    for share, mass, power in spec["wear terms"][wear]
                                )

                            ratio *= mass_power(new_driving) / mass_power(old_driving)
                assert close(amount * ratio, b[flow]), (
                    identity,
                    flow,
                    amount * ratio,
                    b[flow],
                )
                if not close(amount, b[flow]):
                    assert bev_truck and year > 2020
                    changed += 1
                    changes.append(
                        dict(
                            year=year,
                            name=ds["name"],
                            region=ds["location"],
                            flow=flow[1],
                            type=flow[0],
                            before=amount,
                            after=b[flow],
                            ratio=ratio,
                        )
                    )
        assert checked == 65
        assert meta["validation_errors"] == 0
        assert warning_counts(OUT / f"validation_{year}.json") == warning_counts(
            OLD_OUT / f"validation_{year}.json"
        )
        summaries[str(year)] = dict(
            regional_bev_trucks_checked=checked,
            activities=meta["activities"],
            explained_changed_exchanges=changed,
            all_inventory_differences_explained=True,
            non_bev_truck_service_inventories_unchanged=True,
            all_per_vehicle_production_inventories_unchanged=True,
            range_payload_mass_and_truck_purchase_checks_passed=True,
            validation_errors=meta["validation_errors"],
            validation_warnings=meta["validation_warnings"],
            sizing_seconds=sum(t["seconds"] for t in meta["battery_sizing_timings"]),
            build_seconds=meta["seconds"],
        )
    suite = ElementTree.parse(WORK / "tests.xml").getroot().find("testsuite")
    assert suite.attrib["failures"] == suite.attrib["errors"] == "0"
    summaries["tests"] = dict(suite.attrib)
    write_csv(OUT / "vehicle_designs.csv", designs)
    write_csv(OUT / "inventory_changes.csv", changes)
    (OUT / "verification_summary.json").write_text(
        json.dumps(summaries, indent=2) + "\n"
    )
    (OUT / "verification_sources.json").write_text(
        json.dumps(
            {
                "audit_script_sha256": digest(Path(__file__)),
                "tests_xml_sha256": digest(WORK / "tests.xml"),
                "premise_test_sha256": digest(
                    SOURCE / "tests/test_vehicle_battery_sizing.py"
                ),
                "baseline_audit": "premise_vehicle_battery_simple_20261013",
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
