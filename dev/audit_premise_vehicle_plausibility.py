"""Audit fresh exports and the final 2020/2050 Premise car/truck inventories.

Uses private build pickles, verified against their recorded hashes. Failing
accounting checks raise; scientific concerns are recorded separately, not fixed
by clipping inventories. Run with the Premise Python 3.12 environment.
"""

import argparse
import csv
import json
import math
import pickle
from collections import Counter
from pathlib import Path

import yaml

from audit_premise_vehicle_carbon import co2, key, write_csv
from audit_premise_vehicle_payload import digest
from audit_premise_vehicle_provenance import workbook_coefficients
from audit_premise_vehicle_workbooks import identity, read_workbook

ROOT = Path(__file__).resolve().parents[1]
INVENTORIES = ROOT.parent / "premise/premise/data/additional_inventories"
BUILD = ROOT / "results/premise_vehicle_provenance_20261014"
WORK = Path("/private/tmp/premise-vehicle-provenance-20261014")
SPEC, STATE = "vehicle battery sizing", "premise vehicle battery sizing"
PROVENANCE = "vehicle inventory provenance"
DIRECT = ("Carbon monoxide, fossil", "Nitrogen oxides", "Particulate Matter, < 2.5 um")


def close(a, b, context):
    assert math.isclose(a, b, rel_tol=4e-6, abs_tol=1e-12), (context, a, b)


def structured(value):
    return json.loads(value) if isinstance(value, str) else value


def total(ds, name):
    return sum(
        e["amount"]
        for e in ds["exchanges"]
        if e["type"] == "biosphere" and e["name"] == name
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=WORK)
    parser.add_argument("--build-records", type=Path, default=BUILD)
    parser.add_argument(
        "--allow-fuel-mismatch",
        action="store_true",
        help="Record historical fuel-energy failures for review instead of raising.",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    templates, parameters, catalogue, reproduction = {}, {}, [], []
    gains = yaml.safe_load(
        (
            ROOT.parent
            / "premise/premise/data/GAINS_emission_factors/GAINS_ei_pollutants.yaml"
        ).read_text()
    )
    for family, folder, label in (
        ("car", "cars", "pass_cars"),
        ("truck", "trucks", "trucks"),
    ):
        filename = f"lci-{label}.xlsx"
        generated_path = args.generation / folder / filename
        fresh = {identity(d): d for d in read_workbook(generated_path)[0]}
        current = {identity(d): d for d in read_workbook(INVENTORIES / filename)[0]}
        assert current.keys() == fresh.keys()
        for ident, ds in current.items():
            a, b = workbook_coefficients(ds), workbook_coefficients(fresh[ident])
            assert a.keys() == b.keys(), ident
            for flow, value in a.items():
                close(value, b[flow], (ident, flow))
        with (args.generation / folder / "vehicle_parameters.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            name = row["name"]
            parameters[name] = row
            templates[name] = next(d for d in current.values() if d["name"] == name)
            num = lambda field: float(row[field])
            for field in (
                "curb mass",
                "driving mass",
                "lifetime kilometers",
                "kilometers per year",
                "TtW energy",
            ):
                assert math.isfinite(num(field)) and num(field) > 0, (name, field)
            capacity, mass = num("electric energy stored"), num("energy battery mass")
            if mass > 0:
                close(
                    capacity,
                    num("battery cell mass") * num("battery cell energy density"),
                    name,
                )
                close(mass, num("battery cell mass") + num("battery BoP mass"), name)
            close(
                num("battery_capacity_with_replacements_kWh"),
                capacity * (1 + num("battery lifetime replacements")),
                name,
            )
            cargo = num("cargo mass") if family == "truck" else 0
            if family == "truck":
                assert 0 < cargo <= num("available payload")
                assert num("driving mass") <= num("gross mass")
                close(
                    num("available payload"),
                    num("gross mass") - num("driving mass") + cargo,
                    name,
                )
            # The model's consumption field is volume, including gases at the
            # model density; convert to mass before interpreting kg/100 km.
            fuel_kg = num("fuel consumption") * num("fuel density per kg")
            catalogue.append(
                dict(
                    family=family,
                    name=name,
                    size=row["size"],
                    powertrain=row["powertrain"],
                    proxy=row["proxy"],
                    capacity_kWh=capacity,
                    pack_mass_kg=mass,
                    curb_mass_kg=num("curb mass"),
                    driving_mass_kg=num("driving mass"),
                    cargo_kg=cargo,
                    electricity_kWh_per_100km=100 * num("electricity consumption"),
                    model_fuel_kg_per_100km=100 * fuel_kg,
                    model_fuel_MJ_per_km=fuel_kg * num("LHV fuel MJ per kg"),
                    lifetime_km=num("lifetime kilometers"),
                    replacements=num("battery lifetime replacements"),
                )
            )
        reproduction.append(
            dict(
                family=family,
                activities=len(current),
                services=len(rows),
                installed_sha256=digest(INVENTORIES / filename),
                freshly_generated_sha256=digest(generated_path),
                coefficients_reproduced=True,
            )
        )
    designs, counts, fuel_rows, fuel_checks = [], {}, [], []
    for year in (2020, 2050):
        meta = json.loads((args.build_records / f"build_{year}.json").read_text())
        path = args.workspace / str(year) / "database.pickle"
        assert digest(path) == meta["private_inventory_sha256"]
        with path.open("rb") as stream:
            index = {key(d): d for d in pickle.load(stream)}
        checked = Counter()
        for ds in index.values():
            if PROVENANCE not in ds or ds["unit"] not in {"kilometer", "ton kilometer"}:
                continue
            provenance = structured(ds[PROVENANCE])
            name = provenance["baseline identity"]["name"]
            par, template = parameters[name], templates[name]
            family = provenance["family"]
            if ds.get("emptied"):
                checked["forwarders_excluded_from_direct_checks"] += 1
                continue
            checked["operating_services"] += 1
            output = sum(
                e["amount"] for e in ds["exchanges"] if e["type"] == "production"
            )
            assert math.isfinite(output) and output > 0
            assert all(math.isfinite(e["amount"]) for e in ds["exchanges"])
            state = ds.get(STATE)
            spec = structured(ds.get(SPEC))
            cargo = (state or {}).get(
                "cargo mass kg", float(par.get("cargo mass", 1000))
            )
            load = cargo / 1000 if family == "truck" else 1
            base_load = (
                float(par.get("cargo mass", 1000)) / 1000 if family == "truck" else 1
            )
            normalization = base_load / load
            vehicles = [
                e
                for e in ds["exchanges"]
                if e["type"] == "technosphere"
                and e["unit"] == "unit"
                and e["name"]
                .lower()
                .startswith(("passenger car,", "lorry production,"))
            ]
            assert len(vehicles) == 1, key(ds)
            close(
                vehicles[0]["amount"] / output,
                1 / (float(par["lifetime kilometers"]) * load),
                key(ds),
            )
            provider = index[key(vehicles[0])]
            batteries = [
                e
                for e in provider["exchanges"]
                if e["type"] == "technosphere"
                and e.get("product") == "electricity storage capacity"
            ]
            capacity = (state or {}).get(
                "capacity kWh", float(par["electric energy stored"])
            )
            replacements = float(par["battery lifetime replacements"])
            if capacity > 0:
                assert len(batteries) == 1, key(ds)
                close(batteries[0]["amount"], capacity * (1 + replacements), key(ds))
                checked["battery_allocation"] += 1
            final = ds["premise vehicle provenance"]
            factor = final.get("IAM energy multiplier", 1) * final.get(
                "car energy floor multiplier", 1
            )
            grid = fuel_energy = 0
            expected_co2 = [0, 0]
            fuel_count = 0
            for e in final["operating energy inputs"]:
                assert e["amount"] >= 0 and key(e) in index
                if e["product"] == "electricity, low voltage":
                    grid += e["amount"]
                    continue
                fuel_count += 1
                supplier = index[key(e)]
                properties = supplier.get("premise fuel properties")
                if properties:
                    assert properties["unresolved CO2 kg per unit"] == 0
                    energy = properties["energy MJ per unit"]
                    carbon = [
                        properties[f"{origin} CO2 kg per unit"]
                        for origin in ("fossil", "non-fossil")
                    ]
                elif e["product"] == "liquefied petroleum gas":
                    energy, carbon = 45.5, [45.5 * 0.0631, 0]
                else:
                    raise AssertionError((key(ds), e))
                fuel_energy += e["amount"] * energy
                for j in (0, 1):
                    expected_co2[j] += e["amount"] * carbon[j]
                fuel_rows.append(
                    dict(
                        year=year,
                        name=ds["name"],
                        location=ds["location"],
                        supplier=e["name"],
                        supplier_location=e["location"],
                        unit=e["unit"],
                        amount_per_service=e["amount"],
                        delivered_MJ_per_unit=energy,
                    )
                )
            if fuel_count:
                energy_field = (
                    "fuel_energy_MJ_per_vkm"
                    if family == "car"
                    else "fuel_energy_MJ_per_tkm"
                )
                expected_energy = float(par[energy_field]) * factor * normalization
                fuel_checks.append(
                    dict(
                        year=year,
                        name=ds["name"],
                        location=ds["location"],
                        delivered_MJ_per_service=fuel_energy,
                        expected_MJ_per_service=expected_energy,
                        passed=math.isclose(
                            fuel_energy, expected_energy, rel_tol=4e-6, abs_tol=1e-12
                        ),
                    )
                )
                for actual, expected in zip(co2(ds), expected_co2):
                    close(actual / output, expected, key(ds))
                checked["fuel_energy_and_carbon"] += 1
            # Exhaust PM only: abrasion is in separate component activities.
            for substance in DIRECT:
                gains_factor = ds.get("log parameters", {}).get(gains.get(substance), 1)
                close(
                    total(ds, substance) / output,
                    total(template, substance) * normalization * gains_factor,
                    (key(ds), substance),
                )
            if state:
                checked["resized_battery"] += 1
                close(capacity, spec["capacity kWh"] * factor, key(ds))
                close(
                    state["pack mass kg"],
                    state["cell mass kg"] + state["balance of pack mass kg"],
                    key(ds),
                )
                close(
                    capacity,
                    state["cell mass kg"] * state["cell density kWh/kg"],
                    key(ds),
                )
                close(
                    state["curb mass kg"] - state["pack mass kg"],
                    spec["curb mass kg"] - spec["pack mass kg"],
                    key(ds),
                )
                electric_range = (
                    capacity
                    * spec["depth of discharge"]
                    / (
                        grid
                        * load
                        / spec["electric share"]
                        * spec["charge efficiency"]
                        * spec["charger efficiency"]
                    )
                )
                close(electric_range, spec["electric range km"], key(ds))
                if family == "truck":
                    driver = (
                        spec["driving mass kg"]
                        - spec["curb mass kg"]
                        - spec["cargo mass kg"]
                    )
                    close(
                        state["driving mass kg"],
                        state["curb mass kg"] + driver + cargo,
                        key(ds),
                    )
                    assert state["driving mass kg"] <= spec["gross mass kg"]
                    if par["powertrain"] == "BEV":
                        close(
                            cargo / state["available payload kg"],
                            spec["cargo mass kg"]
                            / (spec["gross mass kg"] - spec["curb mass kg"] - driver),
                            key(ds),
                        )
                designs.append(
                    dict(
                        year=year,
                        family=family,
                        name=ds["name"],
                        location=ds["location"],
                        capacity_kWh=capacity,
                        pack_mass_kg=state["pack mass kg"],
                        curb_mass_kg=state["curb mass kg"],
                        driving_mass_kg=state["driving mass kg"],
                        cargo_kg=cargo if family == "truck" else None,
                        electric_range_km=electric_range,
                        grid_kWh_per_vkm=grid * load,
                        vehicle_input_per_service=vehicles[0]["amount"] / output,
                    )
                )
        counts[year] = dict(checked)
    write_csv(args.output / "fresh_export_checks.csv", reproduction)
    write_csv(args.output / "baseline_catalogue.csv", catalogue)
    write_csv(args.output / "scenario_designs.csv", designs)
    write_csv(args.output / "final_fuel_inputs.csv", fuel_rows)
    write_csv(args.output / "fuel_energy_checks.csv", fuel_checks)
    counts["fuel_energy_failures"] = sum(not r["passed"] for r in fuel_checks)
    (args.output / "accounting_summary.json").write_text(
        json.dumps(counts, indent=2) + "\n"
    )
    print(json.dumps(counts, indent=2))
    if not args.allow_fuel_mismatch:
        assert counts["fuel_energy_failures"] == 0, "Fuel-energy regression detected"


if __name__ == "__main__":
    main()
