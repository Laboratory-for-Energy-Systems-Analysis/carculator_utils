"""Separate truck boundary/route sensitivities from documented dynamometer loads.

Uses full model construction without changing production code or class defaults.
The A+B*v+C*v² laboratory force is injected through a time-varying equivalent
rolling coefficient with aerodynamic drag zeroed. It is NOT a tire coefficient.
"""

import argparse
import copy
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import numpy as np
import xarray as xr

from carculator_utils.energy_consumption import EnergyConsumptionModel
from validate_energy_2025 import provenance, run_case

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/_static/energy_validation_2025/expanded"
LBF = 4.4482216152605
MPH = 0.44704
LOADS = {
    "smith": dict(
        A=97.41,
        B=-7e-14,
        C=0.1071,
        source="https://calstart.org/wp-content/uploads/2018/10/Battery-Electric-Parcel-Delivery-Truck-Testing-and-Demonstration.pdf",
        source_sha256="9a51db5d07a543f4442ae6080a121a35c359685bbe56c1b1439bb00defcd4540",
        locator="Appendix B printed p15, PDF p143, Table 4",
        note="Calculated road load from frontal-area method, not an independently measured coastdown",
    ),
    "mt45": dict(
        A=147.70,
        B=-1.35,
        C=0.100,
        source="https://docs.nlr.gov/docs/fy11osti/48896.pdf",
        source_sha256="65c2fcc9dd7dda88a660c84de23617071a0be97efee4fb2b5808814d6933c01b",
        locator="Printed p33, Vehicle Simulation",
        note="Laboratory road-load curve derived from local approximate coastdowns and prior coefficients",
    ),
}


@contextmanager
def instrument(diagnostics, road_load=None, flat=False, aux_off=False):
    original = EnergyConsumptionModel.motive_energy_per_km

    def wrapped(ecm, driving_mass, *args, **kwargs):
        assert not args, "Expected keyword energy inputs"
        if aux_off:
            kwargs["aux_power"] = xr.zeros_like(kwargs["aux_power"])
            kwargs["hvac_power"] = None
        gradient = ecm.gradient.copy()
        if flat:
            ecm.gradient = np.zeros_like(gradient)
        velocity = ecm.velocity.reshape(len(ecm.velocity), -1)[:, 0]
        if road_load:
            assert (
                np.max(np.abs(ecm.gradient)) == 0
            ), "Laboratory load is for a flat dynamometer"
            mass = float(driving_mass.item())
            mph = velocity / MPH
            force = (
                road_load["A"] + road_load["B"] * mph + road_load["C"] * mph**2
            ) * LBF
            assert np.all(force >= 0)
            kwargs["rr_coef"] = xr.DataArray(force / (mass * 9.81), dims=["second"])
            kwargs["drag_coef"] = xr.zeros_like(kwargs["drag_coef"])
        try:
            result = original(ecm, driving_mass, **kwargs)
        finally:
            ecm.gradient = gradient
        energy = result.squeeze(drop=True)
        distance = velocity.sum() / 1000
        if road_load:
            actual = energy.sel(parameter="rolling resistance").values
            assert np.allclose(
                actual, force * velocity / 1000, rtol=1e-9, atol=1e-8
            ), "Road-load force adapter mismatch"
            assert np.allclose(energy.sel(parameter="air resistance"), 0)
        if aux_off:
            assert np.allclose(energy.sel(parameter="auxiliary energy"), 0)
        record = {
            name: float(energy.sel(parameter=name).sum()) / distance / 36
            for name in [
                "rolling resistance",
                "air resistance",
                "gradient resistance",
                "kinetic energy",
                "motive energy at wheels",
                "motive energy",
                "recuperated energy",
                "auxiliary energy",
            ]
        }
        record["units"] = (
            "kWh/100 km; signed component work, not additive positive traction shares"
        )
        record["actual_active_seconds"] = int(np.count_nonzero(ecm.driving_time))
        diagnostics.clear()
        diagnostics.update(record)
        return result

    with patch.object(EnergyConsumptionModel, "motive_energy_per_km", wrapped):
        yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "logs").mkdir()
    speed = args.output / "steady_80.csv"
    np.savetxt(
        speed,
        np.c_[np.arange(3600), np.full(3600, 80.0)],
        delimiter=",",
        header="time_s,speed_kmh",
        comments="",
        fmt="%.6f",
    )
    catalog = json.loads((DATA / "measurements.json").read_text())
    old = json.loads((DATA / "calibrated_2025/runs.json").read_text())
    rows = []
    cases = [
        "eactros_tour_mean",
        "volvo_green_truck",
        "calstart_smith_ocbc_dc",
        "nrel_mt45_diesel_ocbc",
        "nrel_mt45_diesel_nycc_x3",
    ]
    for case in cases:
        observation = next(r for r in catalog["observations"] if r["id"] == case)
        dataset = catalog["datasets"][observation["dataset_id"]]
        config = copy.deepcopy(dataset["model_comparison"])
        config["cycle"] = observation.get("model_cycle", config["cycle"])
        config.update(copy.deepcopy(observation.get("model_overrides", {})))
        if config["size"] == "40t":
            variants = [
                "baseline",
                "flat_same_speed",
                "rolling_minus_20pct",
                "drag_minus_20pct",
                "auxiliaries_off",
                "steady_80_flat",
            ]
        elif case.startswith("calstart"):
            variants = ["baseline", "source_road_load"]
        else:
            variants = ["baseline", "source_road_load", "source_load_no_hybrid"]
        for variant in variants:
            options = copy.deepcopy(config)
            load = None
            flat = variant == "flat_same_speed"
            if variant == "rolling_minus_20pct":
                options["factors"] = {"rolling resistance coefficient": 0.8}
            if variant == "drag_minus_20pct":
                options["factors"] = {"aerodynamic drag coefficient": 0.8}
            if variant == "steady_80_flat":
                options.update(
                    cycle_profile=str(speed.resolve()),
                    cycle_label="Steady 80 km/h flat; diagnostic, not a measured route",
                )
            if variant.startswith("source_"):
                load = LOADS["smith" if case.startswith("calstart") else "mt45"]
            if variant == "source_load_no_hybrid":
                options.setdefault("inputs", {}).update(
                    {"combustion power share": 1.0, "electric motor power share": 0.0}
                )
            diagnostic = {}
            with instrument(diagnostic, load, flat, variant == "auxiliaries_off"):
                result = run_case(args.output, case + "_" + variant, **options)
            assert result["eligible_for_comparison"]
            assert abs(result["driving mass"] - config["target_driving_mass"]) < 0.1
            assert (
                abs(
                    result["energy_input_driving_mass_kg"]
                    - config["target_driving_mass"]
                )
                < 0.1
            )
            if variant == "baseline":
                previous = next(r for r in old if r["case"] == case)
                assert abs(result["TtW energy"] - previous["TtW energy"]) < 1e-5
            rows.append(
                dict(
                    observation_id=case,
                    variant=variant,
                    reported=observation["value"],
                    unit=observation["unit"],
                    boundary=dataset.get("charging_losses"),
                    source_url=dataset["source_url"],
                    source_road_load=load,
                    diagnostics=diagnostic,
                    run=result,
                )
            )
    meta = provenance()
    meta.update(
        road_loads=LOADS,
        road_load_units="A lbf, B lbf/mph, C lbf/mph²; SI force uses mph=v_mps/0.44704 and lbf=4.4482216152605 N",
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        catalog_sha256=hashlib.sha256(
            (DATA / "measurements.json").read_bytes()
        ).hexdigest(),
        interpretation="Heavy truck +/-20% road-load and flat/steady tests are unfitted diagnostics, not measured vehicle calibration. Laboratory road-load substitutions retain 2025 technology unless explicitly disabling the diesel hybrid share.",
    )
    (args.output / "provenance.json").write_text(json.dumps(meta, indent=2) + "\n")
    (args.output / "runs.json").write_text(json.dumps(rows, indent=2) + "\n")
    for row in rows:
        r = row["run"]
        print(
            row["observation_id"],
            row["variant"],
            "DC",
            r["battery_terminal_kWh_100km"],
            "AC",
            r["electricity_kWh_100km"],
            "fuel",
            r["fuel_L_100km"],
        )


if __name__ == "__main__":
    main()
