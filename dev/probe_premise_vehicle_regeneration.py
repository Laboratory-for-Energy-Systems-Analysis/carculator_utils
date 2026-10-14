"""Exercise current local model/LCIA/Excel paths for representative premise vehicles.

These are raw model exports for comparison, not replacement premise workbooks.
No Brightway database is read or written. Run with the matched Python 3.12 stack.
"""

import argparse
import csv
import importlib
import json
import sys
import traceback
from pathlib import Path

import numpy as np

CASES = {
    "car": ("carculator", "Car", "Medium", ["ICEV-p", "BEV"], "vkm", {}),
    "bus": ("carculator_bus", "Bus", "13m-city", ["ICEV-d", "BEV-depot"], "pkm", {}),
    "truck": (
        "carculator_truck",
        "Truck",
        "40t",
        ["ICEV-d", "BEV"],
        "tkm",
        {"cycle": "Long haul"},
    ),
    "two-wheeler": (
        "carculator_two_wheeler",
        "TwoWheeler",
        "Motorcycle 11-35kW",
        ["ICEV-p", "BEV"],
        "vkm",
        {},
    ),
}


def probe_native_scope(args):
    """Screen selected native coordinates with defaults, without an inventory solve."""
    with args.scope_manifest.open() as stream:
        recipes = list(csv.DictReader(stream))
    report = {}
    for family, (package, stem, _, _, _, kwargs) in CASES.items():
        selected = [
            recipe
            for recipe in recipes
            if recipe["family"] == family
            and recipe["selected_for_2020_update"] == "True"
            and recipe["status"].startswith("native")
        ]
        scope = {
            "size": sorted({r["model_size"] for r in selected}),
            "powertrain": sorted({r["model_powertrain"] for r in selected}),
            "year": [2020],
        }
        result = {
            "scope": scope,
            "country": "CH",
            "kwargs": kwargs,
            "diagnostic_only": "Default climate/cycles/loads, not a final generation recipe",
        }
        report[family] = result
        try:
            module = importlib.import_module(package)
            inputs = getattr(module, stem + "InputParameters")()
            inputs.static()
            _, array = module.fill_xarray_from_input_parameters(inputs, scope=scope)
            model = getattr(module, stem + "Model")(array, country="CH", **kwargs)
            model.set_all()
            result["vehicles"] = []
            for recipe in selected:
                cell = model.array.sel(
                    size=recipe["model_size"],
                    powertrain=recipe["model_powertrain"],
                    year=2020,
                ).isel(value=0)
                parameters = [
                    "TtW energy",
                    "cargo mass",
                    "average passengers",
                    "range",
                    "target range",
                    "electric energy stored",
                    "curb mass",
                    "gross mass",
                    "available payload",
                ]
                # TwoWheelerModel does not populate the legacy is_available
                # array parameter; it applies availability directly to energy.
                if family != "two-wheeler":
                    parameters.extend(["is_available", "is_compliant"])
                values = {
                    p: float(cell.sel(parameter=p))
                    for p in parameters
                    if p in cell.parameter.values
                }
                passed = (
                    all(np.isfinite(value) for value in values.values())
                    and values["TtW energy"] > 0
                    and values.get("is_available", 1) > 0
                    and values.get("is_compliant", 1) > 0
                    and (family != "truck" or values["cargo mass"] > 0)
                )
                result["vehicles"].append(
                    dict(name=recipe["name"], screening_passed=bool(passed), **values)
                )
            result["status"] = "completed"
        except Exception:
            result.update(status="failed", error=traceback.format_exc())
        (args.output / "feasibility.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        print(f"SCOPE {family}: {result['status']}", flush=True)
    if any(r["status"] != "completed" for r in report.values()):
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repositories-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--year", type=int, default=2020)
    parser.add_argument(
        "--scope-manifest",
        type=Path,
        help="Screen all selected native 2020 model coordinates, without LCIA/export",
    )
    parser.add_argument(
        "--families", nargs="+", choices=list(CASES), default=list(CASES)
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    for package in ["carculator_utils", *[c[0] for c in CASES.values()]]:
        sys.path.insert(0, str(args.repositories_root / package))
    if args.scope_manifest:
        probe_native_scope(args)
        return
    from audit_premise_vehicle_workbooks import read_workbook

    report = {
        "python": sys.version,
        "numpy": np.__version__,
        "year": args.year,
        "cases": {},
    }
    for family, (package, stem, size, powertrains, fu, kwargs) in CASES.items():
        if family not in args.families:
            continue
        result = {
            "scope": dict(size=[size], powertrain=powertrains, year=[args.year]),
            "functional_unit": fu,
            "country": "CH",
            "kwargs": kwargs,
        }
        report["cases"][family] = result
        try:
            module = importlib.import_module(package)
            result["module"] = module.__file__
            result["version"] = module.__version__
            inputs = getattr(module, f"{stem}InputParameters")()
            inputs.static()
            _, array = module.fill_xarray_from_input_parameters(
                inputs, scope=result["scope"]
            )
            model = getattr(module, f"{stem}Model")(array, country="CH", **kwargs)
            model.set_all()
            inventory = getattr(module, f"Inventory{stem}")(
                model, scenario="static", functional_unit=fu
            )
            impacts = inventory.calculate_impacts()
            result["lcia_finite"] = bool(np.isfinite(impacts.values).all())
            result["impact_shape"] = list(impacts.shape)
            result["cycle"] = str(model.cycle)
            result["energy_storage"] = repr(model.energy_storage)
            result["model_results"] = []
            for powertrain in model.array.powertrain.values:
                cell = model.array.sel(
                    size=size, powertrain=powertrain, year=args.year
                ).isel(value=0)
                result["model_results"].append(
                    dict(
                        powertrain=str(powertrain),
                        **{
                            parameter: float(cell.sel(parameter=parameter))
                            for parameter in [
                                "TtW energy",
                                "electricity consumption",
                                "fuel consumption",
                                "curb mass",
                                "driving mass",
                                "cargo mass",
                                "average passengers",
                                "lifetime kilometers",
                                "kilometers per year",
                                "energy battery mass",
                                "electric energy stored",
                                "battery lifetime replacements",
                                "fuel cell lifetime replacements",
                                "target range",
                            ]
                            if parameter in cell.parameter.values
                        },
                    )
                )
            paths = inventory.export_lci(
                ecoinvent_version="3.12",
                software="brightway2",
                format="file",
                directory=str(args.output / family),
                filename="raw_probe",
            )
            if not isinstance(paths, list):
                paths = [paths]
            result["exports"] = [str(p) for p in paths]
            exported = []
            for path in paths:
                exported.extend(read_workbook(Path(path))[0])
            result["activities"] = len(exported)
            result["transport"] = [
                d
                for d in exported
                if d["name"].startswith(f"transport, {model.vehicle_type},")
            ]
            result["checks"] = []
            for data in result["model_results"]:
                load = (
                    data["average passengers"]
                    if fu == "pkm"
                    else data["cargo mass"] / 1000 if fu == "tkm" else 1
                )
                expected_vehicle = 1 / (data["lifetime kilometers"] * load)
                # Match by the exported powertrain label, not by row order.
                from carculator_utils.export import rename_mapping

                label = rename_mapping("rename_powertrains.yaml")[data["powertrain"]]
                activity = next(
                    d
                    for d in result["transport"]
                    if d["name"] == f"transport, {model.vehicle_type}, {label}, {size}"
                )
                vehicle = sum(
                    e["amount"]
                    for e in activity["exchanges"]
                    if e["type"] == "technosphere"
                    and e["name"] == f"{model.vehicle_type}, {label}, {size}"
                )
                electricity = sum(
                    e["amount"]
                    for e in activity["exchanges"]
                    if e["type"] == "technosphere"
                    and e["name"].startswith("electricity supply for electric vehicles")
                )
                checks = dict(
                    powertrain=data["powertrain"],
                    vehicle_lifetime_normalization=bool(
                        np.isclose(vehicle, expected_vehicle, rtol=1e-6, atol=0)
                    ),
                    electricity_load_normalization=bool(
                        np.isclose(
                            electricity,
                            data["electricity consumption"] / load,
                            rtol=1e-6,
                            atol=1e-12,
                        )
                    ),
                )
                result["checks"].append(checks)
                assert all(v for k, v in checks.items() if k != "powertrain"), checks
            assert result["lcia_finite"]
            (args.output / f"{family}_raw.json").write_text(
                json.dumps(exported, indent=2, default=str) + "\n"
            )
            result["status"] = "completed"
        except Exception:
            result["status"] = "failed"
            result["error"] = traceback.format_exc()
        (args.output / "probe.json").write_text(
            json.dumps(report, indent=2, default=str) + "\n"
        )
        print(f"PROBE {family}: {result['status']}", flush=True)
    if any(case["status"] != "completed" for case in report["cases"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
