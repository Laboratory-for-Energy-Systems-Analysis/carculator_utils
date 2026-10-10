"""Independently reconstruct cycle work and diagnose LCIA source grouping.

Force calculations use the speed trace, slopes and final vehicle parameters;
they do not call the energy module's force/energy helpers. Efficiency maps and
HVAC demand are retained model assumptions, not independently validated here.
"""

import argparse
import contextlib
import importlib
import io
import json
from pathlib import Path

import numpy as np
import yaml
from audit_pipeline_spotchecks import ROOT, cases, check, scalar
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import spsolve


def physics(case):
    module = importlib.import_module(case["package"])
    ip = getattr(module, case["prefix"] + "InputParameters")()
    ip.static()
    _, a = module.fill_xarray_from_input_parameters(
        ip,
        scope={
            "size": [case["size"]],
            "powertrain": [case["powertrain"]],
            "year": [case["year"]],
        },
    )
    vm = getattr(module, case["prefix"] + "Model")(a, **case["options"])
    vm.set_all()
    p = {str(name): scalar(vm[name]) for name in vm.array.parameter.values}
    e = vm.energy.sel(powertrain=case["powertrain"])
    trace = lambda name: np.asarray(e.sel(parameter=name)).ravel()
    speed = np.nan_to_num(vm.ecm.cycle[:, 0]) / 3.6
    slope = np.nan_to_num(vm.ecm.gradient[:, 0])
    acceleration = np.zeros(len(speed))
    acceleration[1:-1] = (speed[2:] - speed[:-2]) / 2
    mass = p["driving mass"]
    forces = {
        "rolling resistance": mass
        * 9.81
        * p["rolling resistance coefficient"]
        * np.cos(slope),
        "air resistance": 0.5
        * vm.ecm.rho_air
        * p["aerodynamic drag coefficient"]
        * p["frontal area"]
        * speed**2,
        "gradient resistance": mass * 9.81 * np.sin(slope),
        "kinetic energy": mass * acceleration,
    }
    total = sum(forces.values())
    expected_power = {k: force * speed / 1000 for k, force in forces.items()}
    expected_power["motive energy at wheels"] = np.maximum(total, 0) * speed / 1000
    distance = sum(speed) / 1000
    record = {"id": case["id"], "cycle_km": distance, "checks": [], "cycle_work_kJ": {}}
    # Retain the original 0.2% heavy-vehicle threshold for before/after checks.
    # The former truck stopping rule (1% of available payload) permitted the
    # final-mass residual that this independent force check exposed.
    tol = 0.002 if case["prefix"] in ["Truck", "Bus"] else 2e-5
    for name, expected in expected_power.items():
        actual = trace(name)
        record["cycle_work_kJ"][name] = {
            "model": float(sum(actual)),
            "manual": float(sum(expected)),
        }
        # Check every second, scaling error by the maximum demand rather than
        # dividing by a near-zero force at stops or a net-zero kinetic integral.
        check(
            record,
            name + " maximum trace error",
            max(abs(actual - expected)),
            0,
            "kJ per second",
            atol=max(1e-8, max(abs(expected)) * tol),
            rtol=0,
        )
    positive = sum(trace("motive energy"))
    auxiliary = sum(trace("auxiliary energy"))
    hvac = sum(
        sum(trace(name))
        for name in [
            "cooling energy",
            "heating energy",
            "battery cooling energy",
            "battery heating energy",
        ]
    )
    control = (
        sum(trace("combustion control energy"))
        if "combustion control energy" in e.parameter
        else 0
    )
    recovered = -sum(trace("recuperated energy"))
    if case["prefix"] == "TwoWheeler":
        recovered = 0
    elif p["combustion power share"] > 0:
        wheel = trace("motive energy at wheels")
        trans_work = sum(trace("transmission efficiency") * wheel)
        motor = scalar(vm.get_electric_motor_efficiency())
        recovered = min(
            positive,
            recovered * motor * trans_work / sum(wheel) * positive / sum(wheel),
        )
    elif p["fuel cell system efficiency"] > 0:
        recovered = min(positive, recovered / p["fuel cell system efficiency"])
    net = (positive + auxiliary + hvac + control - recovered) / distance
    if case["powertrain"].startswith("BEV"):
        net /= p["battery discharge efficiency"]
    check(record, "cycle integration to TtW", p["TtW energy"], net, "kJ/km")
    record["energy_balance"] = {
        "positive_input_kJ": positive,
        "auxiliary_kJ": auxiliary,
        "hvac_kJ": hvac,
        "combustion_control_kJ": control,
        "regeneration_credit_kJ": recovered,
        "ttw_manual_kJ_per_km": net,
        "ttw_model_kJ_per_km": p["TtW energy"],
    }
    # Infer the mass used by the trace from an independent rolling-work balance.
    rolling_per_kg = (
        9.81 * p["rolling resistance coefficient"] * sum(np.cos(slope) * speed) / 1000
    )
    record["trace_mass_kg"] = float(sum(trace("rolling resistance")) / rolling_per_kg)
    record["final_driving_mass_kg"] = mass
    if case["id"] == "case-10":
        # Diagnostic only: refresh the energy at the final sizing state. Do not
        # export this partly refreshed object or treat it as a second full run.
        vm.calculate_ttw_energy()
        record["ttw_after_refresh_at_final_mass_kJ_per_km"] = scalar(vm["TtW energy"])
    return record


def grouping(record, private):
    labels = json.loads((private / (record["id"] + "-labels.json")).read_text())
    z = np.load(private / (record["id"] + "-matrices.npz"))
    a, b = z["A"], z["B"]
    vehicle_type = {
        "Car": "car",
        "Truck": "truck",
        "Bus": "bus",
        "TwoWheeler": "two-wheeler",
    }[record["prefix"]]
    (transport,) = [
        i
        for i, label in enumerate(labels)
        if label[0].startswith(f"transport, {vehicle_type}, ")
    ]
    (vehicle,) = [
        i for i, label in enumerate(labels) if label[0].startswith(vehicle_type + ", ")
    ]
    groups = yaml.safe_load(
        (ROOT / "carculator_utils/data/lcia/impact_source_categories.yaml").read_text()
    )
    duplicates = []
    extra = np.zeros(b.shape[0])
    for i, label in enumerate(labels):
        matches = []
        for group, rule in groups.items():
            terms = rule if isinstance(rule, list) else rule.get("contains", [])
            exact = [] if isinstance(rule, list) else rule.get("exact", [])
            if label[0] in exact or any(term in label[0] for term in terms):
                matches.append(group)
        amount = -a[i, transport] + a[i, vehicle] * a[vehicle, transport]
        if len(matches) <= 1 or amount == 0:
            continue
        demand = np.zeros(len(a))
        demand[i] = 1
        impact = (
            b @ spsolve(csc_matrix(a), demand) * amount / record["load_per_vehicle_km"]
        )
        extra += impact * (len(matches) - 1)
        duplicates.append(
            {
                "supplier": label,
                "groups": matches,
                "climate_counted_extra": float(impact[0] * (len(matches) - 1)),
            }
        )
    core = np.array([r["core"] for r in record["impacts"]])
    manual = np.array([r["manual"] for r in record["impacts"]])
    observed = core - manual
    checks = {
        "id": record["id"],
        "duplicates": duplicates,
        "checks": [],
        "explains_all_category_differences": bool(
            np.allclose(core - extra, manual, rtol=1e-5, atol=1e-10)
        ),
        "maximum_residual": float(max(abs(observed - extra))),
    }
    if "fuel_blend" in record:
        (market,) = [
            i
            for i, label in enumerate(labels)
            if label[0].startswith("fuel supply for ") and a[i, transport] != 0
        ]
        expected = {}
        for component in record["fuel_blend"].values():
            i = labels.index(component["name"])
            expected[i] = expected.get(i, 0) + scalar(component["share"])
        for i, amount in expected.items():
            check(
                checks,
                "fuel mass fraction: " + labels[i][0],
                -a[i, market],
                amount,
                "kg/kg blend",
            )
        # Only mass-denominated technosphere inputs belong in this balance.
        # Hydrogen supply also purchases compression electricity in kWh.
        observed_total = -sum(
            a[i, market]
            for i, label in enumerate(labels)
            if i != market and len(label) == 4 and label[2] == "kilogram"
        )
        check(checks, "fuel supply total mass", observed_total, 1, "kg/kg blend")
        checks["fuel_supply_non_mass_inputs"] = [
            {"supplier": label, "amount_per_kg_blend": float(-a[i, market])}
            for i, label in enumerate(labels)
            if i != market
            and len(label) == 4
            and label[2] != "kilogram"
            and a[i, market] != 0
        ]
    p = record["parameters"]
    batteries = [
        i
        for i, label in enumerate(labels)
        if label[0].startswith("market for battery, Li-ion")
    ]
    check(
        checks,
        "battery production including replacements",
        -sum(a[i, vehicle] for i in batteries),
        p["energy battery mass"] * (1 + p["battery lifetime replacements"]),
        "kg/vehicle",
    )
    # A short, additive hand-calculation table: allocation of the complete
    # vehicle, direct exhaust, supplied energy and remaining road/maintenance
    # burdens. No source-category substring grouping is used here.
    buckets = {
        name: np.zeros(len(a))
        for name in [
            "vehicle production and replacements",
            "direct emissions",
            "fuel and electricity supply",
            "road, maintenance and other operation",
        ]
    }
    for i, label in enumerate(labels):
        if i == transport or a[i, transport] == 0:
            continue
        group = (
            "vehicle production and replacements"
            if i == vehicle
            else (
                "direct emissions"
                if len(label) == 3
                else (
                    "fuel and electricity supply"
                    if label[0].startswith(
                        ("fuel supply for ", "electricity supply for electric vehicles")
                    )
                    else "road, maintenance and other operation"
                )
            )
        )
        buckets[group][i] = -a[i, transport] / record["load_per_vehicle_km"]
    checks["manual_climate_contributions_per_fu"] = {
        name: float(b[0] @ spsolve(csc_matrix(a), demand))
        for name, demand in buckets.items()
    }
    check(
        checks,
        "sum of four manual LCIA contributions",
        sum(checks["manual_climate_contributions_per_fu"].values()),
        manual[0],
        "kg CO2-eq/FU",
    )
    return checks


def phev(case):
    """Check utility-factor weighting using retained electric/combustion modes."""
    import carculator as module

    ip = module.CarInputParameters()
    ip.static()
    _, array = module.fill_xarray_from_input_parameters(
        ip, scope={"size": [case["size"]], "powertrain": ["PHEV-p"], "year": [2025]}
    )
    vm = module.CarModel(array, drop_hybrids=False, **case["options"])
    vm.set_all()
    p = lambda mode, name: scalar(vm[name].sel(powertrain=mode))
    fraction = case["options"]["electric_utility_factor"][2025]
    result = {"id": case["id"], "electric_distance_fraction": fraction, "checks": []}
    petrol = (
        (1 - fraction)
        * p("PHEV-c-p", "TtW energy")
        / (
            1000
            * p("PHEV-c-p", "LHV fuel MJ per kg")
            * p("PHEV-c-p", "fuel density per kg")
        )
    )
    electricity = (
        fraction
        * p("PHEV-e", "TtW energy")
        / (
            3600
            * p("PHEV-e", "battery charge efficiency")
            * p("PHEV-e", "charger efficiency")
        )
    )
    check(
        result,
        "utility-weighted fuel demand",
        p("PHEV-p", "fuel consumption"),
        petrol,
        "L/km",
    )
    check(
        result,
        "utility-weighted grid demand",
        p("PHEV-p", "electricity consumption"),
        electricity,
        "kWh/km",
    )
    check(
        result,
        "utility-weighted TtW",
        p("PHEV-p", "TtW energy"),
        fraction * p("PHEV-e", "TtW energy")
        + (1 - fraction) * p("PHEV-c-p", "TtW energy"),
        "kJ/km",
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--model-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    records = json.loads(args.model_report.read_text())["cases"]
    result = {
        "physics": [],
        "source_grouping": [grouping(r, args.private_dir) for r in records],
        "scope": "Physics checks exclude aggregated PHEV modes and the repeated prospective case. Efficiency-map and HVAC outputs are inputs to the cycle energy balance.",
    }
    with contextlib.redirect_stdout(io.StringIO()):
        result["phev"] = phev(next(c for c in cases() if c["powertrain"] == "PHEV-p"))
    for case in cases():
        if case["powertrain"].startswith("PHEV") or case["scenario"] != "static":
            continue
        with contextlib.redirect_stdout(io.StringIO()):
            record = physics(case)
        result["physics"].append(record)
        print(
            case["id"],
            [c["name"] for c in record["checks"] if not c["passed"]],
            flush=True,
        )
        args.report.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
