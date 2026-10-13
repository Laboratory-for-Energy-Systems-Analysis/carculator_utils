"""Trace Regional-delivery PHEV battery use without changing model assumptions."""

import csv
import json
import math
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

WORK = Path("/private/tmp/premise-vehicle-replacements-20261013")
OUT = ROOT / "results/premise_vehicle_replacements_20261013"


def main():
    inputs = TruckInputParameters()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={
            "size": ["3.5t", "7.5t", "18t", "26t", "32t", "40t", "60t"],
            "powertrain": ["PHEV-d"],
            "year": [2020],
        },
    )
    model = TruckModel(array, cycle="Regional delivery", drop_hybrids=False)
    model.set_all()
    with (WORK / "baseline/lci-trucks.parameters.csv").open() as stream:
        previous = {
            r["size"]: r for r in csv.DictReader(stream) if r["powertrain"] == "PHEV-d"
        }
    rows = []
    for size in array.coords["size"].values:
        cell = model.array.sel(size=size, year=2020, value=0)
        val = lambda name, pt="PHEV-e": float(cell.sel(parameter=name, powertrain=pt))
        lifetime, annual = val("lifetime kilometers"), val("kilometers per year")
        capacity, cycles, share = (
            val("electric energy stored"),
            val("battery cycle life"),
            val("electric utility factor"),
        )
        energy = val("TtW energy") / 3600
        equivalent_cycles = lifetime * share * energy / capacity
        expected = min(max(equivalent_cycles / cycles - 1, 0), 3)
        actual = val("battery lifetime replacements", "PHEV-d")
        assert math.isclose(expected, actual, abs_tol=2e-6)
        recuperation, recovered_work_share = {}, {}
        for pt in ("PHEV-e", "PHEV-c-d"):
            trace = model.energy.sel(size=size, powertrain=pt, year=2020, value=0)
            distance = float(trace.sel(parameter="velocity").sum("second")) / 1000
            recovered_dc = -float(
                trace.sel(parameter="recuperated energy").sum("second")
            )
            positive_wheels = float(
                trace.sel(parameter="motive energy at wheels").sum("second")
            )
            mean_transmission = (
                float(
                    (
                        trace.sel(parameter="transmission efficiency")
                        * trace.sel(parameter="motive energy at wheels")
                    ).sum("second")
                )
                / positive_wheels
            )
            motor_efficiency = float(
                model.get_electric_motor_efficiency().sel(
                    size=size, powertrain=pt, year=2020, value=0
                )
            )
            recovered_work_share[pt] = (
                recovered_dc * motor_efficiency * mean_transmission / positive_wheels
            )
            # Combustion fuel credit is capped at positive propulsion demand.
            # Only the recovered electricity actually reused belongs in this
            # discharge sensitivity; the default Regional cases do not hit it.
            if pt == "PHEV-c-d":
                recovered_dc /= max(1, recovered_work_share[pt])
            recuperation[pt] = (
                recovered_dc / distance / 3600 / val("battery discharge efficiency")
            )
        # Diagnostic only: add energy cycled through the modelled regenerative
        # path in both modes, assuming the physical pack's discharge efficiency.
        # This is not a calibrated gross-throughput or calendar-ageing model.
        additional = lifetime * (
            share * recuperation["PHEV-e"] + (1 - share) * recuperation["PHEV-c-d"]
        )
        gross_sensitivity = equivalent_cycles + additional / capacity
        rows.append(
            dict(
                size=size,
                lifetime_km=lifetime,
                annual_km=annual,
                vehicle_lifetime_years=lifetime / annual,
                electric_utility_factor=share,
                electric_mode_stored_kWh_per_km=energy,
                installed_kWh=capacity,
                cycle_life_EFC=cycles,
                model_equivalent_full_cycles=equivalent_cycles,
                old_replacements=float(previous[size]["battery lifetime replacements"]),
                corrected_replacements=actual,
                lifetime_purchase_kWh=capacity * (1 + actual),
                electric_mode_recycled_stored_kWh_per_km=recuperation["PHEV-e"],
                combustion_mode_recycled_stored_kWh_per_km=recuperation["PHEV-c-d"],
                combustion_regeneration_fraction_of_positive_work=recovered_work_share[
                    "PHEV-c-d"
                ],
                recuperation_sensitivity_EFC=gross_sensitivity,
                recuperation_sensitivity_replacements=min(
                    max(gross_sensitivity / cycles - 1, 0), 3
                ),
            )
        )
    write_csv(OUT / "truck_replacement_inputs.csv", rows)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
