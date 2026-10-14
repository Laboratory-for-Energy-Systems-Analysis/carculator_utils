"""Check the installed car pack references, cycle energy, and native EF LCIA."""

import csv
import json
from pathlib import Path

import numpy as np
from audit_car_fcev_buffer import csv_write, digest, inspect_model
from carculator import (
    CarInputParameters,
    CarModel,
    InventoryCar,
    fill_xarray_from_input_parameters,
)

from carculator_utils.model import VehicleModel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/premise_car_fcev_buffer_20261014"


def verify_sizing_roundoff(inputs, sizes):
    """Isolate the extra sizing iteration using the preceding shared pack hook."""

    class CountedCar(CarModel):
        def iterate_sizing(self, *args, **kwargs):
            for iteration in super().iterate_sizing(*args, **kwargs):
                self.last_iteration = iteration
                yield iteration

    class PreviousPack(CountedCar):
        set_fuel_cell_mass = VehicleModel.set_fuel_cell_mass

        def check_fuel_cell_battery_power(self):
            # The old generic reference predates the Mirai power specification.
            pass

    _, array = fill_xarray_from_input_parameters(
        inputs, scope={"size": sorted(sizes), "year": [2020]}
    )
    models = []
    for cls in (PreviousPack, CountedCar):
        model = cls(array, country="CH", starts_per_day=1.8, drop_hybrids=False)
        model.set_all()
        models.append(model)
    powers = [p for p in models[0].array.powertrain.values if p != "FCEV"]
    # Cost markups are sampled independently; compare physical quantities.
    fields = [
        "TtW energy",
        "electric energy stored",
        "curb mass",
        "driving mass",
        "range",
        "fuel consumption",
        "battery power",
    ]
    old, new = [m.array.sel(powertrain=powers, parameter=fields).values for m in models]
    np.testing.assert_allclose(old, new, rtol=5e-7, atol=0)
    difference = np.divide(
        abs(new - old), abs(old), out=np.zeros_like(old), where=old != 0
    )
    return {
        "old_iterations": models[0].last_iteration,
        "new_iterations": models[1].last_iteration,
        "max_non_fcev_relative_difference": float(difference.max()),
        "fields": fields,
    }


def main():
    parameters = (
        ROOT.parent
        / "premise/premise/data/additional_inventories"
        / "lci-pass_cars.parameters.csv"
    )
    installed = {
        r["size"]: r
        for r in csv.DictReader(parameters.open())
        if r["powertrain"] == "FCEV"
    }
    assert len(installed) == 8
    inputs = CarInputParameters()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={"size": sorted(installed), "powertrain": ["FCEV"], "year": [2020]},
    )
    model = CarModel(array, country="CH", starts_per_day=1.8)
    model.set_all()
    rows = inspect_model(model, "installed_mirai_calibration", "mirai", None)
    for row in rows:
        original = installed[row["size"]]
        for output, field in (
            ("nominal_kwh", "electric energy stored"),
            ("pack_kg", "energy battery mass"),
            ("ttw_kj_km", "TtW energy"),
        ):
            np.testing.assert_allclose(row[output], float(original[field]), rtol=3e-6)
    csv_write(OUT / "model_cycle_checks.csv", rows)
    # A fresh, small native LCIA, with bundled background and no Brightway import.
    _, small = fill_xarray_from_input_parameters(
        inputs, scope={"size": ["Medium"], "powertrain": ["FCEV"], "year": [2020]}
    )
    case = CarModel(small, country="CH", starts_per_day=1.8)
    case.set_all()
    inventory = InventoryCar(
        case, scenario="static", method="ef", functional_unit="vkm"
    )
    result = inventory.calculate_impacts()
    assert np.isfinite(result.values).all()
    roundoff = verify_sizing_roundoff(inputs, installed)
    (OUT / "model_verification.json").write_text(
        json.dumps(
            {
                "installed_sizes_checked": len(rows),
                "dc_energy_and_fuel_balances_pass": True,
                "reference_pack_pairs_pass": True,
                "native_EF_finite": True,
                "native_EF_shape": list(result.shape),
                "non_FCEV_float32_roundoff": roundoff,
                "native_EF_boundary": "Bundled static background; separate from full Premise EF 3.1 comparison.",
                "parameters_sha256": digest(parameters),
                "script_sha256": digest(Path(__file__)),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
