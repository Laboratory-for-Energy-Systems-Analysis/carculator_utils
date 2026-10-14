"""Check metadata restoration, adapter reproducibility and both full inventories."""

import json
import math
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

from audit_premise_vehicle_battery import warning_counts
from audit_premise_vehicle_carbon import coefficients, write_csv
from audit_premise_vehicle_payload import digest, load_database
from audit_premise_vehicle_workbooks import identity, read_workbook

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "premise"
WORK = Path("/private/tmp/premise-vehicle-provenance-20261014")
BEFORE = Path("/private/tmp/premise-vehicle-lpg-20261014")
OUT = ROOT / "results/premise_vehicle_provenance_20261014"
OLD_OUT = ROOT / "results/premise_vehicle_lpg_20261014"
INVENTORIES = SOURCE / "premise/data/additional_inventories"
SPEC, STATE = "vehicle inventory provenance", "premise vehicle provenance"


def workbook_coefficients(ds):
    return coefficients(
        {
            "exchanges": [
                dict(
                    e,
                    product=e.get("reference product"),
                    categories=(e.get("categories") or "").split("::"),
                )
                for e in ds["exchanges"]
            ]
        }
    )


def main():
    installation = json.loads((OUT / "installation.json").read_text())
    files = {r["filename"]: r for r in installation["files"]}
    for name, value in installation["source_files"].items():
        assert digest(ROOT / "dev" / name) == value, name
    for name, record in installation["companions"].items():
        assert digest(INVENTORIES / name) == record["after_sha256"], name
    workbook_rows, adapters = [], []
    for family, folder, filename in (
        ("car", "cars", "lci-pass_cars.xlsx"),
        ("truck", "trucks", "lci-trucks.xlsx"),
        ("legacy", "trucks", "lci-truck-legacy-components.xlsx"),
    ):
        current = {identity(d): d for d in read_workbook(INVENTORIES / filename)[0]}
        old = {identity(d): d for d in read_workbook(WORK / "before" / filename)[0]}
        adapter = {
            identity(d): d
            for d in read_workbook(WORK / "adapter-check" / folder / filename)[0]
        }
        assert current.keys() == old.keys() == adapter.keys()
        for key, ds in current.items():
            assert (
                workbook_coefficients(ds)
                == workbook_coefficients(old[key])
                == workbook_coefficients(adapter[key])
            ), key
            assert ds["source"] == adapter[key]["source"]
            assert ds["database"] == adapter[key]["database"] == Path(filename).stem
            spec = (
                json.loads(ds[SPEC])
                if family != "legacy"
                else json.loads(ds["inventory provenance"])
            )
            if family != "legacy":
                assert ds["model"] == spec["original model"]
                assert "Model publication:" in ds["comment"]
                assert spec["baseline identity"] == dict(
                    zip(("name", "reference product", "location", "unit"), key)
                )
                role = spec["role"]
                if family == "car" and spec.get("model powertrain", "").startswith(
                    ("ICEV", "HEV", "PHEV")
                ):
                    assert (
                        "the original LCA model, carculator, uses emission factors for cold start, evaporative and running emissions from the HBEFA 5.1 emissions handbook"
                        in ds["comment"]
                    )
                if role == "bundled component":
                    assert "baseline vehicle parameters" not in spec
            else:
                role = "retained legacy component"
                assert SPEC not in ds and "model publication" not in ds
            workbook_rows.append(
                dict(
                    workbook=filename,
                    name=ds["name"],
                    location=ds["location"],
                    role=role,
                    source=ds["source"],
                    model=ds.get("model", "not newly generated"),
                )
            )
        adapters.append(
            dict(
                family=family,
                activities=len(current),
                all_coefficients_exactly_unchanged=True,
                restored_sources_match_adapter=True,
                database_label=Path(filename).stem,
            )
        )
    summaries = {"workbooks_and_adapters": adapters}
    for year in (2020, 2050):
        meta = json.loads((OUT / f"build_{year}.json").read_text())
        prior = json.loads((OLD_OUT / f"build_{year}.json").read_text())
        saved = json.loads((OUT / f"saved_{year}.json").read_text())
        for field in (
            "iam_files",
            "transport_mapping_sources",
            "fuel_properties_sha256",
            "activities",
            "exchanges",
        ):
            assert meta[field] == prior[field], field
        assert {
            p
            for p, h in meta["python_sources"].items()
            if prior["python_sources"].get(p) != h
        } == {"premise/transport.py", "premise/vehicle_provenance.py"}
        for name, value in meta["python_sources"].items():
            assert digest(SOURCE / name) == value, name
        for name, value in meta["workbooks"].items():
            assert digest(INVENTORIES / name) == value, name
            if name in files:
                assert (
                    value == files[name]["after_sha256"]
                    and prior["workbooks"][name] == files[name]["before_sha256"]
                )
            else:
                assert value == prior["workbooks"][name]
        database, baseline = load_database(WORK, year, meta), load_database(
            BEFORE, year, prior
        )
        assert database.keys() == baseline.keys()
        roles, rounding, checked = Counter(), 0, 0
        for key, ds in database.items():
            a, b = coefficients(baseline[key]), coefficients(ds)
            assert a.keys() == b.keys(), key
            for flow, value in a.items():
                assert math.isclose(value, b[flow], rel_tol=1e-12, abs_tol=1e-18), (
                    key,
                    flow,
                )
                rounding += int(value != b[flow])
            checked += len(a)
            if SPEC in ds:
                spec = json.loads(ds[SPEC]) if isinstance(ds[SPEC], str) else ds[SPEC]
                state = ds[STATE]
                assert (
                    state["scenario year"] == year
                    and state["baseline model year"] == 2020
                )
                assert state["location"] == ds["location"]
                assert ds["source"] == spec["activity source"]
                if state["role"] == "forwarding service":
                    assert not state["operating energy inputs"]
                    assert "scenario battery specifications" not in state
                else:
                    assert state.get("scenario battery specifications") == ds.get(
                        "premise vehicle battery sizing"
                    )
                roles[state["role"]] += 1
            elif "inventory provenance" in ds:
                roles["retained legacy component"] += 1
                assert STATE not in ds
        assert sum(roles.values()) == saved["metadata_activities"]
        assert saved["metadata_exactly_preserved"]
        assert meta["validation_errors"] == 0
        assert warning_counts(OUT / f"validation_{year}.json") == warning_counts(
            OLD_OUT / f"validation_{year}.json"
        )
        summaries[str(year)] = dict(
            activities=len(database),
            compared_coefficients=checked,
            material_coefficient_changes=0,
            floating_point_differences=rounding,
            relative_tolerance=1e-12,
            absolute_tolerance=1e-18,
            provenance_roles=dict(roles),
            validation_errors=0,
            validation_warnings=meta["validation_warnings"],
            warning_identities_unchanged=True,
            saved_metadata_activities=saved["metadata_activities"],
            saved_energy_link_checks=saved["operating_energy_links_checked"],
        )
    suite = ElementTree.parse(WORK / "tests.xml").getroot().find("testsuite")
    assert suite.attrib["failures"] == suite.attrib["errors"] == "0"
    summaries["tests"] = suite.attrib
    adapter_suite = (
        ElementTree.parse(WORK / "adapter-tests.xml").getroot().find("testsuite")
    )
    assert adapter_suite.attrib["failures"] == adapter_suite.attrib["errors"] == "0"
    summaries["adapter_tests"] = adapter_suite.attrib
    write_csv(OUT / "workbook_sources.csv", workbook_rows)
    (OUT / "verification_summary.json").write_text(
        json.dumps(summaries, indent=2) + "\n"
    )
    (OUT / "verification_sources.json").write_text(
        json.dumps(
            dict(
                audit_script_sha256=digest(Path(__file__)),
                saved_check_sha256=digest(
                    ROOT / "dev/verify_premise_vehicle_provenance.py"
                ),
                tests_xml_sha256=digest(WORK / "tests.xml"),
                baseline="premise_vehicle_lpg_20261014",
            ),
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
