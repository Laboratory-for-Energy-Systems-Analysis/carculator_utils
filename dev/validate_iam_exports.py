"""Collect completed 2025 family exports, then audit exact 3.12 destinations.

Run --collect in the family runtime environment and --audit in Brightway's
environment. No destination database is modified. Custom noise is reported
separately because it requires a user-supplied biosphere database and method.
"""

import argparse
import importlib
import json
from pathlib import Path


def collect(path):
    from validate_iam_models import CASES

    records = []
    for package, (prefix, size, electric, combustion, kwargs) in CASES.items():
        module = importlib.import_module(package)
        for chemistry in (None, "NMC-532"):
            inputs = getattr(module, prefix + "InputParameters")()
            inputs.static()
            _, array = module.fill_xarray_from_input_parameters(
                inputs,
                scope={
                    "size": [size],
                    "powertrain": [electric, combustion],
                    "year": [2025],
                },
            )
            options = dict(kwargs)
            if chemistry:
                options["energy_storage"] = {
                    "electric": {(electric, size, 2025): chemistry}
                }
            model = getattr(module, prefix + "Model")(array, **options)
            model.set_all()
            inventory = getattr(module, "Inventory" + prefix)(model, scenario="static")
            exported = inventory.export_lci(software="brightway2", format="bw2io")
            records.append(
                {
                    "package": package,
                    "chemistry": chemistry or "default",
                    "version": "3.12",
                    "data": exported.data,
                }
            )
    path.write_text(json.dumps(records, indent=2) + "\n")


def audit(source, output):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from audit_export_targets import audit as audit_targets

    records = json.loads(source.read_text())
    reports = audit_targets(records)
    for record, report in zip(records, reports):
        report["chemistry"] = record["chemistry"]
        # This exact known flow set is retained in Brightway/openLCA exports.
        import ast

        noise = {}
        for key in list(report["unresolved"]):
            label = ast.literal_eval(key)
            if (
                len(label) == 3
                and label[2] == "joule"
                and label[1]
                in [
                    (f"octave {i}", "day time", setting)
                    for i in range(1, 9)
                    for setting in ("urban", "suburban", "rural")
                ]
                and label[0] == "noise, " + ", ".join(label[1])
            ):
                noise[key] = report["unresolved"].pop(key)
        report["custom_noise_requires_user_method"] = noise
    output.write_text(json.dumps(reports, indent=2) + "\n")
    unresolved = [r for r in reports if r["unresolved"]]
    if unresolved:
        raise ValueError(f"Unresolved ecoinvent suppliers/flows; see {output}")
    print(f"Verified all external links in {len(reports)} completed family exports.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--collect", action="store_true")
    mode.add_argument("--audit", action="store_true")
    parser.add_argument("--inventories", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.collect:
        collect(args.inventories)
    else:
        if not args.report:
            parser.error("--report is required for --audit")
        audit(args.inventories, args.report)
