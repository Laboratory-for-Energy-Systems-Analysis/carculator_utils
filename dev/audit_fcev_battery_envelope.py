"""Screen current truck FCEV buffers against a documented reference pack.

Read-only, offline audit: the reference is NOT an approved model default.
The May 2021 AKASOL OEM 37 PRC sheet is an explicit candidate proxy for
2020, not evidence that all 2020 NMC batteries have these specifications.
No pulse-recovery, SOC, temperature or ageing certification is implied.
"""

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from audit_premise_fcev_power import storage_lower_bound

ROOT = Path(__file__).resolve().parents[1]
for package in ("carculator_utils", "carculator_truck"):
    sys.path.insert(0, str(ROOT.parent / package))

from carculator_truck import TruckInputParameters, TruckModel
from carculator_utils.array import fill_xarray_from_input_parameters

REFERENCE = {
    "name": "AKASOL AKASYSTEM 15 OEM 37 PRC",
    "edition": "May 2021; unapproved candidate proxy for model year 2020",
    "url": "https://www.act-news.com/wp-content/uploads/2020/11/"
    "210525_LowRes_AK_Datenblatt_AKASystem_15-OEM-37-PRC_2021_2159x2794mm_EN.pdf",
    "earlier_brochure_url": "https://bus-news.com/wp-content/uploads/sites/4/"
    "2020/07/AKASOL-Bus-Applications-Brochure.pdf",
    "nominal_kwh": 25.0,
    "pack_kg": 238.0,
    "charge_continuous_kw": 36.0,
    "charge_10s_kw": 86.0,
    "discharge_rms_kw": 50.0,
    "discharge_10s_kw": 150.0,
    "qualification": "Ratings depend on SOC, temperature and integration. "
    "RMS rating has no averaging/recovery interval in this sheet. "
    "NMC stoichiometry and internal cell mass fraction are not specified. "
    "The earlier brochure reports the same product, 24.5 kWh, about 238 kg, "
    "37-50 kW continuous and 75-150 kW peak, without separate charge limits.",
}


def longest_run(mask):
    """Count consecutive one-second samples, without joining cycle boundaries."""
    edges = np.diff(np.r_[False, np.asarray(mask, bool), False].astype(int))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    return int((ends - starts).max(initial=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    installed_path = ROOT.parent / (
        "premise/premise/data/additional_inventories/lci-trucks.parameters.csv"
    )
    with installed_path.open() as stream:
        installed = {
            row["size"]: row
            for row in csv.DictReader(stream)
            if row["powertrain"] == "FCEV"
        }
    inputs = TruckInputParameters()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={"size": sorted(installed), "powertrain": ["FCEV"], "year": [2020]},
    )
    model = TruckModel(array, country="CH", cycle="Regional delivery")
    model.set_all()
    rows, traces = [], {}
    for size in sorted(installed, key=lambda x: float(x.removesuffix("t"))):
        selection = dict(size=size, powertrain="FCEV", year=2020, value=0)
        cell = model.array.sel(selection)
        p = lambda name: float(cell.sel(parameter=name))
        trace = model.energy.sel(selection)
        t = lambda name: np.asarray(trace.sel(parameter=name), float)
        for name in (
            "electric energy stored",
            "energy battery mass",
            "battery power",
            "TtW energy",
        ):
            np.testing.assert_allclose(p(name), float(installed[size][name]), rtol=2e-6)
        eta_c, eta_d = p("battery charge efficiency"), p("battery discharge efficiency")
        eta_fc = p("fuel cell system efficiency")
        demand = (t("motive energy") + t("auxiliary energy")) * eta_fc
        generation = -t("recuperated energy") / (eta_c * eta_d)
        np.testing.assert_allclose(
            demand,
            t("motive energy at wheels")
            / t("transmission efficiency")
            / t("engine efficiency")
            + t("auxiliary energy") * eta_fc,
            rtol=2e-6,
            atol=1e-5,
        )
        net_fc = p("fuel cell power") / p("fuel cell own consumption")
        # Best case: stack instantly supplies its full net rating when needed,
        # and regenerative electricity may directly supply simultaneous demand.
        discharge = np.maximum(demand - generation - net_fc, 0)
        charge = np.maximum(generation - demand, 0)
        capacity = p("electric energy stored")
        scale = capacity / REFERENCE["nominal_kwh"]
        charge_cont = scale * REFERENCE["charge_continuous_kw"]
        charge_peak = scale * REFERENCE["charge_10s_kw"]
        discharge_rms = scale * REFERENCE["discharge_rms_kw"]
        discharge_peak = scale * REFERENCE["discharge_10s_kw"]
        # Frozen-vehicle sensitivity only: curtail generator output above the
        # reference's continuous charging limit plus simultaneous DC demand.
        # Preserve the existing model's round-trip convention to isolate this
        # one effect. This is not a full controller or a regenerated vehicle.
        curtailed = np.maximum(generation - demand - charge_cont, 0)
        distance = float(t("velocity").sum() / 1000)
        positive_fuel = float(t("motive energy").sum())
        current_credit = min(
            float(generation.sum()) * eta_c * eta_d / eta_fc, positive_fuel
        )
        limited_credit = min(
            float((generation - curtailed).sum()) * eta_c * eta_d / eta_fc,
            positive_fuel,
        )
        penalty = (current_credit - limited_credit) / distance
        # Unlimited-power storage lower bound after limiting regenerative
        # inflow only. FC-to-battery charging is still unlimited in this bound.
        usable_bound = storage_lower_bound(
            demand, generation - curtailed, net_fc, eta_c, eta_d
        )
        row = dict(
            size=size,
            year=2020,
            cycle="Regional delivery",
            nominal_kwh=capacity,
            current_pack_kg=p("energy battery mass"),
            reference_pack_kg_at_same_capacity=scale * REFERENCE["pack_kg"],
            recorded_buffer_kw=p("battery power"),
            peak_cycle_discharge_dc_kw=float(discharge.max()),
            cycle_discharge_rms_dc_kw=float(np.sqrt(np.mean(discharge**2))),
            peak_generator_dc_kw=float(generation.max()),
            peak_net_regenerative_charge_dc_kw=float(charge.max()),
            reference_charge_continuous_kw=charge_cont,
            reference_charge_10s_kw=charge_peak,
            reference_discharge_rms_kw=discharge_rms,
            reference_discharge_10s_kw=discharge_peak,
            seconds_charge_above_continuous=int((charge > charge_cont).sum()),
            longest_charge_above_continuous_s=longest_run(charge > charge_cont),
            seconds_charge_above_10s_max=int((charge > charge_peak).sum()),
            seconds_discharge_above_rms_rating=int((discharge > discharge_rms).sum()),
            longest_discharge_above_rms_rating_s=longest_run(discharge > discharge_rms),
            seconds_discharge_above_10s_max=int((discharge > discharge_peak).sum()),
            current_ttw_kj_km=p("TtW energy"),
            frozen_mass_continuous_charge_cap_penalty_kj_km=penalty,
            frozen_mass_continuous_charge_cap_penalty_percent=100
            * penalty
            / p("TtW energy"),
            curtailed_generator_energy_fraction=float(
                curtailed.sum() / generation.sum()
            ),
            optimistic_usable_kwh_after_regen_limit=usable_bound,
            declared_battery_dod=p("battery DoD"),
        )
        rows.append(row)
        traces[size] = dict(
            demand_dc_kw=demand.tolist(),
            generator_dc_kw=generation.tolist(),
            minimum_battery_discharge_dc_kw=discharge.tolist(),
            net_regenerative_charge_dc_kw=charge.tolist(),
        )
    with (args.output / "envelope_screen.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (args.output / "reference.json").write_text(json.dumps(REFERENCE, indent=2) + "\n")
    (args.output / "traces.json").write_text(json.dumps(traces) + "\n")
    manifest = dict(
        interpreter=sys.executable,
        python=sys.version,
        numpy=np.__version__,
        installed_parameters=str(installed_path),
        installed_parameters_sha256=hashlib.sha256(
            installed_path.read_bytes()
        ).hexdigest(),
        sources={
            str(path.relative_to(ROOT.parent)): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in (
                Path(__file__),
                ROOT / "carculator_utils/model.py",
                ROOT / "carculator_utils/energy_consumption.py",
                ROOT.parent / "carculator_truck/carculator_truck/model.py",
                ROOT.parent
                / "carculator_truck/carculator_truck/data/default_parameters.json",
            )
        },
        commits={
            repo.name: subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repo, text=True
            ).strip()
            for repo in (
                ROOT,
                ROOT.parent / "carculator_truck",
                ROOT.parent / "premise",
            )
        },
        scope="Read-only reference screening. No model defaults, inventories or databases changed.",
    )
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
