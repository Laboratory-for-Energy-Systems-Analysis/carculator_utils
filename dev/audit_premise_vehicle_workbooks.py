"""Read premise's vehicle workbooks without modifying them or a Brightway project.

Run with Python 3.12 and openpyxl/PyYAML. Excel formulas are read twice so that
both their cached results and missing calculation caches can be audited.
"""

import argparse
import csv
import hashlib
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
import yaml

WORKBOOKS = {
    "car": ("lci-pass_cars.xlsx", "transport_passenger_cars.yaml"),
    "bus": ("lci-buses.xlsx", "transport_bus.yaml"),
    "truck": ("lci-trucks.xlsx", "transport_road_freight.yaml"),
    "two-wheeler": ("lci-two_wheelers.xlsx", "transport_two_wheelers.yaml"),
}


def read_workbook(path):
    """Parse Activity/Exchanges blocks, respecting sheet-level skip markers."""
    cached = openpyxl.load_workbook(path, read_only=True, data_only=True)
    formulas = openpyxl.load_workbook(path, read_only=True, data_only=False)
    datasets, sheets, missing_caches = [], [], []
    for sheet in cached:
        rows = list(sheet.values)
        skipped = bool(rows and str(rows[0][0]).lower() == "skip")
        count = 0
        for formula_row, value_row in zip(formulas[sheet.title], rows):
            for cell, value in zip(formula_row, value_row):
                if cell.data_type == "f":
                    count += 1
                    if value is None:
                        missing_caches.append(f"{sheet.title}!{cell.coordinate}")
        sheets.append(
            dict(name=sheet.title, skipped=skipped, rows=len(rows), formulas=count)
        )
        if skipped:
            continue
        dataset, headers, exchanges = None, None, False
        database = None
        for number, row in enumerate(rows, 1):
            key = str(row[0]).strip().lower() if row[0] is not None else ""
            if key == "database":
                database = row[1]
            elif key == "activity":
                dataset = dict(
                    workbook=path.name,
                    sheet=sheet.title,
                    row=number,
                    database=database,
                    name=row[1],
                    exchanges=[],
                )
                datasets.append(dataset)
                headers, exchanges = None, False
            elif dataset is None:
                continue
            elif key == "exchanges":
                exchanges = True
            elif exchanges and key == "name":
                headers = [str(c).lower().strip() if c else None for c in row]
            elif exchanges and headers and key:
                exchange = {k: v for k, v in zip(headers, row) if k}
                exchange["row"] = number
                dataset["exchanges"].append(exchange)
            elif key and not exchanges:
                dataset[key] = row[1]
    cached.close()
    formulas.close()
    return datasets, sheets, missing_caches


def identity(dataset):
    return tuple(
        (
            (dataset.get(key) or dataset.get("product"))
            if key == "reference product"
            else dataset.get(key)
        )
        for key in ("name", "reference product", "location", "unit")
    )


def write_csv(path, records):
    columns = list(dict.fromkeys(key for record in records for key in record))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    key: json.dumps(value) if isinstance(value, (dict, list)) else value
                    for key, value in record.items()
                }
            )


def matches(name, aliases):
    """Evaluate the string name filters used in these four mapping files."""
    filters, masks = aliases.get("fltr", []), aliases.get("mask", [])
    if isinstance(filters, str):
        filters = [filters]
    if isinstance(masks, str):
        masks = [masks]
    if not isinstance(filters, list) or not isinstance(masks, list):
        raise ValueError(f"Unsupported mapping filter: {aliases}")
    return any(f.lower() in name.lower() for f in filters) and not any(
        m.lower() in name.lower() for m in masks
    )


def candidate_recipe(dataset):
    """Map identities to candidates, retaining only the requested 2020 classes."""
    family, name = dataset["family"], dataset["name"]
    result = {
        "family": family,
        "name": name,
        "reference product": dataset.get("reference product"),
        "location": dataset.get("location"),
        "unit": dataset.get("unit"),
        "sheet": dataset["sheet"],
        "row": dataset["row"],
        "status": "native candidate; operating assumptions require confirmation",
        "model_size": "",
        "model_powertrain": "",
        "candidate_year": 2020,
        "year_evidence": "proposed 2020 IAM reference; original year undocumented",
    }
    parts = name.split(", ")
    powers = {
        "gasoline": "ICEV-p",
        "diesel": "ICEV-d",
        "compressed gas": "ICEV-g",
        "gasoline hybrid": "HEV-p",
        "diesel hybrid": "HEV-d",
        "plugin gasoline hybrid": "PHEV-p",
        "plugin diesel hybrid": "PHEV-d",
        "battery electric": "BEV",
        "fuel cell electric": "FCEV",
        "battery electric - overnight charging": "BEV-depot",
        "battery electric - opportunity charging": "BEV-opp",
        "battery electric - battery-equipped trolleybus": "BEV-motion",
    }
    standards = re.findall(r"EURO-[A-Za-z0-9]+", name)
    result["emission_standard"] = standards[-1] if standards else ""
    if family == "car":
        result.update(model_size=parts[3], model_powertrain=powers.get(parts[2], ""))
        result["candidate_year"] = {
            "EURO-2": 2000,
            "EURO-3": 2005,
            "EURO-4": 2010,
            "EURO-6ab": 2015,
        }.get(result["emission_standard"], 2020)
    elif family == "bus":
        sizes = {
            "13m single deck urban bus": "13m-city",
            "13m double deck urban bus": "13m-city-double",
            "13m single deck coach bus": "13m-coach",
            "13m double deck coach bus": "13m-coach-double",
            "18m articulated urban bus": "18m",
            "9m midibus": "9m",
        }
        result.update(
            model_size=next(value for key, value in sizes.items() if key in name),
            model_powertrain=powers.get(parts[2], ""),
        )
        result["candidate_year"] = {
            "EURO-III": 2000,
            "EURO-IV": 2005,
            "EURO-V": 2010,
        }.get(result["emission_standard"], 2020)
        if parts[2] in ("gasoline", "liquefied petroleum gas"):
            result["model_powertrain"] = ""
    elif family == "truck":
        result.update(
            model_size=parts[4].replace(" metric ton", "t"),
            model_powertrain=powers.get(parts[3], ""),
        )
        original = re.findall(r"Manufacture year: (\d+)", dataset.get("comment") or "")
        result["year_evidence"] = (
            f"original comment year={original[0] if original else 'undocumented'}; proposed 2020 rebasing is a separate change"
        )
        if parts[3] in ("gasoline", "gasoline hybrid", "liquefied petroleum gas"):
            result["model_powertrain"] = ""
    else:
        result["candidate_year"] = dataset.get("year", 2020)
        result["year_evidence"] = "explicit workbook year"
        if parts[1] == "Motorbike":
            result.update(
                model_size=f"Motorcycle {parts[3]}", model_powertrain=powers[parts[2]]
            )
            if parts[3] == "<4kW":
                result.update(
                    status="unavailable: no Motorcycle <4kW; BEV Moped <4kW is masked",
                    model_size="",
                )
        elif parts[1] in ("Scooter", "Moped"):
            result.update(
                model_size=f"{parts[1]} {parts[3]}", model_powertrain=powers[parts[2]]
            )
        elif parts[1] == "Kick Scooter":
            result.update(model_size="Kick-scooter", model_powertrain="BEV")
        elif parts[1] == "Bicycle":
            result["model_size"] = (
                "Bicycle cargo"
                if "cargo bike" in name
                else "Bicycle <45" if "45 km/h" in name else "Bicycle <25"
            )
            result["model_powertrain"] = "Human" if "conventional" in name else "BEV"
        else:
            result["status"] = (
                "preserve separately: tram is outside carculator_two_wheeler"
            )
    if not result["model_powertrain"] and not result["status"].startswith("preserve"):
        result["status"] = "explicit proxy policy required; no native powertrain"
    if family in ("car", "bus") and result["emission_standard"]:
        result["year_evidence"] = (
            "candidate inferred from EURO label and current euro_classes.yaml; original year not recovered"
        )
    result["functional_unit"] = {
        "car": "vkm",
        "bus": "pkm",
        "truck": "tkm",
        "two-wheeler": "vkm",
    }[family]
    if "Tram" in name:
        result["functional_unit"] = "pkm"
    standard = result["emission_standard"]
    selected = (
        not standard
        or standard
        == {
            "car": "EURO-6",
            "bus": "EURO-VI",
            "truck": "EURO-VI",
            "two-wheeler": "EURO-5",
        }[family]
    )
    result["selected_for_2020_update"] = selected
    if selected:
        result["candidate_year"] = 2020
        if family != "truck":
            result["year_evidence"] = (
                "2020 baseline requested by user; not a claim about original export provenance"
            )
    else:
        result["candidate_year"] = None
        result["year_evidence"] = (
            "historical class excluded by requested 2020-only scope"
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--premise", type=Path, default=Path("../premise"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    inventory_dir = args.premise / "premise/data/additional_inventories"
    mapping_dir = args.premise / "premise/iam_variables_mapping"
    summary, catalogue, all_datasets, coverage = {}, [], [], []
    issues = defaultdict(list)
    for family, (filename, mapping_file) in WORKBOOKS.items():
        path = inventory_dir / filename
        datasets, sheets, caches = read_workbook(path)
        for ds in datasets:
            ds["family"] = family
        all_datasets.extend(datasets)
        transports = [d for d in datasets if d["name"].lower().startswith("transport,")]
        summary[family] = dict(
            path=str(path.resolve()),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            sheets=sheets,
            datasets=len(datasets),
            transport_datasets=len(transports),
            exchanges=sum(len(d["exchanges"]) for d in datasets),
            locations=dict(Counter(d.get("location") for d in datasets)),
            units=dict(Counter(d.get("unit") for d in datasets)),
            transport_units=dict(Counter(d.get("unit") for d in transports)),
            missing_formula_caches=caches,
        )
        mapping = yaml.safe_load((mapping_dir / mapping_file).read_text())
        selected_names = set()
        for technology, data in mapping.items():
            if "ecoinvent_aliases" not in data:
                continue
            selected = [
                d for d in transports if matches(d["name"], data["ecoinvent_aliases"])
            ]
            selected_names.update(d["name"] for d in selected)
            coverage.append(
                dict(
                    family=family,
                    technology=technology,
                    matches=len(selected),
                    names=[d["name"] for d in selected],
                    locations=[d.get("location") for d in selected],
                    aliases=data["ecoinvent_aliases"],
                )
            )
        summary[family]["mapped_transport_datasets"] = sum(
            d["name"] in selected_names for d in transports
        )
        for ds in datasets:
            counts = Counter(e.get("type") for e in ds["exchanges"])
            row = {k: v for k, v in ds.items() if k != "exchanges"}
            row["exchange_counts"] = dict(counts)
            row["mapped_by_iam_name_filters"] = ds["name"] in selected_names
            catalogue.append(row)
            label = dict(
                workbook=filename, sheet=ds["sheet"], row=ds["row"], name=ds["name"]
            )
            production = [e for e in ds["exchanges"] if e.get("type") == "production"]
            if len(production) != 1:
                issues["production_count"].append(dict(**label, count=len(production)))
            elif identity(production[0]) != identity(ds):
                issues["production_identity"].append(
                    dict(
                        **label,
                        activity=identity(ds),
                        production=identity(production[0]),
                    )
                )
            for exc in ds["exchanges"]:
                amount = exc.get("amount")
                if not isinstance(amount, (float, int)) or not math.isfinite(amount):
                    issues["invalid_amount"].append(dict(**label, exchange=exc))
                if exc.get("type") == "technosphere" and not (
                    exc.get("reference product") or exc.get("product")
                ):
                    issues["missing_product"].append(dict(**label, exchange=exc))
    identities = defaultdict(list)
    for ds in all_datasets:
        identities[tuple(str(v).lower() for v in identity(ds))].append(ds)
    for key, datasets in identities.items():
        if len(datasets) > 1:
            issues["duplicate_identities"].append(
                dict(identity=key, workbooks=[d["workbook"] for d in datasets])
            )
    suppliers = Counter()
    for ds in all_datasets:
        for exc in ds["exchanges"]:
            if exc.get("type") == "technosphere":
                key = tuple(str(v).lower() for v in identity(exc))
                if key not in identities:
                    suppliers[identity(exc)] += 1
    external = [
        dict(zip(("name", "reference product", "location", "unit"), key), uses=count)
        for key, count in suppliers.most_common()
    ]
    provenance = {}
    for package in [
        "carculator_utils",
        "carculator",
        "carculator_bus",
        "carculator_truck",
        "carculator_two_wheeler",
        "premise",
    ]:
        repo = args.premise.parent / package
        provenance[package] = {
            "head": subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
            ).strip(),
            "status": subprocess.check_output(
                ["git", "-C", str(repo), "status", "--short"], text=True
            ),
        }
    for name, data in [
        ("summary", summary),
        ("checks", issues),
        ("provenance", provenance),
        ("parsed_inventories", all_datasets),
    ]:
        (args.output / f"{name}.json").write_text(
            json.dumps(data, indent=2, default=str) + "\n"
        )
    write_csv(args.output / "datasets.csv", catalogue)
    write_csv(args.output / "mapping_coverage.csv", coverage)
    write_csv(args.output / "external_suppliers.csv", external)
    recipes = [
        candidate_recipe(d) for d in all_datasets if d["name"].startswith("transport,")
    ]
    write_csv(args.output / "candidate_recipes.csv", recipes)
    for family, data in summary.items():
        print(
            family,
            {
                k: data[k]
                for k in [
                    "datasets",
                    "transport_datasets",
                    "exchanges",
                    "locations",
                    "transport_units",
                    "mapped_transport_datasets",
                ]
            },
        )
    print("Checks:", {key: len(value) for key, value in issues.items()})
    print("External supplier identities:", len(external))


if __name__ == "__main__":
    main()
