"""Trace missing truck HEV storage and screen cycle-buffer requirements.

Read-only diagnostic: the source model and installed inventories are unchanged.
The buffer screen is an optimistic regenerative-only energy balance, not a
calibrated hybrid controller, a selected battery design, or a lifetime model.
"""

import contextlib
import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np

from audit_premise_vehicle_workbooks import write_csv

ROOT = Path(__file__).resolve().parents[1]
for package in ("carculator_utils", "carculator_truck"):
    sys.path.insert(0, str(ROOT.parent / package))

from carculator_truck import (
    InventoryTruck,
    TruckInputParameters,
    TruckModel,
    fill_xarray_from_input_parameters,
)

OUT = ROOT / "results/premise_truck_hev_storage_20261013"


def buffer_screen(charge, discharge_opportunity, usable_capacity):
    """Stored kWh per one-second interval; use recovered energy at first chance.

    Warm up to a periodic cycle, so the last braking event can supply the next
    cycle. Discharge is limited by wheel demand, electric motor power and energy
    already in the buffer. Capacity clips charging. No engine charging, external
    electricity or battery-specific current/temperature constraints are added.
    """
    stored = 0.0
    for iteration in range(100):
        initial = stored
        maximum = accepted = delivered = spilled = 0.0
        for incoming, opportunity in zip(charge, discharge_opportunity):
            accepted_now = min(incoming, max(usable_capacity - stored, 0))
            accepted += accepted_now
            spilled += incoming - accepted_now
            stored += accepted_now
            maximum = max(maximum, stored)
            discharge = min(stored, opportunity)
            stored -= discharge
            delivered += discharge
        if abs(stored - initial) < 1e-10:
            break
    else:
        raise AssertionError("Diagnostic buffer did not reach a periodic state")
    assert np.isclose(accepted, delivered, rtol=1e-9, atol=1e-9)
    return {
        "maximum_stored_kWh": maximum,
        "accepted_stored_kWh": accepted,
        "discharged_stored_kWh": delivered,
        "curtailed_stored_kWh": spilled,
    }


def main():
    OUT.mkdir(exist_ok=True)
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
        inventory = InventoryTruck(model, functional_unit="vkm", scenario="static")
    rows = []
    for size in model.array["size"].values:
        for year in model.array.year.values:
            cell = model.array.sel(size=size, powertrain="HEV-d", year=year, value=0)
            value = lambda label: float(cell.sel(parameter=label))
            trace = model.energy.sel(size=size, powertrain="HEV-d", year=year, value=0)
            distance = float(trace.sel(parameter="velocity").sum("second")) / 1000
            eta_motor = float(
                model.get_electric_motor_efficiency().sel(
                    size=size, powertrain="HEV-d", year=year, value=0
                )
            )
            eta_discharge = value("battery discharge efficiency")
            regenerated_dc = -trace.sel(parameter="recuperated energy").values
            charge = regenerated_dc / eta_discharge / 3600
            positive_wheel_power = trace.sel(parameter="motive energy at wheels").values
            transmission = trace.sel(parameter="transmission efficiency").values
            shaft = np.divide(
                positive_wheel_power,
                transmission,
                out=np.zeros_like(positive_wheel_power),
                where=transmission > 0,
            )
            discharge_opportunity = (
                np.minimum(shaft, value("electric power"))
                / eta_motor
                / eta_discharge
                / 3600
            )
            assert np.isfinite(charge).all() and (charge >= 0).all()
            assert np.isfinite(discharge_opportunity).all()
            assert (discharge_opportunity >= 0).all()
            unlimited = buffer_screen(charge, discharge_opportunity, np.inf)
            column = inventory.inputs[(f"truck, HEV-d, {size}", "CH", "unit", "truck")]
            yi = inventory.scope["year"].index(year)
            packs = [
                idx
                for label, idx in inventory.inputs.items()
                if label[0].startswith("market for battery, Li-ion,")
            ]
            disposal = inventory.inputs[
                (
                    "market for used Li-ion battery",
                    "GLO",
                    "kilogram",
                    "used Li-ion battery",
                )
            ]
            (starter,) = inventory.find_input_indices(("lead acid battery, for lorry",))
            row = {
                "size": size,
                "year": int(year),
                "electric_motor_kW": value("electric power"),
                "starter_power_kW": value("battery power"),
                "nominal_traction_kWh": value("electric energy stored"),
                "traction_pack_kg": value("energy battery mass"),
                "reported_cell_mass_kg": value("battery cell mass"),
                "reported_bop_mass_kg": value("battery BoP mass"),
                "starter_cell_power_density_kW_per_kg": value(
                    "battery cell power density"
                ),
                "minimum_dc_discharge_kW_for_full_motor": value("electric power")
                / eta_motor,
                "modeled_regenerated_stored_kWh_per_km": float(charge.sum()) / distance,
                "unconstrained_screen_required_usable_kWh": unlimited[
                    "maximum_stored_kWh"
                ],
                "cycle_distance_km": distance,
                "cycle_peak_charge_stored_kW": float(charge.max()) * 3600,
                "lifetime_km": value("lifetime kilometers"),
                "cycle_life_EFC": value("battery cycle life"),
                "model_replacements": value("battery lifetime replacements"),
                "lci_li_ion_supply_kg": float(-inventory.A[0, packs, column, yi].sum()),
                "lci_li_ion_disposal_kg": float(inventory.A[0, disposal, column, yi]),
                "lci_lead_acid_supply_kg": float(-inventory.A[0, starter, column, yi]),
                "ttw_kJ_per_km": value("TtW energy"),
                "curb_mass_kg": value("curb mass"),
                "driving_mass_kg": value("driving mass"),
                "energy_battery_cost_EUR": value("energy battery cost"),
                "power_battery_cost_EUR": value("power battery cost"),
            }
            # 2/4/8 kWh are sensitivity windows, not selected nominal packs.
            for window in (2, 4, 8):
                case = buffer_screen(charge, discharge_opportunity, window)
                row[f"screen_{window}kWh_usable_curtailed_fraction"] = case[
                    "curtailed_stored_kWh"
                ] / float(charge.sum())
            rows.append(row)
    write_csv(OUT / "native_hev_storage.csv", rows)
    source = [
        ROOT / "carculator_utils/model.py",
        ROOT / "carculator_utils/energy_consumption.py",
        ROOT / "carculator_utils/inventory.py",
        ROOT.parent / "carculator_truck/carculator_truck/model.py",
        ROOT.parent / "carculator_truck/carculator_truck/inventory.py",
        ROOT.parent / "carculator_truck/carculator_truck/data/default_parameters.json",
        Path(__file__),
    ]
    record = {
        "source_sha256": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source
        },
        "cases": len(rows),
        "settings": "Regional delivery, CH, native 2020/2050 defaults; no Premise transformation",
        "screen_boundary": buffer_screen.__doc__,
        "no_model_or_inventory_changes": True,
    }
    (OUT / "provenance.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
