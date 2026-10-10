"""Audit bundled HBEFA-factor propagation on completed family inventories.

This diagnoses accounting defects without recalibrating emission factors. The
reference calculation retains the existing NH3/N2O multipliers and deterioration
endpoint values and the documented linear lifetime-average deterioration policy.
Their scientific validity is not implied by a passing check.
"""

import argparse
import hashlib
import importlib
import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import yaml

from carculator_utils import DATA_DIR
from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.hot_emissions import (
    MAP_PWT,
    HotEmissionsModel,
    get_mileage_degradation_factor,
)

CASES = [
    (
        "carculator",
        "Car",
        "Medium",
        [
            "ICEV-p",
            "ICEV-d",
            "ICEV-g",
            "HEV-p",
            "HEV-d",
            "PHEV-p",
            "PHEV-d",
            "FCEV",
            "BEV",
        ],
        {},
    ),
    (
        "carculator_bus",
        "Bus",
        "13m-city",
        ["ICEV-d", "ICEV-g", "HEV-d", "FCEV", "BEV-depot"],
        {},
    ),
    (
        "carculator_truck",
        "Truck",
        "40t",
        ["ICEV-d", "ICEV-g", "HEV-d", "PHEV-d", "FCEV", "BEV"],
        {"cycle": "Long haul"},
    ),
    (
        "carculator_two_wheeler",
        "TwoWheeler",
        "Motorcycle 11-35kW",
        ["ICEV-p", "BEV"],
        {},
    ),
]
ENVIRONMENTS = {
    "urban": "urban air close to ground",
    "suburban": "non-urban air or from high stacks",
    "rural": "non-urban air or from high stacks",
}


def table(directory, filename):
    path = directory / filename
    if not path.exists():
        return None
    frame = pd.read_csv(path)
    return frame.groupby(
        [c for c in frame.columns if c != "value"], as_index=False
    ).value.mean()


def factor(frame, **selection):
    if frame is None:
        return 0.0
    for key, value in selection.items():
        if key in frame:
            frame = frame.loc[frame[key] == value]
    return float(frame.value.mean()) if len(frame) else 0.0


def audit(output):
    output.mkdir(parents=True, exist_ok=True)
    records = []
    family_results = []
    source_paths = list((DATA_DIR / "emission_factors").rglob("*.csv"))
    source_paths += list((DATA_DIR / "emission_factors").glob("*.yaml"))
    source_paths += [
        DATA_DIR.parent / filename
        for filename in ("model.py", "inventory.py", "hot_emissions.py")
    ]
    source_paths.append(Path(__file__).resolve())
    mapping = yaml.safe_load(
        (DATA_DIR / "emission_factors/exhaust_and_noise_flows.yaml").read_text()
    )["exhaust"]
    reverse = defaultdict(list)
    for component, flow in mapping.items():
        reverse[flow].append(component)

    def check(family, check_name, label, expected, actual):
        expected, actual = np.broadcast_arrays(np.asarray(expected), np.asarray(actual))
        for idx in np.ndindex(actual.shape):
            exp, act = float(expected[idx]), float(actual[idx])
            records.append(
                {
                    "family": family,
                    "check": check_name,
                    "label": label,
                    "index": str(idx),
                    "expected": exp,
                    "actual": act,
                    "passed": bool(np.isclose(act, exp, rtol=2e-6, atol=1e-15)),
                }
            )

    for name, prefix, size, powertrains, kwargs in CASES:
        package = importlib.import_module(name)
        package_dir = Path(package.__file__).parent
        source_paths += [
            package_dir / filename
            for filename in (
                "model.py",
                "inventory.py",
                "data/default_parameters.json",
                "data/extra_parameters.json",
            )
        ]
        inputs = getattr(package, prefix + "InputParameters")()
        inputs.static()
        _, array = fill_xarray_from_input_parameters(
            inputs,
            scope={
                "size": [size],
                "powertrain": powertrains,
                "year": [2020, 2025, 2030],
            },
        )
        array = array.isel(value=[0, 0]).assign_coords(value=[0, 1])
        array.loc[dict(parameter="lifetime kilometers", value=1)] *= 1.5
        array.loc[dict(parameter="kilometers per year", value=1)] *= 1.1
        model = getattr(package, prefix + "Model")(array, **kwargs)
        captured = {}
        original = HotEmissionsModel.get_hot_emissions

        def capture(hem, *args, **kw):
            result = original(hem, *args, **kw)
            captured.update(
                hem=hem,
                velocity=hem.velocity.copy(deep=True),
                arguments=deepcopy(kw),
                result=result.copy(deep=True),
            )
            return result

        with patch.object(HotEmissionsModel, "get_hot_emissions", capture):
            model.set_all()
        inventory = getattr(package, "Inventory" + prefix)(model)
        impacts = inventory.calculate_impacts()
        assert np.isfinite(impacts).all()
        family_results.append(
            {
                "family": name,
                "size": size,
                "powertrains": powertrains,
                "completed_lcia": True,
            }
        )
        hot = captured["result"]
        arguments = captured["arguments"]
        directory = DATA_DIR / "emission_factors" / model.vehicle_type
        exhaust = table(directory, "EF_HBEFA42_exhaust.csv")
        extra = table(directory, "EF_HBEFA42_non_exhaust.csv")
        degradation = table(directory, "degradation_EF.csv")
        species = table(directory, "NMHC_species.csv")

        # Independently evaluate g/MJ * kJ / 1000, add the declared cold/evap
        # terms in grams, then divide by cycle km and 1000 g/kg.
        def reference(pt, year_index, value, component):
            year = int(hot.year.values[year_index])
            selection = dict(powertrain=pt, size=size, year=year, value=value)
            energy = arguments["energy_consumption"].sel(**selection).values
            speed = captured["velocity"].sel(**selection).values
            distance = speed.sum() / 3600
            euro = arguments["euro_class"][year_index]
            keys = dict(
                powertrain=MAP_PWT[pt], size=size, euro_class=euro, component=component
            )
            grams = factor(exhaust, **keys) * energy / 1000
            multiplier = {
                "car": {"Ammonia": 0.5, "Dinitrogen oxide": 0.5},
                "bus": {"Ammonia": 1 / 12, "Dinitrogen oxide": 1 / 15},
                "truck": {"Ammonia": 10, "Dinitrogen oxide": 10},
            }
            grams *= multiplier.get(model.vehicle_type, {}).get(component, 1)
            endpoint = max(
                1,
                factor(
                    degradation, powertrain=pt, component=component, euro_class=euro
                ),
            )
            reference_km = 890000 if model.vehicle_type in ("bus", "truck") else 200000
            lifetime = float(arguments["lifetime_km"].sel(**selection))
            grams *= 1 + (endpoint - 1) * lifetime / (2 * reference_km)
            yearly = float(arguments["yearly_km"].sel(**selection))
            grams[0] += (
                factor(extra, **keys, type="cold start") * distance * 2.3 * 365 / yearly
            )
            grams[-1] += (
                factor(extra, **keys, type="soak") * distance * 2.3 * 365 / yearly
            )
            grams += (
                distance
                / len(grams)
                * (
                    factor(extra, **keys, type="diurnal") * 365 / yearly
                    + factor(extra, **keys, type="running losses")
                )
            )
            return (
                np.array(
                    [
                        grams[speed <= 50].sum(),
                        grams[(speed > 50) & (speed <= 80)].sum(),
                        grams[speed > 80].sum(),
                    ]
                )
                / distance
                / 1000
            )

        for pt in hot.powertrain.values:
            # Aggregate PHEVs are placeholders here, constructed after hot emissions.
            if pt in ("PHEV-p", "PHEV-d"):
                continue
            for yi, year in enumerate(hot.year.values):
                for value in hot.value.values:
                    selection = dict(powertrain=pt, size=size, year=year, value=value)
                    for component in [
                        "Carbon monoxide",
                        "Nitrogen oxides",
                        "Particulate matters 2.5",
                        "Ammonia",
                        "Dinitrogen oxide",
                        "Methane",
                    ]:
                        actual = [
                            float(hot.sel(**selection, component=f"{component}, {env}"))
                            for env in ENVIRONMENTS
                        ]
                        check(
                            name,
                            "coefficient_to_hot_output",
                            f"{pt}/{year}/{value}/{component}",
                            reference(pt, yi, value, component),
                            actual,
                        )
                    parent = reference(pt, yi, value, "Non-methane hydrocarbon").sum()
                    names = list(species.component.unique()) + [
                        "Non-methane hydrocarbon"
                    ]
                    total = sum(
                        float(hot.sel(**selection, component=f"{c}, {env}"))
                        for c in names
                        for env in ENVIRONMENTS
                    )
                    check(
                        name,
                        "nmhc_mass_conservation",
                        f"{pt}/{year}/{value}",
                        parent,
                        total,
                    )

        # Passenger-car documentation specifies the degradation factor at
        # half the vehicle lifetime, starting at unity for a new vehicle.
        if model.vehicle_type == "car":
            correction = get_mileage_degradation_factor(
                arguments["lifetime_km"],
                arguments["euro_class"],
                hot.powertrain.values,
                model.vehicle_type,
            )
            for pt in ("ICEV-p", "ICEV-d"):
                for yi, euro in enumerate(arguments["euro_class"]):
                    endpoint = max(
                        1,
                        factor(
                            degradation,
                            powertrain=pt,
                            component="Nitrogen oxides",
                            euro_class=euro,
                        ),
                    )
                    lifetime = (
                        arguments["lifetime_km"]
                        .sel(size=size, powertrain=pt)
                        .isel(year=yi)
                    )
                    expected = 1 + (endpoint - 1) * lifetime.values / (2 * 200000)
                    actual = correction.sel(
                        size=size, powertrain=pt, component="Nitrogen oxides"
                    ).isel(year=yi)
                    check(
                        name,
                        "documented_mileage_degradation",
                        f"{pt}/{hot.year.values[yi]}/NOx",
                        expected,
                        actual,
                    )

        # Compare labelled hot-model output with the completed vehicle. For
        # PHEVs reproduce only the documented electric-utility weighting.
        for pt in powertrains:
            selection = dict(size=size, powertrain=pt)
            if pt.startswith("PHEV-"):
                uf = model["electric utility factor"].sel(**selection)
                reference_hot = (
                    hot.sel(size=size, powertrain=pt.replace("PHEV-", "PHEV-c-"))
                    * (1 - uf)
                    + hot.sel(size=size, powertrain="PHEV-e") * uf
                )
            else:
                reference_hot = hot.sel(**selection)
            for component in hot.component.values:
                substance, env = component.rsplit(", ", 1)
                substance = {
                    "Hydrocarbon": "Hydrocarbons",
                    "Particulate matters 2.5": "Particulate matters",
                    "PAHs": "PAH, polycyclic aromatic hydrocarbons",
                    "PAH polycyclic aromatic hydrocarbons": "PAH, polycyclic aromatic hydrocarbons",
                }.get(substance, substance)
                parameter = f"{substance} direct emissions, {env}"
                check(
                    name,
                    "hot_output_to_vehicle",
                    f"{pt}/{parameter}",
                    reference_hot.sel(component=component).transpose("year", "value"),
                    model[parameter].sel(**selection).transpose("year", "value"),
                )
            (column,) = inventory.find_input_indices(
                (f"transport, {model.vehicle_type}, ", f", {pt},", size)
            )
            # HC is the total of methane and NMHC, not a chlorinated species.
            # Check independently of the YAML mapping, which excludes aggregates.
            for env, compartment in ENVIRONMENTS.items():
                row = inventory.inputs[
                    ("Hydrocarbons, chlorinated", ("air", compartment), "kilogram")
                ]
                check(
                    name,
                    "no_duplicate_total_hydrocarbons",
                    f"{pt}/{env}",
                    0,
                    -inventory.A[:, row, column, :],
                )
            for flow, components in reverse.items():
                for compartment in set(ENVIRONMENTS.values()):
                    environments = [
                        env
                        for env, mapped in ENVIRONMENTS.items()
                        if mapped == compartment
                    ]
                    expected = sum(
                        model[f"{c} direct emissions, {env}"].sel(**selection)
                        for env in environments
                        for c in components
                    )
                    row = inventory.inputs[(flow, ("air", compartment), "kilogram")]
                    check(
                        name,
                        "vehicle_to_inventory",
                        f"{pt}/{flow}/{' + '.join(environments)}",
                        expected.transpose("year", "value"),
                        -inventory.A[:, row, column, :].T,
                    )
                old = inventory.inputs[
                    (flow, ("air", "low population density, long-term"), "kilogram")
                ]
                check(
                    name,
                    "no_delayed_rural_exhaust",
                    f"{pt}/{flow}",
                    0,
                    -inventory.A[:, old, column, :],
                )
            if MAP_PWT[pt] != "BEV":
                energy = captured["arguments"]["energy_consumption"]
                if pt.startswith("PHEV-"):
                    energy = energy.sel(
                        size=size, powertrain=pt.replace("PHEV-", "PHEV-c-")
                    ) * (1 - model["electric utility factor"].sel(**selection))
                    expected = model["TtW energy, combustion mode"].sel(**selection) * (
                        1 - model["electric utility factor"].sel(**selection)
                    )
                else:
                    energy = energy.sel(**selection)
                    expected = model["TtW energy"].sel(**selection)
                distance = (
                    model.energy.sel(**selection, parameter="velocity").sum("second")
                    / 1000
                )
                check(
                    name,
                    "emission_energy_vs_fuel_energy",
                    pt,
                    expected.transpose("year", "value"),
                    (energy.sum("second") / distance).transpose("year", "value"),
                )

    frame = pd.DataFrame(records)
    frame.to_csv(output / "checks.csv", index=False)
    summary = {
        "families": family_results,
        "checks": [
            {"check": kind, "tested": len(group), "failed": int((~group.passed).sum())}
            for kind, group in frame.groupby("check")
        ],
        "colliding_inventory_mappings": {
            flow: components
            for flow, components in reverse.items()
            if len(components) > 1
        },
        "scope": "Bundled-factor propagation; not independent validation against licensed HBEFA source data.",
        "source_sha256": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source_paths
        },
        "failure_examples": {
            kind: group.head(4).to_dict(orient="records")
            for kind, group in frame.loc[~frame.passed].groupby("check")
        },
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return not frame.passed.all()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(int(audit(parser.parse_args().output)))
