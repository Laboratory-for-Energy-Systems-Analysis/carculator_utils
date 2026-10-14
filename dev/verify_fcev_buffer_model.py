"""Independently check final Regional-delivery FCEV power and energy balances."""

import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for package in ("carculator_utils", "carculator_truck"):
    sys.path.insert(0, str(ROOT.parent / package))

from carculator_truck import (
    TruckInputParameters,
    TruckModel,
    fill_xarray_from_input_parameters,
)
from audit_premise_vehicle_workbooks import write_csv

WORK = Path("/private/tmp/premise-fcev-buffer-20261014")
OUT = ROOT / "results/premise_fcev_buffer_20261014"


def main():
    with (WORK / "trucks/vehicle_parameters.csv").open() as stream:
        installed = {
            r["size"]: r for r in csv.DictReader(stream) if r["powertrain"] == "FCEV"
        }
    inputs = TruckInputParameters()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={"size": sorted(installed), "powertrain": ["FCEV"], "year": [2020]},
    )
    model = TruckModel(array, country="CH", cycle="Regional delivery")
    model.set_all()
    rows = []
    for z, size in enumerate(model.array.coords["size"].values):
        cell = model.array.sel(size=size, powertrain="FCEV", year=2020, value=0)
        p = lambda k: float(cell.sel(parameter=k))
        trace = model.energy.sel(size=size, powertrain="FCEV", year=2020, value=0)
        t = lambda k: np.asarray(trace.sel(parameter=k), float)
        a = lambda k: np.asarray(getattr(model.ecm, k)[:, 0, 0, 0, z], float)
        for k in (
            "TtW energy",
            "electric energy stored",
            "energy battery mass",
            "battery power",
            "curb mass",
            "cargo mass",
        ):
            np.testing.assert_allclose(p(k), float(installed[size][k]), rtol=2e-6)
        demand = t("motive energy at wheels") / t("transmission efficiency") / t(
            "engine efficiency"
        ) + a("auxiliary_dc_demand_kw")
        stack = p("fuel cell power") / p("fuel cell own consumption")
        capacity = p("electric energy stored")
        discharge = np.maximum(demand - stack, 0)
        charge = a("regenerative_charge_dc_kw")
        direct = a("regenerative_auxiliary_dc_kw")
        generator = a("regenerative_generator_dc_kw")
        spill = a("regenerative_curtailed_dc_kw")
        eta_c, eta_d, eta_fc = (
            p(k)
            for k in (
                "battery charge efficiency",
                "battery discharge efficiency",
                "fuel cell system efficiency",
            )
        )
        assert discharge.max() <= capacity * 2 * (1 + 3e-6)
        assert p("battery power") <= capacity * 6 * (1 + 3e-6)
        assert charge.max() <= capacity * 36 / 25 * (1 + 3e-6)
        np.testing.assert_allclose(generator, direct + charge + spill, atol=1e-5)
        np.testing.assert_allclose(
            -t("recuperated energy"), charge * eta_c * eta_d, rtol=3e-6, atol=1e-5
        )
        np.testing.assert_allclose(
            t("auxiliary energy") * eta_fc + direct,
            a("auxiliary_dc_demand_kw"),
            atol=1e-5,
        )
        distance = t("velocity").sum() / 1000
        recovered = min(charge.sum() * eta_c * eta_d / eta_fc, t("motive energy").sum())
        expected = (
            t("motive energy").sum() + t("auxiliary energy").sum() - recovered
        ) / distance
        np.testing.assert_allclose(p("TtW energy"), expected, rtol=2e-6)
        np.testing.assert_allclose(
            p("energy battery mass"), capacity * 238 / 25, rtol=2e-6
        )
        assert a("power_deficit_kw").max() == 0
        assert p("cargo mass") <= p("available payload")
        np.testing.assert_allclose(
            p("fuel mass") * 120000 / p("TtW energy"), 400, rtol=3e-6
        )
        rows.append(
            dict(
                size=str(size),
                year=2020,
                nominal_kwh=capacity,
                pack_kg=p("energy battery mass"),
                curb_kg=p("curb mass"),
                cargo_kg=p("cargo mass"),
                available_payload_kg=p("available payload"),
                motor_kw=p("electric power"),
                peak_shaft_kw=float(a("shaft_power_demand_kw").max()),
                net_stack_kw=stack,
                required_rated_buffer_kw=p("battery power"),
                peak_cycle_discharge_kw=float(discharge.max()),
                continuous_discharge_kw=capacity * 2,
                peak_charge_kw=float(charge.max()),
                continuous_charge_kw=capacity * 36 / 25,
                curtailed_regeneration_fraction=float(spill.sum() / generator.sum()),
                direct_auxiliary_regeneration_kwh_per_km=float(
                    direct.sum() / 3600 / distance
                ),
                ttw_kj_km=p("TtW energy"),
                hydrogen_kg_100km=p("TtW energy") / 1200,
                brake_recovery_proxy=p("share recuperated energy"),
                range_km=400,
            )
        )
    write_csv(OUT / "model_screen.csv", rows)
    (OUT / "model_screen_summary.json").write_text(
        json.dumps(
            dict(
                checked=len(rows),
                year=2020,
                cycle="Regional delivery",
                range_km=400,
                installed_parameters_match=True,
                continuous_cycle_power_pass=True,
                regenerated_dc_balance_pass=True,
                fuel_energy_balance_pass=True,
                pack_mass_pass=True,
                payload_pass=True,
                motor_cycle_pass=True,
                boundary="Conditioned-pack proxy; not SOC, thermal, ageing or FC-ramp validation. Full motor requirement is checked against the 10-second rating, not indefinite power.",
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
