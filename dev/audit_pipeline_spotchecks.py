"""Run reproducible vehicle-to-LCIA spot checks and collect private BW exports.

Run in a Python 3.12 environment containing all five sibling checkouts. The
public report contains scalar results only; --private-dir holds full exports
and logs and must not be committed or redistributed.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import spsolve

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261010
RTOL = 1e-5  # Float32 vehicle arrays and exports; not empirical uncertainty.
POOLS = {
    "carculator": (
        "Car",
        ["Small", "Lower medium", "Medium", "Large SUV"],
        ["BEV", "ICEV-p"],
        {},
        "pkm",
    ),
    "carculator_truck": (
        "Truck",
        ["7.5t", "18t", "26t", "40t"],
        ["BEV", "ICEV-d"],
        {"cycle": "Urban delivery"},
        "tkm",
    ),
    "carculator_bus": (
        "Bus",
        ["9m", "13m-city", "18m"],
        ["BEV-depot", "ICEV-d"],
        {},
        "pkm",
    ),
    "carculator_two_wheeler": (
        "TwoWheeler",
        ["Scooter <4kW", "Scooter 4-11kW", "Motorcycle 4-11kW"],
        ["BEV", "ICEV-p"],
        {},
        "pkm",
    ),
}


def scalar(value):
    return float(np.asarray(value).item())


def cases():
    rng = np.random.default_rng(SEED)
    selected = []
    for package, (prefix, sizes, powertrains, options, fu) in POOLS.items():
        for pt in powertrains:
            selected.append(
                dict(
                    package=package,
                    prefix=prefix,
                    size=str(rng.choice(sizes)),
                    powertrain=pt,
                    options={**options, "country": str(rng.choice(["CH", "DE", "FR"]))},
                    functional_unit=fu,
                    scenario="static",
                    year=2025,
                )
            )
    selected.extend(
        [
            dict(
                package="carculator",
                prefix="Car",
                size="Lower medium",
                powertrain="PHEV-p",
                options={"country": "CH", "electric_utility_factor": {2025: 0.6}},
                functional_unit="vkm",
                scenario="static",
                year=2025,
            ),
            dict(
                package="carculator_truck",
                prefix="Truck",
                size="26t",
                powertrain="FCEV",
                options={"country": "DE", "cycle": "Regional delivery"},
                functional_unit="tkm",
                scenario="static",
                year=2025,
            ),
        ]
    )
    # Same foreground vehicle, but prospective 2025 background (interpolated).
    selected.append({**selected[0], "scenario": "SSP2-NPi"})
    return [{"id": f"case-{i+1:02d}", **case} for i, case in enumerate(selected)]


def check(record, name, observed, expected, unit="", rtol=RTOL, atol=1e-10):
    observed, expected = scalar(observed), scalar(expected)
    record["checks"].append(
        dict(
            name=name,
            observed=observed,
            expected=expected,
            unit=unit,
            rtol=rtol,
            atol=atol,
            passed=bool(np.isclose(observed, expected, rtol=rtol, atol=atol)),
        )
    )


def run_case(case, private):
    module = importlib.import_module(case["package"])
    ip = getattr(module, case["prefix"] + "InputParameters")()
    ip.static()
    _, array = module.fill_xarray_from_input_parameters(
        ip,
        scope={
            "size": [case["size"]],
            "powertrain": [case["powertrain"]],
            "year": [case["year"]],
        },
    )
    model = getattr(module, case["prefix"] + "Model")(array, **case["options"])
    model.set_all()
    inventory = getattr(module, "Inventory" + case["prefix"])(
        model, scenario=case["scenario"], functional_unit=case["functional_unit"]
    )
    impacts = inventory.calculate_impacts().sum("impact")
    record = {**case, "cycle": model.ecm.cycle_name, "checks": []}
    p = {str(name): scalar(model[name]) for name in model.array.parameter.values}
    record["parameters"] = p
    record["active"] = p["TtW energy"] > 0
    if not record["active"]:
        raise ValueError(
            f"Selected case is unavailable or has no energy demand: {case}"
        )
    check(
        record,
        "driving mass",
        p["driving mass"],
        p["curb mass"]
        + p["cargo mass"]
        + p["average passengers"] * p["average passenger mass"],
        "kg",
        rtol=0.002,
    )
    pt = case["powertrain"]
    if pt.startswith("BEV"):
        check(
            record,
            "battery capacity from cells",
            p["electric energy stored"],
            p["battery cell mass"] * p["battery cell energy density"],
            "kWh",
        )
        check(
            record,
            "battery pack mass from cells",
            p["energy battery mass"],
            p["battery cell mass"] / p["battery cell mass share"],
            "kg",
        )
        check(
            record,
            "AC charging energy",
            p["electricity consumption"],
            p["TtW energy"]
            / (3600 * p["battery charge efficiency"] * p["charger efficiency"]),
            "kWh/km",
        )
        if "range" in p:
            check(
                record,
                "range from usable stored energy",
                p["range"],
                p["electric energy stored"] * p["battery DoD"] * 3600 / p["TtW energy"],
                "km",
            )
    if pt.startswith("ICEV") or pt == "FCEV":
        check(
            record,
            "fuel from energy balance",
            p["fuel consumption"] * p["fuel density per kg"],
            p["TtW energy"] / (1000 * p["LHV fuel MJ per kg"]),
            "kg/km",
            rtol=0.002,
        )
    fu = case["functional_unit"]
    load = (
        1
        if fu == "vkm"
        else p["average passengers"] if fu == "pkm" else p["cargo mass"] / 1000
    )
    record["load_per_vehicle_km"] = load
    # Select by identity, not by hard-coded matrix position or production order.
    transports = [
        (i, key)
        for i, key in inventory.rev_inputs.items()
        if key[0].startswith(f"transport, {model.vehicle_type}, ")
    ]
    assert len(transports) == 1, transports
    column, label = transports[0]
    record["transport_label"] = label
    a = inventory.A[0, :, :, 0].astype(float)
    # Solve the whole system directly; bypass calculate_impacts' supplier
    # selection, vehicle allocation, source grouping and FU implementation.
    demand = np.zeros(a.shape[0])
    demand[column] = 1 / load
    supply = spsolve(csc_matrix(a), demand)
    b = (
        inventory.B.isel(year=0)
        if case["scenario"] == "static"
        else inventory.B.interp(year=case["year"])
    )
    manual = np.asarray(b) @ supply
    record["impacts"] = []
    for i, category in enumerate(impacts.impact_category.values):
        core = scalar(impacts.sel(impact_category=category))
        check(record, f"full matrix solve: {category}", core, manual[i])
        record["impacts"].append(
            dict(category=str(category), core=core, manual=float(manual[i]))
        )
    for i, key in inventory.rev_inputs.items():
        if key[0].startswith(model.vehicle_type + ", "):
            lifetime = p["lifetime kilometers"]
            check(
                record, "vehicle allocation", -a[i, column], 1 / lifetime, "vehicle/km"
            )
        if (
            key[0].startswith("electricity supply for electric vehicles")
            and a[i, column]
        ):
            check(
                record,
                "electricity purchase in A",
                -a[i, column],
                p["electricity consumption"],
                "kWh/km",
            )
        if key[0].startswith("fuel supply for ") and a[i, column]:
            check(
                record,
                "fuel purchase in A",
                -a[i, column],
                p["fuel consumption"] * p["fuel density per kg"],
                "kg/km",
            )
    fuel = {
        "ICEV-p": "petrol",
        "PHEV-p": "petrol",
        "ICEV-d": "diesel",
        "ICEV-g": "methane",
        "FCEV": "hydrogen",
    }.get(pt)
    if fuel:
        blend = inventory.fuel_blend[fuel]
        record["fuel_blend"] = {
            role: {
                k: v.tolist() if isinstance(v, np.ndarray) else v
                for k, v in component.items()
            }
            for role, component in blend.items()
        }
        kg = p["fuel consumption"] * p["fuel density per kg"]
        if fuel != "hydrogen":
            for bio, name in [(False, "fossil"), (True, "non-fossil")]:
                expected = kg * sum(
                    scalar(c["share"])
                    * scalar(c["CO2"])
                    * (
                        scalar(c["biogenic share"])
                        if bio
                        else 1 - scalar(c["biogenic share"])
                    )
                    for c in blend.values()
                )
                i = inventory.inputs[(f"Carbon dioxide, {name}", ("air",), "kilogram")]
                check(record, "tailpipe CO2 " + name, -a[i, column], expected, "kg/km")
    snapshot = inventory.A.copy()
    exported = inventory.export_lci(software="brightway2", format="bw2io")
    check(record, "export preserves A", np.max(np.abs(inventory.A - snapshot)), 0)
    data = exported.data
    targets = [
        d for d in data if d["name"].startswith(f"transport, {model.vehicle_type}, ")
    ]
    assert len(targets) == 1
    record["export_target"] = {
        k: targets[0][k]
        for k in ["name", "reference product", "location", "unit", "code"]
    }
    record["export_activity_count"] = len(data)
    (private / (case["id"] + ".json")).write_text(json.dumps(data, indent=2) + "\n")
    # Private solver diagnostics allow discrepancy analysis without rerunning.
    np.savez_compressed(
        private / (case["id"] + "-matrices.npz"), A=a, B=np.asarray(b), supply=supply
    )
    (private / (case["id"] + "-labels.json")).write_text(
        json.dumps([inventory.rev_inputs[i] for i in range(len(a))])
    )
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    args.private_dir.mkdir(parents=True, exist_ok=args.resume)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "seed": SEED,
        "rtol": RTOL,
        "candidate_pools": POOLS,
        "cases": [],
        "revisions": {},
    }
    if args.resume:
        report = json.loads(args.report.read_text())
    report["runtime"] = {
        "python": sys.version,
        "packages": {
            p: importlib.metadata.version(p)
            for p in ["numpy", "scipy", "xarray", "carculator_utils", *POOLS]
        },
    }
    for package in ["carculator_utils", *POOLS]:
        path = ROOT if package == "carculator_utils" else ROOT.parent / package
        report["revisions"][package] = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
        ).strip()
    for case in cases():
        if any(r["id"] == case["id"] for r in report["cases"]):
            continue
        print("Running", case, flush=True)
        with (
            (args.private_dir / (case["id"] + ".log")).open("w") as log,
            contextlib.redirect_stdout(log),
        ):
            record = run_case(case, args.private_dir)
        report["cases"].append(record)
        args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        failed = [c["name"] for c in record["checks"] if not c["passed"]]
        print("Completed", case["id"], "failed checks:", failed, flush=True)


if __name__ == "__main__":
    main()
