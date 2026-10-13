"""Record the corrected native 2020/2050 HEV specifications beside the baseline."""

import contextlib
import csv
import io
import sys
from pathlib import Path

from audit_premise_vehicle_workbooks import write_csv

ROOT = Path(__file__).resolve().parents[1]
for package in ("carculator_utils", "carculator_truck"):
    sys.path.insert(0, str(ROOT.parent / package))

from carculator_truck import (
    TruckInputParameters,
    TruckModel,
    fill_xarray_from_input_parameters,
)


def main():
    output = ROOT / "results/premise_truck_hev_storage_20261013"
    parameters = TruckInputParameters()
    parameters.static()
    _, array = fill_xarray_from_input_parameters(
        parameters,
        scope={
            "size": ["3.5t", "7.5t", "18t", "26t", "32t", "40t", "60t"],
            "powertrain": ["HEV-d"],
            "year": [2020, 2050],
        },
    )
    with contextlib.redirect_stdout(io.StringIO()):
        model = TruckModel(array, cycle="Regional delivery")
        model.set_all()
    with (output / "native_hev_storage.csv").open() as stream:
        old = {(r["size"], int(r["year"])): r for r in csv.DictReader(stream)}
    rows = []
    for size in model.array["size"].values:
        for year in model.array.year.values:
            cell = model.array.sel(size=size, powertrain="HEV-d", year=year).isel(
                value=0
            )
            value = lambda label: float(cell.sel(parameter=label))
            balance = model.hybrid_buffer_results[
                (size, year, model.array.value.values[0])
            ]
            row = dict(
                size=size,
                year=int(year),
                nominal_kWh=value("electric energy stored"),
                physical_pack_kg=value("energy battery mass"),
                starter_kg=value("starter battery mass"),
                motor_kW=value("electric power"),
                replacements=value("battery lifetime replacements"),
                cycle_life_EFC=value("battery cycle life"),
                ttw_kJ_per_km=value("TtW energy"),
                curb_mass_kg=value("curb mass"),
                brake_wear_kg_per_km=value("brake wear emissions"),
                battery_cost_with_markup_EUR=value("energy battery cost"),
                regeneration_reuse_fraction=balance["discharged_dc_kwh"]
                / balance["unconstrained_reusable_dc_kwh"],
                stored_discharge_kWh_per_km=balance["discharged_stored_kwh_per_km"],
                fuel_increase_percent=100
                * (
                    value("TtW energy") / float(old[(size, int(year))]["ttw_kJ_per_km"])
                    - 1
                ),
                is_available=value("is_available"),
                is_compliant=value("is_compliant"),
            )
            assert row["is_available"] == row["is_compliant"] == 1
            assert abs(balance["charged_kwh"] - balance["discharged_kwh"]) < 1e-8
            rows.append(row)
    write_csv(output / "updated_native_hev_storage.csv", rows)
    print(f"Verified {len(rows)} native model cases")


if __name__ == "__main__":
    main()
