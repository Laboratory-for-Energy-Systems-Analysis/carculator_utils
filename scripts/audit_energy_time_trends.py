"""Compare pre/post harmonization annual full models, using each standard cycle."""

import argparse
import contextlib
import hashlib
import importlib
import json
import traceback
from pathlib import Path
from unittest.mock import patch

import numpy as np

from carculator_utils.model import VehicleModel

from harmonize_energy_time_trends import restore
from validate_energy_2025 import provenance as runtime_provenance

FAMILIES = {
    "carculator": (
        "Car",
        [
            ("Lower medium", p)
            for p in ("ICEV-p", "BEV", "HEV-p", "PHEV-c-p", "PHEV-e", "FCEV")
        ],
    ),
    "carculator_bus": (
        "Bus",
        [
            ("13m-city", p)
            for p in ("ICEV-d", "HEV-d", "BEV-depot", "BEV-opp", "BEV-motion", "FCEV")
        ],
    ),
    "carculator_truck": (
        "Truck",
        [("40t", p) for p in ("ICEV-d", "HEV-d", "BEV", "PHEV-c-d", "PHEV-e", "FCEV")],
    ),
    "carculator_two_wheeler": (
        "TwoWheeler",
        [("Moped <4kW", "ICEV-p"), ("Scooter <4kW", "BEV"), ("Bicycle <25", "BEV")],
    ),
}
YEARS = list(range(2015, 2041))
METRICS = (
    "TtW energy",
    "fuel consumption",
    "electricity consumption",
    "driving mass",
    "electric power",
    "power",
    "is_available",
)


def run(module, prefix, array, size, pt, variant):
    kwargs = {"drop_hybrids": False} if pt.startswith("PHEV") else {}
    model = getattr(module, prefix + "Model")(array, **kwargs)
    model.set_all()
    rows = []
    for year in array.year.values:
        row = dict(
            package=module.__name__,
            size=size,
            powertrain=pt,
            variant=variant,
            year=int(year),
            status="ok",
        )
        for parameter in METRICS:
            if parameter in model.array.parameter:
                row[parameter] = float(
                    model[parameter].sel(size=size, powertrain=pt, year=year).item()
                )
        if not np.isfinite(row["TtW energy"]) or (
            row["TtW energy"] <= 0 and row.get("is_available", 1) > 0
        ):
            raise ValueError(f"Invalid energy: {row}")
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=args.resume)
    runtime = runtime_provenance()
    runtime_path = args.output / "runtime_provenance.json"
    if args.resume:
        previous_runtime = json.loads(runtime_path.read_text())
        for key in ("python", "numpy", "xarray"):
            assert (
                runtime[key] == previous_runtime[key]
            ), "Runtime changed since cached runs"
        for name, details in runtime["packages"].items():
            assert (
                details["sha256"] == previous_runtime["packages"][name]["sha256"]
            ), "Model code or resources changed since cached runs"
    else:
        runtime_path.write_text(json.dumps(runtime, indent=2) + "\n")
    rows = json.loads((args.output / "runs.json").read_text()) if args.resume else []
    valid_cases = {(p, s, t) for p, (_, cases) in FAMILIES.items() for s, t in cases}
    rows = [
        r for r in rows if (r["package"], r["size"], r["powertrain"]) in valid_cases
    ]
    previous_provenance = (
        json.loads((args.output / "provenance.json").read_text()) if args.resume else {}
    )
    provenance, anchors = {}, []
    for package, (prefix, cases) in FAMILIES.items():
        module = importlib.import_module(package)
        cls = getattr(module, prefix + "InputParameters")
        current = json.loads(cls.DEFAULT.read_text())
        manifest_path = cls.DEFAULT.parent / "temporal_energy_provenance.json"
        manifest = json.loads(manifest_path.read_text())
        old = restore(current, manifest)
        provenance[package] = dict(
            default_parameters_sha256=hashlib.sha256(
                cls.DEFAULT.read_bytes()
            ).hexdigest(),
            temporal_provenance_sha256=hashlib.sha256(
                manifest_path.read_bytes()
            ).hexdigest(),
        )
        if args.resume:
            assert (
                provenance[package] == previous_provenance[package]
            ), "Inputs changed since cached runs"
        # Exact preservation of every 2025 scalar and uncertainty definition.
        for key, record in old.items():
            if record["year"] == 2025:
                assert record == {
                    k: v for k, v in current[key].items() if k != "uncertainty_group"
                }
        for size, pt in cases:
            for variant, records in [("before", old), ("after", current)]:
                inputs = cls(parameters=records)
                inputs.static()
                _, native = module.fill_xarray_from_input_parameters(
                    inputs,
                    scope={
                        "size": [size],
                        "powertrain": (
                            [pt, "PHEV-c-d"]
                            if package == "carculator_truck" and pt == "PHEV-e"
                            else [pt]
                        ),
                    },
                )
                array = native.astype(float).interp(year=YEARS)
                with (
                    (args.output / "model.log").open("a") as log,
                    contextlib.redirect_stdout(log),
                    contextlib.redirect_stderr(log),
                ):
                    anchors.extend(
                        run(
                            module,
                            prefix,
                            native.astype(float).sel(year=[2025]),
                            size,
                            pt,
                            variant,
                        )
                    )
                    cached = [
                        r
                        for r in rows
                        if (r["package"], r["size"], r["powertrain"], r["variant"])
                        == (package, size, pt, variant)
                    ]
                    if len(cached) == len(YEARS) and any(
                        r["status"] == "ok" for r in cached
                    ):
                        continue
                    rows = [r for r in rows if r not in cached]
                    try:
                        case_rows = run(module, prefix, array, size, pt, variant)
                    except Exception:
                        # An invalid legacy interpolation can prevent the whole vector run.
                        case_rows = []
                        for year in YEARS:
                            try:
                                case_rows.extend(
                                    run(
                                        module,
                                        prefix,
                                        array.sel(year=[year]),
                                        size,
                                        pt,
                                        variant,
                                    )
                                )
                            except Exception as exc:
                                traceback.print_exc()
                                case_rows.append(
                                    dict(
                                        package=package,
                                        size=size,
                                        powertrain=pt,
                                        variant=variant,
                                        year=year,
                                        status="error",
                                        error=str(exc),
                                    )
                                )
                rows.extend(case_rows)
                print(
                    package,
                    size,
                    pt,
                    variant,
                    sum(r["status"] == "ok" for r in case_rows),
                    "/",
                    len(YEARS),
                    flush=True,
                )
                (args.output / "runs.json").write_text(
                    json.dumps(rows, indent=2) + "\n"
                )
        (args.output / "provenance.json").write_text(
            json.dumps({**previous_provenance, **provenance}, indent=2) + "\n"
        )
    (args.output / "runs.json").write_text(json.dumps(rows, indent=2) + "\n")
    (args.output / "anchors_2025.json").write_text(json.dumps(anchors, indent=2) + "\n")
    comparisons = []
    for package, (_, cases) in FAMILIES.items():
        for size, pt in cases:
            selected = [
                r
                for r in rows
                if (r["package"], r["size"], r["powertrain"]) == (package, size, pt)
            ]
            by_variant = {
                v: {r["year"]: r for r in selected if r["variant"] == v}
                for v in ("before", "after")
            }
            before, after = [
                next(
                    r
                    for r in anchors
                    if (r["package"], r["size"], r["powertrain"], r["variant"])
                    == (package, size, pt, v)
                )
                for v in ("before", "after")
            ]
            assert before["status"] == after["status"] == "ok"
            for p in METRICS:
                if p in before:
                    assert np.isclose(before[p], after[p], rtol=1e-10, atol=1e-10), (
                        package,
                        pt,
                        p,
                        before[p],
                        after[p],
                    )
            entry = dict(
                package=package, size=size, powertrain=pt, anchor_2025_unchanged=True
            )
            for variant, data in by_variant.items():
                energy = {
                    y: r["TtW energy"] for y, r in data.items() if r["status"] == "ok"
                }
                entry[variant] = dict(
                    errors=[y for y, r in data.items() if r["status"] != "ok"],
                    energy_kJ_km={
                        y: energy.get(y) for y in (2020, 2024, 2025, 2026, 2030)
                    },
                    annual_changes_pct={
                        y: 100 * (energy[y] / energy[y - 1] - 1)
                        for y in energy
                        if y - 1 in energy and energy[y - 1] > 0 and energy[y] > 0
                    },
                )
            comparisons.append(entry)
    (args.output / "summary.json").write_text(
        json.dumps(dict(provenance=provenance, comparisons=comparisons), indent=2)
        + "\n"
    )
    # Different batches may stop at different sizing iterations. Check the
    # largest observed anchor residual (the FCEV truck) at tighter tolerance.
    module = importlib.import_module("carculator_truck")
    cls = module.TruckInputParameters
    current = json.loads(cls.DEFAULT.read_text())
    manifest = json.loads(
        (cls.DEFAULT.parent / "temporal_energy_provenance.json").read_text()
    )
    original_sizing = VehicleModel.iterate_sizing

    def tight_sizing(model, parameter, rtol, mask=None):
        return original_sizing(model, parameter, min(rtol, 1e-8), mask)

    tight_rows = []
    with (
        (args.output / "model.log").open("a") as log,
        contextlib.redirect_stdout(log),
        contextlib.redirect_stderr(log),
        patch.object(VehicleModel, "iterate_sizing", tight_sizing),
    ):
        for variant, records in [
            ("before", restore(current, manifest)),
            ("after", current),
        ]:
            inputs = cls(parameters=records)
            inputs.static()
            _, native = module.fill_xarray_from_input_parameters(
                inputs, scope={"size": ["40t"], "powertrain": ["FCEV"]}
            )
            tight_rows.extend(
                run(
                    module,
                    "Truck",
                    native.astype(float).interp(year=YEARS),
                    "40t",
                    "FCEV",
                    variant,
                )
            )
    values = [r["TtW energy"] for r in tight_rows if r["year"] == 2025]
    assert np.isclose(*values, rtol=1e-8)
    (args.output / "fcev_tight_sizing.json").write_text(
        json.dumps(dict(sizing_rtol=1e-8, runs=tight_rows), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
