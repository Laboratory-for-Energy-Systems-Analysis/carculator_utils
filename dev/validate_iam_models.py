"""Run completed family model/LCIA cases against a selected IAM resource bundle."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

CASES = {
    "carculator": ("Car", "Lower medium", "BEV", "ICEV-p", {}),
    "carculator_truck": ("Truck", "18t", "BEV", "ICEV-d", {"cycle": "Urban delivery"}),
    "carculator_bus": ("Bus", "13m-city", "BEV-depot", "ICEV-d", {}),
    "carculator_two_wheeler": ("TwoWheeler", "Scooter <4kW", "BEV", "ICEV-p", {}),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iam-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-nmc532", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    from carculator_utils import DATA_DIR

    inventory_module = importlib.import_module("carculator_utils.inventory")
    overlay = args.output / "data"
    overlay.mkdir()
    for path in DATA_DIR.iterdir():
        (overlay / path.name).symlink_to(
            args.iam_dir.resolve() if path.name == "IAM" else path,
            target_is_directory=path.is_dir(),
        )
    inventory_module.DATA_DIR = overlay
    # B's directory is captured separately at module import time. Redirect it
    # together with A and the index; mixing bundles invalidates every result.
    inventory_module.IAM_FILES_DIR = args.iam_dir.resolve()
    impact_tables, model_tables = [], []
    checks = []
    scenarios = ("static", "SSP2-NPi", "SSP2-PkBudg1000", "SSP2-PkBudg650")
    for package, (prefix, size, electric, combustion, kwargs) in CASES.items():
        module = importlib.import_module(package)
        for chemistry in [None] + (["NMC-532"] if args.include_nmc532 else []):
            years = [2025, 2030, 2050] if chemistry is None else [2025]
            powertrains = [electric, combustion] if chemistry is None else [electric]
            inputs = getattr(module, prefix + "InputParameters")()
            inputs.static()
            _, array = module.fill_xarray_from_input_parameters(
                inputs, scope={"size": [size], "powertrain": powertrains, "year": years}
            )
            options = dict(kwargs)
            if chemistry:
                options["energy_storage"] = {
                    "electric": {(electric, size, 2025): chemistry}
                }
            model = getattr(module, prefix + "Model")(array, **options)
            model.set_all()
            before = model.array.copy(deep=True)
            if not bool((model["TtW energy"] > 0).all()):
                raise AssertionError(
                    f"Unavailable validation case: {package} {chemistry}"
                )
            parameters = [
                "TtW energy",
                "electricity consumption",
                "electric energy stored",
                "energy battery mass",
                "range",
                "target range",
                "driving mass",
            ]
            selected = model.array.sel(
                parameter=[
                    name for name in parameters if name in model.array.parameter.values
                ]
            )
            table = selected.to_dataframe(name="amount").reset_index()
            table["package"], table["chemistry"] = package, chemistry or "default"
            model_tables.append(table)
            for scenario in scenarios if chemistry is None else ["static"]:
                groups = [("recipe", "midpoint")]
                if scenario == "static" and chemistry is None:
                    groups += [("recipe", "endpoint"), ("ef", "midpoint")]
                for method, indicator in groups:
                    inventory = getattr(module, "Inventory" + prefix)(
                        model, scenario=scenario, method=method, indicator=indicator
                    )
                    results = inventory.calculate_impacts()
                    if not np.isfinite(results.values).all():
                        raise AssertionError(
                            f"Nonfinite impacts: {package}, {scenario}"
                        )
                    table = (
                        results.sum("impact").to_dataframe(name="amount").reset_index()
                    )
                    table["package"], table["chemistry"] = (
                        package,
                        chemistry or "default",
                    )
                    table["scenario"], table["method"], table["indicator"] = (
                        scenario,
                        method,
                        indicator,
                    )
                    impact_tables.append(table)
                    checks.append(
                        {
                            "package": package,
                            "chemistry": chemistry or "default",
                            "scenario": scenario,
                            "method": method,
                            "indicator": indicator,
                            "vehicles": int(np.prod(results.shape[1:4])),
                        }
                    )
                    xr.testing.assert_equal(model.array, before)
                    del inventory
            print(f"Completed: {package}, {chemistry or 'default'}", flush=True)
    pd.concat(impact_tables, ignore_index=True).to_csv(
        args.output / "impacts.csv", index=False
    )
    pd.concat(model_tables, ignore_index=True).to_csv(
        args.output / "vehicles.csv", index=False
    )
    (args.output / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")


if __name__ == "__main__":
    main()
