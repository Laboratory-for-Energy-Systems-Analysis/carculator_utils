"""Explain all full-build inventory changes from the Large Car intensity proxy."""

import csv
import json
import math
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

from audit_premise_vehicle_battery import close, expected_mass_ratio, warning_counts
from audit_premise_vehicle_payload import digest, load_database, grid_per_service
from audit_premise_vehicle_carbon import (
    PROPERTIES,
    VEHICLE_CO2_KEY,
    co2,
    coefficients,
    key,
    issues,
    write_csv,
)
from audit_premise_vehicle_hydrogen import COMPRESSION_KEY, EXPECTED, quantity

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "premise"
WORK = Path("/private/tmp/premise-large-car-proxy-20261013")
BEFORE = Path("/private/tmp/premise-vehicle-payload-20261013")
OUT = ROOT / "results/premise_large_car_proxy_20261013"
OLD_OUT = ROOT / "results/premise_vehicle_payload_20261013"
STATE, SPEC = "premise vehicle battery sizing", "vehicle battery sizing"


def energy_factor(ds):
    log = ds.get("log parameters", {})
    return log.get("efficiency change", 1) * log.get("car energy floor", {}).get(
        "floor correction factor", 1
    )


def source(ds):
    return ds.get("log parameters", {}).get("IAM efficiency source", {})


def fuel_carbon(ds, index):
    expected = [0, 0]
    count = 0
    for exc in ds["exchanges"]:
        if exc["type"] != "technosphere":
            continue
        stem = exc["name"].removeprefix("market for ").removeprefix("market group for ")
        if not stem.startswith(
            ("petrol", "gasoline", "diesel", "natural gas", "liquefied petroleum gas")
        ):
            continue
        count += 1
        properties = index[key(exc)].get(PROPERTIES)
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
            expected[i] += exc["amount"] * factor
    assert count
    assert all(
        math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-13)
        for a, b in zip(co2(ds), expected)
    ), key(ds)


def main():
    factors = list(csv.DictReader((OUT / "proxy_factors.csv").open()))
    factor_map = {
        (r["region"], r["proxy_variable"]): r
        for r in factors
        if r["model"] == "remind" and r["pathway"] == "SSP2-NPi"
    }
    summaries, changes, designs, warning_changes = {}, [], [], []
    for year in (2020, 2050):
        meta = json.loads((OUT / f"build_{year}.json").read_text())
        old_meta = json.loads((OLD_OUT / f"build_{year}.json").read_text())
        for field in ("workbooks", "iam_files", "fuel_properties_sha256"):
            assert meta[field] == old_meta[field]
        for section in ("python_sources", "transport_mapping_sources"):
            for path, value in meta[section].items():
                assert digest(SOURCE / path) == value, path
        assert {
            k
            for k, v in meta["python_sources"].items()
            if v != old_meta["python_sources"][k]
        } == {"premise/data_collection.py", "premise/transport.py"}
        database = load_database(WORK, year, meta)
        baseline = load_database(BEFORE, year, old_meta)
        assert database.keys() == baseline.keys()
        proxy_count = carbon_count = hydrogen_count = changed = 0
        changed_activities, providers = set(), set()
        for identity, ds in database.items():
            detail = source(ds)
            if detail.get("kind") == "proxy intensity":
                proxy_count += 1
                assert source(baseline[identity])["kind"] == "unavailable"
                expected = factor_map[(ds["location"], detail["intensity variable"])]
                iam_factor = (
                    1 if year == 2020 else float(expected["energy_factor_2050"])
                )
                assert close(
                    ds["log parameters"].get("efficiency change", 1), iam_factor
                )
                assert (
                    detail["native intensity variable"] == expected["native_variable"]
                )
                assert detail["intensity variable"] in ds["comment"]
                assert ds["comment"].count("IAM efficiency proxy") == 1
                if STATE in ds:
                    state = ds[STATE]
                    spec = (
                        json.loads(ds[SPEC]) if isinstance(ds[SPEC], str) else ds[SPEC]
                    )
                    f = grid_per_service(ds) / spec["grid kWh per service"]
                    assert close(state["capacity kWh"], spec["capacity kWh"] * f)
                    assert close(state["energy factor"], f)
                    assert math.isclose(
                        state["pack mass kg"]
                        * spec["cell mass share"]
                        * state["cell density kWh/kg"],
                        state["capacity kWh"],
                        rel_tol=2e-6,
                    )
                    stored_km = (
                        grid_per_service(ds)
                        * spec["charge efficiency"]
                        * spec["charger efficiency"]
                        / spec["electric share"]
                    )
                    actual_range = (
                        state["capacity kWh"] * spec["depth of discharge"] / stored_km
                    )
                    assert math.isclose(
                        actual_range, spec["electric range km"], rel_tol=3e-6
                    )
                    vehicle = [
                        e
                        for e in ds["exchanges"]
                        if e["type"] == "technosphere"
                        and e["unit"] == "unit"
                        and e["name"].lower().startswith("passenger car,")
                    ]
                    assert len(vehicle) == 1
                    provider_key = key(vehicle[0])
                    if year > 2020:
                        providers.add(provider_key)
                        assert database[provider_key][STATE] == state
                    designs.append(
                        dict(
                            year=year,
                            name=ds["name"],
                            region=ds["location"],
                            capacity_kWh=state["capacity kWh"],
                            pack_mass_kg=state["pack mass kg"],
                            electric_range_km=actual_range,
                            energy_factor=f,
                        )
                    )
            if VEHICLE_CO2_KEY in ds:
                assert ds[VEHICLE_CO2_KEY]["status"] == "resolved"
                fuel_carbon(ds, database)
                carbon_count += 1
            if COMPRESSION_KEY in ds and not ds.get("emptied", False):
                h2 = quantity(ds, "hydrogen, gaseous, low pressure")
                assert h2 > 0
                assert math.isclose(
                    quantity(ds, "electricity, low voltage") / h2,
                    EXPECTED,
                    rel_tol=1e-10,
                )
                hydrogen_count += 1
        for identity, ds in database.items():
            old = baseline[identity]
            a, b = coefficients(old), coefficients(ds)
            assert a.keys() == b.keys(), identity
            is_proxy = source(ds).get("kind") == "proxy intensity"
            ratio_energy = energy_factor(ds) / energy_factor(old) if is_proxy else 1
            state, old_state = ds.get(STATE), old.get(STATE)
            spec = ds.get(SPEC)
            spec = json.loads(spec) if isinstance(spec, str) else spec
            for flow, amount in a.items():
                ratio = 1
                if state and old_state:
                    ratio *= expected_mass_ratio(
                        flow, spec, state
                    ) / expected_mass_ratio(flow, spec, old_state)
                    if (
                        ds["unit"] == "unit"
                        and flow[2] == "electricity storage capacity"
                    ):
                        ratio *= state["capacity kWh"] / old_state["capacity kWh"]
                if is_proxy:
                    if flow[0] == "technosphere" and (
                        (
                            flow[2] == "electricity, low voltage"
                            and flow[4] == "kilowatt hour"
                        )
                        or (
                            flow[4] in {"kilogram", "cubic meter", "megajoule"}
                            and (flow[2] or "").startswith(
                                (
                                    "petrol",
                                    "gasoline",
                                    "diesel",
                                    "natural gas",
                                    "hydrogen",
                                )
                            )
                        )
                    ):
                        ratio *= ratio_energy
                    if flow[0] == "biosphere" and (
                        flow[1]
                        in {"Carbon dioxide, fossil", "Carbon dioxide, non-fossil"}
                        or (
                            flow[1]
                            in {
                                "Sulfur dioxide",
                                "Methane, fossil",
                                "Methane, non-fossil",
                            }
                            and flow[-1] in (("air",), ("air", "unspecified"))
                        )
                    ):
                        ratio *= ratio_energy
                assert close(amount * ratio, b[flow]), (
                    identity,
                    flow,
                    amount * ratio,
                    b[flow],
                )
                if not close(amount, b[flow]):
                    assert year == 2050 and (
                        is_proxy or identity in providers
                    ), identity
                    assert not ds["name"].startswith("market "), identity
                    changed += 1
                    changed_activities.add(identity)
                    changes.append(
                        dict(
                            year=year,
                            name=ds["name"],
                            region=ds["location"],
                            flow=flow[1],
                            before=amount,
                            after=b[flow],
                            ratio=ratio,
                        )
                    )
        assert (proxy_count, carbon_count, hydrogen_count) == (40, 495, 147)
        old_warnings = warning_counts(OLD_OUT / f"validation_{year}.json")
        new_warnings = warning_counts(OUT / f"validation_{year}.json")
        for identity in old_warnings.keys() | new_warnings.keys():
            if old_warnings[identity] != new_warnings[identity]:
                assert year == 2050
                assert identity[0] == "LEGACY.TRANSPORT_HOT_EMISSION_DIAGNOSTIC"
                assert (old_warnings[identity], new_warnings[identity]) == (2, 3)
                warning_changes.append(
                    dict(
                        year=year,
                        rule=identity[0],
                        activity=identity[1],
                        before=old_warnings[identity],
                        after=new_warnings[identity],
                    )
                )
        new_diagnostics = [
            i
            for i in issues(OUT / f"validation_{year}.json")
            if i["rule_id"] == "LEGACY.TRANSPORT_HOT_EMISSION_DIAGNOSTIC"
        ]
        old_diagnostics = [
            i
            for i in issues(OLD_OUT / f"validation_{year}.json")
            if i["rule_id"] == "LEGACY.TRANSPORT_HOT_EMISSION_DIAGNOSTIC"
        ]
        for change in [c for c in warning_changes if c["year"] == year]:

            def matches_co(issue):
                return tuple(issue["activity_key"]) == tuple(
                    change["activity"]
                ) and issue["message"].startswith("Carbon monoxide:")

            assert not any(matches_co(i) for i in old_diagnostics)
            found = [i for i in new_diagnostics if matches_co(i)]
            assert len(found) == 1
            change["diagnostic"] = found[0]["message"]
            change["explanation"] = (
                "Unchanged CO inventory; lower fuel use reduces the energy-based hot-reference denominator."
            )
        assert meta["validation_errors"] == 0
        summaries[str(year)] = dict(
            activities=len(database),
            proxy_services=proxy_count,
            changed_exchanges=changed,
            changed_activities=len(changed_activities),
            all_inventory_differences_explained=True,
            fleet_market_exchanges_unchanged=True,
            carbon_checks=carbon_count,
            hydrogen_checks=hydrogen_count,
            validation_errors=0,
            validation_warnings=meta["validation_warnings"],
            warning_identities_unchanged=old_warnings == new_warnings,
            build_seconds=meta["seconds"],
        )
    suite = ElementTree.parse(WORK / "tests.xml").getroot().find("testsuite")
    assert suite.attrib["errors"] == suite.attrib["failures"] == "0"
    summaries["tests"] = suite.attrib
    write_csv(OUT / "inventory_changes.csv", changes)
    write_csv(OUT / "vehicle_designs.csv", designs)
    (OUT / "warning_changes.json").write_text(
        json.dumps(warning_changes, indent=2) + "\n"
    )
    (OUT / "verification_summary.json").write_text(
        json.dumps(summaries, indent=2) + "\n"
    )
    (OUT / "verification_sources.json").write_text(
        json.dumps(
            {
                "audit_script_sha256": digest(Path(__file__)),
                "tests_xml_sha256": digest(WORK / "tests.xml"),
                "baseline": "premise_vehicle_payload_20261013",
                "tests": {
                    name: digest(SOURCE / "tests" / name)
                    for name in (
                        "test_vehicle_energy_intensities.py",
                        "test_vehicle_emission_scaling.py",
                    )
                },
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
