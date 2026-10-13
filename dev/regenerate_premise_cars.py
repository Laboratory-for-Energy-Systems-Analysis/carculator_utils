"""Regenerate the approved 2020 passenger-car foreground for premise.

Use matched local carculator sources in a Python 3.12 environment. Background
energy belongs to premise; default model fuel energy is conserved when adapting
fuel mass to premise's reference fuels. No Brightway project is modified.
"""

import argparse
import copy
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import openpyxl
import yaml

from audit_premise_vehicle_workbooks import identity, read_workbook, write_csv

COLD_START_SOURCE_NOTE = (
    "the original LCA model, carculator, uses emission factors for cold start, "
    "evaporative and running emissions from the HBEFA 5.1 emissions handbook. "
)


def clean(dataset):
    result = copy.deepcopy(dataset)
    for item in [result, *result["exchanges"]]:
        for field in ("row", "sheet", "workbook", "database", "code", "product"):
            item.pop(field, None)
    return result


def relabel(item, target):
    for field in ("name", "reference product", "location", "unit"):
        item[field] = target[field]


def write_workbook(path, datasets):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "test"
    sheet.append(["Database", "lci-pass_cars"])
    sheet.append([])
    fields = [
        "name",
        "amount",
        "location",
        "unit",
        "categories",
        "type",
        "reference product",
        "comment",
    ]
    for dataset in datasets:
        sheet.append(["Activity", dataset["name"]])
        for key in ("reference product", "location", "unit", "comment"):
            sheet.append([key, dataset.get(key)])
        sheet.append(["production amount", 1])
        sheet.append(["type", "process"])
        sheet.append(["Exchanges"])
        sheet.append(fields)
        for exchange in dataset["exchanges"]:
            sheet.append([exchange.get(field) for field in fields])
        sheet.append([])
    workbook.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--audit", type=Path, default=Path("results/premise_vehicle_audit_20261012")
    )
    parser.add_argument("--reuse-raw", action="store_true")
    parser.add_argument("--starts-per-day", type=float, default=1.8)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    for package in ("carculator_utils", "carculator"):
        sys.path.insert(0, str(root / package))
    args.output.mkdir(parents=True, exist_ok=True)
    recipes = [
        r
        for r in csv.DictReader((args.audit / "candidate_recipes.csv").open())
        if r["family"] == "car" and r["selected_for_2020_update"] == "True"
    ]
    old = {
        d["name"]: d
        for d in json.loads((args.audit / "parsed_inventories.json").read_text())
        if d["workbook"] == "lci-pass_cars.xlsx"
    }
    native = [r for r in recipes if r["status"].startswith("native")]
    raw_path = args.output / "raw.json"
    parameter_path = args.output / "model_parameters.json"
    if not args.reuse_raw:
        from carculator import (
            CarInputParameters,
            CarModel,
            InventoryCar,
            fill_xarray_from_input_parameters,
        )

        inputs = CarInputParameters()
        inputs.static()
        scope = {
            "size": sorted({r["model_size"] for r in native}),
            "powertrain": sorted({r["model_powertrain"] for r in native}),
            "year": [2020],
        }
        _, array = fill_xarray_from_input_parameters(inputs, scope=scope)
        model = CarModel(array, country="CH", starts_per_day=args.starts_per_day)
        model.set_all()
        params = [
            "TtW energy",
            "electricity consumption",
            "fuel consumption",
            "LHV fuel MJ per kg",
            "fuel density per kg",
            "curb mass",
            "driving mass",
            "average passengers",
            "lifetime kilometers",
            "kilometers per year",
            "energy battery mass",
            "electric energy stored",
            "battery lifetime replacements",
            "fuel cell lifetime replacements",
            "range",
        ]
        parameters = {}
        for r in native:
            cell = model.array.sel(
                size=r["model_size"], powertrain=r["model_powertrain"], year=2020
            ).isel(value=0)
            parameters[r["name"]] = {p: float(cell.sel(parameter=p)) for p in params}
            parameters[r["name"]]["starts per day"] = model.starts_per_day
        parameter_path.write_text(json.dumps(parameters, indent=2) + "\n")
        inventory = InventoryCar(model, scenario="static", functional_unit="vkm")
        paths = inventory.export_lci(
            ecoinvent_version="3.12",
            software="brightway2",
            format="file",
            directory=str(args.output / "raw"),
            filename="cars_2020",
        )
        raw = []
        for path in paths if isinstance(paths, list) else [paths]:
            raw.extend(read_workbook(Path(path))[0])
        raw_path.write_text(json.dumps(raw, indent=2) + "\n")
    raw = json.loads(raw_path.read_text())
    parameters = json.loads(parameter_path.read_text())
    assert all(
        p.get("starts per day", 2.3) == args.starts_per_day for p in parameters.values()
    ), "Raw inventories use a different starts-per-day assumption"
    raw_index = {identity(d): d for d in raw}
    raw_names = {d["name"]: d for d in raw}
    powers = yaml.safe_load(
        (
            root
            / "carculator_utils/carculator_utils/data/export/rename_powertrains.yaml"
        ).read_text()
    )
    # kg reference fuel; factors kg CO2/MJ from premise's fuels.yaml and car_energy.py.
    fuels = {
        "petrol": (42.6, 0.0737),
        "diesel": (43.0, 0.0732),
        "methane": (46.5, 0.06),
        "hydrogen": (120.0, 0.0),
        "LPG": (45.5, 0.0631),
    }
    fuel_names = {
        "petrol": "market for petrol, low-sulfur",
        "diesel": "market for diesel, low-sulfur",
        "methane": "market for natural gas, medium pressure, vehicle grade",
        "hydrogen": "market for hydrogen, gaseous",
        "LPG": "market for liquefied petroleum gas",
    }
    datasets, noise, balance = [], [], []
    productions = {}
    for recipe in recipes:
        original = old[recipe["name"]]
        proxy = "liquefied petroleum gas" in recipe["name"]
        size, power = (
            ("Medium", "ICEV-g")
            if proxy
            else (recipe["model_size"], recipe["model_powertrain"])
        )
        source_name = f"transport, car, {powers[power]}, {size}"
        param_name = (
            recipe["name"].replace("liquefied petroleum gas", "compressed gas")
            if proxy
            else recipe["name"]
        )
        par = parameters[param_name]
        ds = clean(raw_names[source_name])
        relabel(ds, original)
        old_production = next(
            e
            for e in original["exchanges"]
            if e["type"] == "technosphere" and e["name"].startswith("Passenger car,")
        )
        production = clean(raw_names[source_name.removeprefix("transport, ")])
        relabel(production, old_production)
        kept = []
        energy, expected_co2 = 0.0, 0.0
        for exc in ds["exchanges"]:
            if exc["unit"] == "joule" and exc["type"] == "biosphere":
                noise.append(
                    dict(vehicle=ds["name"], vehicle_location=ds["location"], **exc)
                )
                continue
            if exc["name"] in ("Carbon dioxide, fossil", "Carbon dioxide, non-fossil"):
                continue
            if (
                proxy
                and exc["name"] in ("Methane, fossil", "Methane, non-fossil")
                and exc.get("categories") == "air"
            ):
                # Generic-air methane is pump-to-tank leakage; compartmented
                # HBEFA combustion methane remains the documented CNG proxy.
                continue
            if exc["type"] == "production":
                relabel(exc, ds)
            elif exc["name"].startswith("car, "):
                relabel(exc, production)
            elif exc["name"].startswith("fuel supply for "):
                family = exc["name"].split()[3]
                if family == "hydrogen":
                    supply = raw_index[identity(exc)]
                    compression = sum(
                        e["amount"]
                        for e in supply["exchanges"]
                        if e["type"] == "technosphere"
                        and e["name"].startswith(
                            "electricity supply for fuel preparation"
                        )
                    )
                    if compression:
                        kept.append(
                            {
                                "name": "market group for electricity, low voltage",
                                "reference product": "electricity, low voltage",
                                "location": "RER",
                                "unit": "kilowatt hour",
                                "type": "technosphere",
                                "amount": exc["amount"] * compression,
                                "comment": f"Default model hydrogen tank compression retained: {compression:.12g} kWh/kg H2, purchased from premise regional electricity.",
                            }
                        )
                fuel = "LPG" if proxy else family
                lhv, co2 = fuels[fuel]
                engine_energy = (
                    par["fuel consumption"]
                    * par["fuel density per kg"]
                    * par["LHV fuel MJ per kg"]
                )
                purchased_energy = exc["amount"] * par["LHV fuel MJ per kg"]
                # The present 2020 defaults have zero pump-to-tank leakage.
                # A changed future default requires explicit carbon handling.
                assert np.isclose(
                    purchased_energy, engine_energy, rtol=1e-6, atol=1e-8
                ), "Nonzero pump-to-tank loss needs a regional methane adapter"
                energy += engine_energy
                target = next(
                    e for e in original["exchanges"] if e["name"] == fuel_names[fuel]
                )
                relabel(exc, target)
                if family == "hydrogen":
                    exc.update(
                        name="market for hydrogen, gaseous, low pressure",
                        **{
                            "reference product": "hydrogen, gaseous, low pressure",
                            "location": "RER",
                        },
                    )
                exc["amount"] = energy / lhv
                expected_co2 += energy * co2
                exc["comment"] = (
                    f"Default carculator fuel energy preserved ({energy:.12g} MJ/vkm); premise reference LHV {lhv} MJ/kg. Regional scenario blend belongs to premise."
                )
            elif exc["name"].startswith("electricity supply for electric vehicles"):
                target = next(
                    e
                    for e in original["exchanges"]
                    if e["name"] == "market group for electricity, low voltage"
                )
                relabel(exc, target)
                exc["comment"] = (
                    "Grid purchase including default charging losses; premise regional electricity supply."
                )
            kept.append(exc)
        if expected_co2:
            kept.append(
                {
                    "name": "Carbon dioxide, fossil",
                    "amount": expected_co2,
                    "unit": "kilogram",
                    "categories": "air",
                    "type": "biosphere",
                    "comment": "Reference fuel full-oxidation CO2; premise reclassifies fossil/biogenic emissions with its regional blend. Other carbon pollutants remain model defaults (not an elemental closure).",
                }
            )
        ds["exchanges"] = kept
        note = (
            f"2020 default vehicle parameters; {args.starts_per_day:g} starts/stops per day "
            f"and {par['kilometers per year']:g} km/year. Swiss climate, default driving cycle. "
            "Daily starts follow Swiss National Inventory Document 2026, Table 3-90 (2020); "
            "cold-start and hot-soak factors are retained. Operating energy and battery supply "
            "adapted to premise. Noise in companion audit. "
        )
        if power not in {"BEV", "FCEV"}:
            note += COLD_START_SOURCE_NOTE
        if proxy:
            note += "LPG proxy: CNG vehicle manufacture INCLUDING CNG tank, efficiency, maintenance and non-CO2 combustion emissions; CNG pump-to-tank methane leakage excluded. LPG-specific LHV and CO2. Raw model fuel commentary describes the CNG proxy. "
        ds["comment"] = note + ds.get("comment", "")
        datasets.append(ds)
        capacity = par["electric energy stored"] * (
            1 + par["battery lifetime replacements"]
        )
        mass = par["energy battery mass"] * (1 + par["battery lifetime replacements"])
        pack_exchanges = [
            e
            for e in production["exchanges"]
            if e["name"].startswith("market for battery, Li-")
        ]
        eol = [
            e
            for e in production["exchanges"]
            if e["name"] == "market for used Li-ion battery"
        ]
        assert np.isclose(
            sum(e["amount"] for e in pack_exchanges), mass, atol=1e-5, rtol=1e-6
        )
        assert np.isclose(-sum(e["amount"] for e in eol), mass, atol=1e-5, rtol=1e-6)
        production["exchanges"] = [
            e for e in production["exchanges"] if e not in pack_exchanges + eol
        ]
        if capacity:
            production["exchanges"].append(
                {
                    "name": "market for battery capacity (MIX scenario)",
                    "reference product": "electricity storage capacity",
                    "location": "GLO",
                    "unit": "kilowatt hour",
                    "type": "technosphere",
                    "amount": capacity,
                    "comment": f"{par['electric energy stored']:.12g} kWh nominal * (1 + {par['battery lifetime replacements']:.12g} lifetime replacements). Capacity market includes battery manufacture AND end of life; original kg pack and disposal removed.",
                }
            )
        for e in production["exchanges"]:
            if e["type"] == "production":
                relabel(e, production)
        production["comment"] = note + production.get("comment", "")
        productions.setdefault(identity(production), production)
        balance.append(
            dict(
                name=ds["name"],
                size=size,
                powertrain=power,
                proxy=proxy,
                fuel_energy_MJ_per_vkm=energy,
                reference_fossil_CO2_kg_per_vkm=expected_co2,
                battery_capacity_with_replacements_kWh=capacity,
                **par,
            )
        )
    datasets.extend(productions.values())
    # Only retain reachable custom components. Distinct names prevent an earlier
    # bus/truck import from silently replacing corrected car component recipes.
    queue = list(datasets)
    auxiliaries = {}
    while queue:
        ds = queue.pop()
        for exc in ds["exchanges"]:
            key = identity(exc)
            if (
                exc["type"] != "technosphere"
                or key not in raw_index
                or key in auxiliaries
            ):
                continue
            assert not exc["name"].startswith(
                ("fuel supply", "electricity supply", "transport, car", "car, ")
            ), (ds["name"], exc)
            aux = clean(raw_index[key])
            auxiliaries[key] = aux
            queue.append(aux)
    for aux in auxiliaries.values():
        aux["name"] += ", carculator passenger car 2020"
    datasets.extend(auxiliaries.values())
    for ds in datasets:
        for exc in ds["exchanges"]:
            key = identity(exc)
            if key in auxiliaries:
                relabel(exc, auxiliaries[key])
            assert np.isfinite(exc["amount"])
        assert sum(e["type"] == "production" for e in ds["exchanges"]) == 1
        assert identity(
            next(e for e in ds["exchanges"] if e["type"] == "production")
        ) == identity(ds)
    assert len({identity(d) for d in datasets}) == len(datasets)
    path = args.output / "lci-pass_cars.xlsx"
    write_workbook(path, datasets)
    (args.output / "adapted.json").write_text(json.dumps(datasets, indent=2) + "\n")
    write_csv(args.output / "noise_audit.csv", noise)
    write_csv(args.output / "vehicle_parameters.csv", balance)
    record = dict(
        cng_supply_basis={
            "delivered_LHV_MJ_per_kg": 46.5,
            "source": "ecoinvent vehicle-grade natural gas market comment",
            "policy": "Preserve model energy and source compression recipe; upstream gas energy is not delivered LHV",
            "approved_on": "2026-10-13",
        },
        year=2020,
        country="CH",
        starts_per_day=args.starts_per_day,
        annual_mileage_policy="Unchanged 2020 defaults: combustion cars 12000 km/year; BEV Micro 6000 km/year.",
        starts_source="https://www.bafu.admin.ch/dam/en/sd-web/rMTT3CcvG0fJ/Switzerland%27s%20National%20Inventory%20Document%202026%20%28GHG%20inventory%201990-2024%29.pdf#page=167",
        starts_source_locator="Table 3-90, passenger cars, 2020 column; selected by user 2026-10-13",
        cold_start_factors_source={
            "database": "HBEFA",
            "version": "5.1",
            "model": "carculator",
            "reference": COLD_START_SOURCE_NOTE.strip(),
            "confirmed_on": "2026-10-13",
            "scope": "Passenger-car cold-start, evaporative and running emission factors; no coefficient changes.",
        },
        transport_count=len(recipes),
        production_count=len(productions),
        auxiliaries=[d["name"] for d in auxiliaries.values()],
        noise_exchanges=len(noise),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        export_version="3.12",
        commits={
            p: subprocess.check_output(
                ["git", "-C", str(root / p), "rev-parse", "HEAD"], text=True
            ).strip()
            for p in ("carculator", "carculator_utils", "premise")
        },
        source_sha256={
            filename: hashlib.sha256((root / filename).read_bytes()).hexdigest()
            for filename in (
                "carculator_utils/carculator_utils/hot_emissions.py",
                "carculator_utils/carculator_utils/data/emission_factors/provenance.json",
                "carculator_utils/dev/regenerate_premise_cars.py",
            )
        },
    )
    (args.output / "provenance.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
