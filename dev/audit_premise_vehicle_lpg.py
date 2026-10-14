"""Independently check LPG coverage and unchanged full-build inventories."""

import json
import math
from pathlib import Path
from xml.etree import ElementTree

from audit_premise_vehicle_battery import warning_counts
from audit_premise_vehicle_carbon import co2, coefficients, key, write_csv
from audit_premise_vehicle_payload import digest, load_database

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "premise"
WORK = Path("/private/tmp/premise-vehicle-lpg-20261014")
BEFORE = Path("/private/tmp/premise-large-car-proxy-20261013")
OUT = ROOT / "results/premise_vehicle_lpg_20261014"
OLD_OUT = ROOT / "results/premise_large_car_proxy_20261013"
SPEC = "vehicle lpg policy"
STATE = "premise vehicle LPG supply"
LPG = "liquefied petroleum gas"


def main():
    installation = json.loads((OUT / "installation.json").read_text())
    installed = {r["filename"]: r for r in installation["files"]}
    for name, value in installation["generator_sources"].items():
        assert digest(ROOT / "dev" / name) == value, name
    assert (
        digest(ROOT / "dev/install_premise_lpg_metadata.py")
        == installation["installer_sha256"]
    )
    summaries, rows = {}, []
    prior_lpg = None
    for year in (2020, 2050):
        meta = json.loads((OUT / f"build_{year}.json").read_text())
        old_meta = json.loads((OLD_OUT / f"build_{year}.json").read_text())
        for field in (
            "iam_files",
            "fuel_properties_sha256",
            "transport_mapping_sources",
            "activities",
            "exchanges",
        ):
            assert meta[field] == old_meta[field], field
        assert meta["encrypted_iam"] and not meta["persistent_user_database_written"]
        assert meta["source_database"] == "ecoinvent-3.12-cutoff"
        assert meta["scenario"] == dict(model="remind", pathway="SSP2-NPi", year=year)
        assert meta["workbooks"].keys() == old_meta["workbooks"].keys()
        for name, value in meta["workbooks"].items():
            if name in installed:
                assert value == installed[name]["after_sha256"]
                assert old_meta["workbooks"][name] == installed[name]["before_sha256"]
            else:
                assert value == old_meta["workbooks"][name], name
            assert (
                digest(SOURCE / "premise/data/additional_inventories" / name) == value
            )
        for section in ("python_sources", "transport_mapping_sources"):
            for path, value in meta[section].items():
                assert digest(SOURCE / path) == value, path
        assert {
            k
            for k, v in meta["python_sources"].items()
            if v != old_meta["python_sources"].get(k)
        } == {
            "premise/fuels/carbon.py",
            "premise/transport.py",
            "premise/validation.py",
            "premise/vehicle_lpg.py",
        }
        database = load_database(WORK, year, meta)
        baseline = load_database(BEFORE, year, old_meta)
        assert database.keys() == baseline.keys()
        lpg_services, checked_coefficients = {}, 0
        roundoff_count, max_absolute_delta, max_relative_delta = 0, 0.0, 0.0
        for identity, ds in database.items():
            old = baseline[identity]
            a, b = coefficients(old), coefficients(ds)
            assert a.keys() == b.keys(), identity
            for flow, amount in a.items():
                # Whole-build summation order causes machine-precision differences.
                assert math.isclose(amount, b[flow], rel_tol=1e-12, abs_tol=1e-18), (
                    identity,
                    flow,
                    amount,
                    b[flow],
                )
                if amount != b[flow]:
                    roundoff_count += 1
                    delta = abs(amount - b[flow])
                    max_absolute_delta = max(max_absolute_delta, delta)
                    max_relative_delta = max(
                        max_relative_delta, delta / max(abs(amount), abs(b[flow]))
                    )
            checked_coefficients += len(b)
            if SPEC not in ds:
                assert STATE not in ds, identity
                continue
            assert a == b, identity  # Strict equality for all five LPG services.
            spec = json.loads(ds[SPEC]) if isinstance(ds[SPEC], str) else ds[SPEC]
            state = ds[STATE]
            assert state["status"] == "resolved", identity
            assert state["year"] == year and state["baseline year"] == 2020
            assert state["LPG efficiency mapping"] == "unavailable"
            assert state["applied energy factor"] == 1
            assert state["supply mode"] == "fossil fallback"
            assert ds["location"] == state["vehicle location"] == "RER"
            assert state["CNG pump-to-tank methane leakage"] == "excluded"
            assert "CNG manufacture including tank" in state["proxy boundary"]
            fuel = [
                e
                for e in ds["exchanges"]
                if e["type"] == "technosphere" and e.get("product") == LPG
            ]
            assert len(fuel) == len(state["suppliers"]) == 1
            exc, supplier = fuel[0], state["suppliers"][0]
            assert key(exc) == (
                f"market for {LPG}",
                LPG,
                "Europe without Switzerland",
                "kilogram",
            )
            assert key(exc) in database
            assert key(supplier) == key(exc)
            assert supplier["amount"] == exc["amount"]
            assert supplier["energy MJ per unit"] == 45.5
            assert "premise fuel properties" not in database[key(exc)]
            output = sum(
                e["amount"] for e in ds["exchanges"] if e["type"] == "production"
            )
            amount = exc["amount"] / output
            assert amount == spec["fuel kg per service"]
            energy = amount * 45.5
            fossil, biogenic = (a / output for a in co2(ds))
            assert math.isclose(fossil, energy * 0.0631, rel_tol=1e-12)
            assert biogenic == state["non-fossil CO2 kg per service"] == 0
            assert energy == state["energy MJ per service"]
            assert fossil == state["fossil CO2 kg per service"]
            assert "Europe without Switzerland" in ds["comment"]
            assert "No scenario LPG blend" in ds["comment"]
            assert "2020 operating energy retained" in ds["comment"]
            assert (
                "Operating fuel blends and electricity supplied by Premise regional scenario markets."
                not in ds["comment"]
            )
            assert ds["comment"].count("LPG supply (") == 1
            for e in ds["exchanges"]:
                if (
                    e["type"] == "biosphere"
                    and e["name"] in {"Methane, fossil", "Methane, non-fossil"}
                    and tuple(e.get("categories", ()))
                    in {("air",), ("air", "unspecified")}
                ):
                    assert e["amount"] == 0
            vehicles = [
                e
                for e in ds["exchanges"]
                if e["type"] == "technosphere"
                and e["unit"] == "unit"
                and e["name"]
                .lower()
                .startswith(("passenger car,", "lorry production,"))
            ]
            assert len(vehicles) == 1 and "compressed gas" in vehicles[0]["name"]
            assert key(vehicles[0]) in database
            assert coefficients(database[key(vehicles[0])]) == coefficients(
                baseline[key(vehicles[0])]
            )
            lpg_services[identity] = (
                amount,
                energy,
                fossil,
                biogenic,
                key(vehicles[0]),
            )
            rows.append(
                dict(
                    year=year,
                    name=ds["name"],
                    location=ds["location"],
                    unit=ds["unit"],
                    fuel_supplier=exc["name"],
                    fuel_location=exc["location"],
                    fuel_kg_per_service=amount,
                    energy_MJ_per_service=energy,
                    fossil_CO2_kg_per_service=fossil,
                    biogenic_CO2_kg_per_service=biogenic,
                    efficiency_factor=1,
                    LPG_efficiency_mapping="unavailable",
                    scenario_fuel_blend=False,
                    manufacture_proxy=vehicles[0]["name"],
                    manufacture_proxy_location=vehicles[0]["location"],
                    CNG_leakage_excluded=True,
                )
            )
        assert len(lpg_services) == 5
        if prior_lpg is not None:
            assert lpg_services == prior_lpg
        prior_lpg = lpg_services
        assert warning_counts(OUT / f"validation_{year}.json") == warning_counts(
            OLD_OUT / f"validation_{year}.json"
        )
        assert meta["validation_errors"] == 0
        summaries[str(year)] = dict(
            activities=len(database),
            exchanges=meta["exchanges"],
            compared_coefficients=checked_coefficients,
            activity_identities_unchanged=True,
            changed_coefficients=0,
            coefficient_relative_tolerance=1e-12,
            coefficient_absolute_tolerance=1e-18,
            floating_point_differences=roundoff_count,
            max_absolute_difference=max_absolute_delta,
            max_relative_difference=max_relative_delta,
            lpg_coefficients_exactly_unchanged=True,
            lpg_services=len(lpg_services),
            validation_errors=0,
            validation_warnings=meta["validation_warnings"],
            warning_identities_unchanged=True,
            build_seconds=meta["seconds"],
        )
    suite = ElementTree.parse(WORK / "tests.xml").getroot().find("testsuite")
    assert suite.attrib["errors"] == suite.attrib["failures"] == "0"
    summaries["tests"] = suite.attrib
    summaries["lpg_2020_2050_quantities_identical"] = True
    write_csv(OUT / "lpg_coverage.csv", rows)
    (OUT / "verification_summary.json").write_text(
        json.dumps(summaries, indent=2) + "\n"
    )
    (OUT / "verification_sources.json").write_text(
        json.dumps(
            dict(
                baseline="premise_large_car_proxy_20261013",
                audit_script_sha256=digest(Path(__file__)),
                tests_xml_sha256=digest(WORK / "tests.xml"),
                test_lpg_sha256=digest(SOURCE / "tests/test_vehicle_lpg.py"),
                installation_sha256=digest(OUT / "installation.json"),
            ),
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
