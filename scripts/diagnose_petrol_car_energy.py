"""Diagnose the mass-matched Golf petrol comparison without fitting defaults.

Full WLTC runs vary one assumption at a time. Per-second accounting separates
stops, moving non-traction and traction. No ADAC electric trace is substituted
for the distinct combustion-vehicle protocol.
"""

import argparse
import copy
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import numpy as np

from carculator_utils.energy_consumption import EnergyConsumptionModel
from validate_energy_2025 import provenance, run_case

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/_static/energy_validation_2025/expanded"


@contextmanager
def capture(holder):
    original = EnergyConsumptionModel.motive_energy_per_km

    def wrapped(ecm, driving_mass, *args, **kwargs):
        result = original(ecm, driving_mass, *args, **kwargs)
        holder["energy"] = result.squeeze(drop=True).copy(deep=True)
        holder["active"] = ecm.driving_time.ravel().astype(bool)
        holder["aux_W"] = float(kwargs["aux_power"].item())
        return result

    with patch.object(EnergyConsumptionModel, "motive_energy_per_km", wrapped):
        yield


def accounting(holder, run):
    energy = holder["energy"]
    get = lambda name: energy.sel(parameter=name).values.ravel()
    v = get("velocity")
    active = holder["active"]
    traction = get("motive energy at wheels") > 0
    masks = {
        "traction": active & traction,
        "moving_nontraction": active & ~traction & (v > 0),
        "stopped": active & (v == 0),
    }
    assert np.array_equal(
        sum(m.astype(int) for m in masks.values()), active.astype(int)
    )
    conversion = run["LHV fuel MJ per kg"] * run["fuel density per kg"] * 10
    distance = v.sum() / 1000
    components = ["motive energy", "auxiliary energy", "motive energy at wheels"]
    states = {}
    for label, mask in masks.items():
        states[label] = {
            "seconds": int(mask.sum()),
            "distance_km": float(v[mask].sum() / 1000),
            "fuel_equivalent_L_per_100km_whole_cycle": {
                name: float(get(name)[mask].sum() / distance / conversion)
                for name in components[:2]
            },
            "auxiliary_service_kJ": float(holder["aux_W"] * mask.sum() / 1000),
        }
    # Exact partition of the full trace, not separate phase model runs.
    phases = {}
    for name, lo, hi in [
        ("low", 0, 590),
        ("medium", 590, 1023),
        ("high", 1023, 1478),
        ("extra_high", 1478, 1801),
    ]:
        length = v[lo:hi].sum() / 1000
        phases[name] = {
            "seconds_slice": [lo, hi],
            "distance_km": float(length),
            "fuel_before_regeneration_L_100km": float(
                sum(get(c)[lo:hi].sum() for c in components[:2]) / length / conversion
            ),
        }
    fuel_before_credit = (
        sum(get(c).sum() for c in components[:2]) / distance / conversion
    )
    assert np.isclose(
        fuel_before_credit,
        sum(
            sum(s["fuel_equivalent_L_per_100km_whole_cycle"].values())
            for s in states.values()
        ),
    )
    if run["electric power"] == 0:
        assert np.isclose(fuel_before_credit, run["fuel_L_100km"], atol=1e-8)
    return dict(
        states=states,
        wltc_phases=phases,
        fuel_before_regeneration_L_100km=float(fuel_before_credit),
        regeneration_credit_L_100km=float(fuel_before_credit - run["fuel_L_100km"]),
        note="WLTC phases are not ADAC urban/rural/motorway results; auxiliary fuel includes effective low-load engine losses, not only incremental accessory fuel.",
    )


def control_probe(ecm, driving_mass, original, holder, mode, *args, **kwargs):
    """Idealized service-balanced probe, not a calibrated engine controller.

    Stops borrow auxiliary energy from a buffer; traction repays it with 75%
    round-trip efficiency. Optional overrun funding uses braking mechanical
    energy, with 80% reverse transmission efficiency and a 0 or 5 kW reserve.
    No restart fuel, gear/RPM thresholds, thermal veto or buffer capacity model.
    """
    reference = original(ecm, driving_mass, *args, **kwargs)
    trace = reference.squeeze(drop=True)
    get = lambda name: trace.sel(parameter=name).values.ravel()
    active = ecm.driving_time.ravel().astype(bool)
    stopped = active & (get("velocity") == 0)
    traction = active & (get("motive energy at wheels") > 0)
    service = float(kwargs["aux_power"].item()) / 1000  # kW
    available = -get("negative motive energy") * 0.8
    reserve = 5.0 if mode.endswith("reserve5kw") else 0.0
    overrun = active & (get("velocity") > 0) & (available >= service + reserve)
    if mode == "stop_start_probe":
        overrun[:] = False
    schedule = np.ones_like(active, dtype=float)
    schedule[stopped | overrun] = 0
    repayment_kJ = service * stopped.sum() / 0.75
    schedule[traction] += repayment_kJ / (traction.sum() * service)
    fuel_funded = float((schedule * active).sum() * service)
    kinetic_funded = float(overrun.sum() * service)
    delivered = float(active.sum() * service)
    buffer_loss = float(repayment_kJ - stopped.sum() * service)
    assert np.isclose(fuel_funded + kinetic_funded, delivered + buffer_loss)
    assert np.all(available[overrun] >= service + reserve)
    original_aux = EnergyConsumptionModel.aux_energy_per_km

    def scheduled_aux(instance, *a, **kw):
        result = original_aux(instance, *a, **kw)
        assert not isinstance(
            result, tuple
        ), "This probe only supports the car auxiliary path"
        return result * schedule.reshape((-1,) + (1,) * (result.ndim - 1))

    with patch.object(EnergyConsumptionModel, "aux_energy_per_km", scheduled_aux):
        result = original(ecm, driving_mass, *args, **kwargs)
    final = result.squeeze(drop=True)
    assert np.allclose(
        final.sel(parameter="motive energy at wheels"),
        trace.sel(parameter="motive energy at wheels"),
    )
    assert np.allclose(
        final.sel(parameter="auxiliary energy").values.ravel()[stopped | overrun], 0
    )
    holder["control"] = dict(
        engine_off_stop_seconds=int(stopped.sum()),
        fuel_cut_seconds=int(overrun.sum()),
        buffer_round_trip_efficiency=0.75,
        reverse_transmission_efficiency=0.8,
        mechanical_reserve_kW=reserve,
        auxiliary_service_kJ=delivered,
        engine_funded_service_and_buffer_losses_kJ=fuel_funded,
        kinetic_funded_service_kJ=kinetic_funded,
        buffer_loss_kJ=buffer_loss,
        caveat="Engineering sensitivity, not Golf ECU calibration; absent restart fuel, RPM/gear thresholds, thermal constraints and finite buffer sizing",
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "logs").mkdir()
    catalog = json.loads((DATA / "measurements.json").read_text())
    config = catalog["datasets"]["adac_golf_petrol"]["model_comparison"]
    previous = next(
        r
        for r in json.loads((DATA / "calibrated_2025/runs.json").read_text())
        if r["case"] == "golf_combined"
    )
    variants = [
        "baseline",
        "no_hybrid",
        "transmission_90pct",
        "transmission_95pct",
        "rolling_minus_20pct",
        "drag_minus_20pct",
        "source_drag_coefficient",
        "auxiliary_half",
        "mass_minus_75kg",
        "mass_plus_75kg",
        "stop_start_probe",
        "stop_start_overrun_probe",
        "stop_start_overrun_reserve5kw",
    ]
    rows = []
    for variant in variants:
        options = copy.deepcopy(config)
        # All sensitivities after baseline start with the documented nonhybrid configuration.
        if variant != "baseline":
            options["inputs"].update(
                {"combustion power share": 1.0, "electric motor power share": 0.0}
            )
        if variant.startswith("transmission_"):
            options["transmission_efficiency"] = (
                0.9 if variant == "transmission_90pct" else 0.95
            )
        if variant == "rolling_minus_20pct":
            options["factors"] = {"rolling resistance coefficient": 0.8}
        if variant == "source_drag_coefficient":
            options["inputs"]["aerodynamic drag coefficient"] = 0.28
        if variant == "drag_minus_20pct":
            options["factors"] = {"aerodynamic drag coefficient": 0.8}
        if variant.startswith("mass_"):
            delta = -75 if variant == "mass_minus_75kg" else 75
            options["inputs"]["cargo mass"] += delta
            options["target_driving_mass"] += delta
        holder = {}
        # Hook the actual energy input for this diagnostic; input demand is derived by set_all().
        original = EnergyConsumptionModel.motive_energy_per_km

        def auxiliary_probe(ecm, driving_mass, *a, **kw):
            if variant == "auxiliary_half":
                kw["aux_power"] = kw["aux_power"] * 0.5
            if variant.startswith("stop_start"):
                return control_probe(
                    ecm, driving_mass, original, holder, variant, *a, **kw
                )
            return original(ecm, driving_mass, *a, **kw)

        with (
            patch.object(
                EnergyConsumptionModel, "motive_energy_per_km", auxiliary_probe
            ),
            capture(holder),
        ):
            run = run_case(args.output, "golf_" + variant, **options)
        assert run["eligible_for_comparison"] and run["cap_active_seconds"] == 0
        assert (
            abs(run["energy_input_driving_mass_kg"] - options["target_driving_mass"])
            < 0.1
        )
        if variant == "baseline":
            assert abs(run["TtW energy"] - previous["TtW energy"]) < 1e-5
        if variant != "baseline":
            assert run["electric power"] == 0
        # Capture records incoming power before the auxiliary hook.
        if variant == "auxiliary_half":
            holder["aux_W"] *= 0.5
        detail = accounting(holder, run)
        if "control" in holder:
            detail["control_probe"] = holder["control"]
        holder["energy"].isel(second=holder["active"]).to_pandas().to_csv(
            args.output / (variant + "_trace.csv"), float_format="%.8g"
        )
        rows.append(dict(variant=variant, run=run, accounting=detail))
        print(variant, run["fuel_L_100km"], flush=True)
    meta = provenance()
    meta.update(
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        catalog_sha256=hashlib.sha256(
            (DATA / "measurements.json").read_bytes()
        ).hexdigest(),
        interpretation="All WLTC, not matched ADAC cycles. Probes after no_hybrid vary one assumption from no_hybrid. No fit or production default change.",
        adac_combined_L_100km=5.6,
        sources={
            "test_report": "https://assets.adac.de/image/upload/Autodatenbank/Autotest/at6463-vw-golf-15-tsi-life/vw-golf-15-tsi-life.pdf",
            "test_report_locators": "p8 start-stop; p13 mass, 85 kW, manual gearbox, Cd=0.28 and consumption",
            "protocol": "https://assets.adac.de/image/upload/v1721027897/ADAC-eV/KOR/Text/PDF/ecotest-methodik-ab-04-2021_pg5juw.pdf",
            "control_context": "https://www.epa.gov/sites/default/files/2017-06/documents/sae-2017-01-0533-characterizing-factors-influencing-si-engine-transient-fuel-consumption-alpha.pdf",
        },
        adac_source=catalog["datasets"]["adac_golf_petrol"]["source_url"],
    )
    (args.output / "runs.json").write_text(json.dumps(rows, indent=2) + "\n")
    (args.output / "provenance.json").write_text(json.dumps(meta, indent=2) + "\n")


if __name__ == "__main__":
    main()
