"""Read-only BEV sizing probe: separate mass feedback from the IAM target.

Runs 2020 source models at a smaller pack and the approved NMC-622 density.
No inventory is installed. Candidate engineering changes are diagnostics only.
"""

import contextlib
import hashlib
import io
import json
import pickle
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
for name in ("carculator_utils", "carculator", "carculator_truck"):
    sys.path.insert(0, str(ROOT / name))

from carculator import CarInputParameters, CarModel
from carculator_truck import TruckInputParameters, TruckModel
from carculator_utils.array import fill_xarray_from_input_parameters

OUT = ROOT / "carculator_utils/results/premise_vehicle_range_20261013"
BASELINE = Path("/private/tmp/premise-vehicle-efficiency-20261013/2050/database.pickle")
DENSITIES = ROOT / "premise/premise/data/battery/energy_density.yaml"
ENGINEERING = (
    "rolling resistance coefficient",
    "aerodynamic drag coefficient",
    "electric motor efficiency",
    "electric transmission efficiency",
)


def main():
    density = yaml.safe_load(DENSITIES.read_text())["NMC622"]["target"][2050]["mean"]
    with BASELINE.open("rb") as handle:
        database = pickle.load(handle)
    factors = {
        d["name"]: d.get("log parameters", {}).get("efficiency change", 1)
        for d in database
        if d["location"] == "EUR"
    }
    del database
    rows = []
    for kind, size, inputs_cls, model_cls, name in (
        (
            "truck",
            "40t",
            TruckInputParameters,
            TruckModel,
            "transport, freight, lorry, battery electric, 40 metric ton",
        ),
        (
            "car",
            "Large",
            CarInputParameters,
            CarModel,
            "transport, passenger car, battery electric, Large",
        ),
    ):
        inputs = inputs_cls()
        inputs.static()
        _, full = fill_xarray_from_input_parameters(
            inputs, scope={"size": [size], "powertrain": ["BEV"], "year": [2020, 2050]}
        )
        original = full.sel(year=[2020])
        options = {"country": "CH"}
        if kind == "truck":
            options["cycle"] = "Regional delivery"
        else:
            options["starts_per_day"] = 1.8

        def run(array, **kwargs):
            with contextlib.redirect_stdout(io.StringIO()):
                model = model_cls(array, **options, **kwargs)
                model.set_all()
            return model

        baseline = run(original)
        val = lambda m, p: float(m[p].item())
        factor = factors[name]
        capacity = val(baseline, "electric energy stored") * factor
        target = val(baseline, "TtW energy") * factor
        modified = original.copy(deep=True)
        modified.loc[dict(parameter="battery cell energy density, NMC-622")] = density
        packs = {"capacity": {("BEV", size, 2020): capacity}}
        resized = run(modified, energy_storage=packs)
        # A native future engineering package is a diagnostic candidate, not
        # an approved replacement for the IAM energy-intensity target.
        future = modified.copy(deep=True)
        parameters = {}
        for parameter in ENGINEERING:
            if parameter not in full.parameter:
                continue
            a = float(full.sel(year=2020, parameter=parameter).item())
            b = float(full.sel(year=2050, parameter=parameter).item())
            parameters[parameter] = {"2020": a, "2050": b}
            future.loc[dict(parameter=parameter)] = b
        projected = run(future, energy_storage=packs)
        full_future = full.sel(year=[2050]).assign_coords(year=[2020]).copy(deep=True)
        full_future.loc[dict(parameter="battery cell energy density, NMC-622")] = (
            density
        )
        # Keep duty, lifetime, load and depth of discharge on the approved
        # baseline while testing the native future hardware/energy assumptions.
        for parameter in (
            "lifetime kilometers",
            "kilometers per year",
            "cargo mass",
            "average passengers",
            "average passenger mass",
            "battery DoD",
            "target range",
            "battery cycle life, NMC-622",
        ):
            if parameter in full.parameter:
                full_future.loc[dict(parameter=parameter)] = original.sel(
                    parameter=parameter
                )
        native_future = run(full_future, energy_storage=packs)
        selected = (
            "electric energy stored",
            "energy battery mass",
            "curb mass",
            "driving mass",
            "electric power",
            "TtW energy",
            "electricity consumption",
            "engine efficiency",
            "transmission efficiency",
            "battery DoD",
            "battery charge efficiency",
            "battery discharge efficiency",
            "charger efficiency",
            "auxiliary power demand",
        )
        cases = {}
        for label, model in (
            ("baseline_2020", baseline),
            ("resized_only", resized),
            ("resized_with_native_2050_engineering", projected),
            ("resized_with_native_2050_hardware", native_future),
        ):
            cases[label] = {p: val(model, p) for p in selected}
            cases[label]["actual range km"] = (
                val(model, "electric energy stored")
                * val(model, "battery DoD")
                * 3600
                / val(model, "TtW energy")
            )
            if kind == "truck":
                for p in ("cargo mass", "available payload", "is_compliant"):
                    cases[label][p] = val(model, p)
        rows.append(
            dict(
                family=kind,
                name=name,
                iam_energy_factor=factor,
                target_stored_energy_kJ_per_km=target,
                engineering_inputs=parameters,
                cases=cases,
            )
        )
    OUT.mkdir(exist_ok=True, parents=True)
    (OUT / "engineering_probe.json").write_text(json.dumps(rows, indent=2) + "\n")
    sources = [
        Path(__file__),
        DENSITIES,
        ROOT / "carculator/carculator/model.py",
        ROOT / "carculator_truck/carculator_truck/model.py",
        ROOT / "carculator_utils/carculator_utils/model.py",
        ROOT / "carculator_utils/carculator_utils/energy_consumption.py",
    ]
    (OUT / "probe_sources.json").write_text(
        json.dumps(
            {
                "python": sys.version,
                "source_sha256": {
                    str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
                },
                "private_scenario": str(BASELINE),
                "private_scenario_sha256": hashlib.sha256(
                    BASELINE.read_bytes()
                ).hexdigest(),
                "diagnostic_only": True,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
