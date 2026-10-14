"""Audit 2020 FCEV car packs and run explicitly hypothetical pack sensitivities.

Uses source models without changing defaults, installed inventories or databases.
Reference-pack scaling is a candidate proxy, not a measured vehicle design.
Charge limits are diagnostic assumptions, never inferred from discharge ratings.
"""

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = {
    "mirai": {
        "nominal_kwh": 310.8 * 4 / 1000,
        "pack_kg": 44.6,
        "discharge_kw": 31.5,
        "duration_seconds": 10,
        "source": "Toyota second-generation Mirai announcement, 30 November 2020",
        "url": "https://newsroom.toyota.eu/introducing-the-all-new-toyota-mirai/",
        "qualification": "Late-2020 launch; charging and continuous output unspecified.",
    },
    "nexo": {
        "nominal_kwh": 1.56,
        "pack_kg": 51.2,
        "discharge_kw": 40,
        "duration_seconds": None,
        "source": "Hyundai 2020 Australian emergency guide and 2018 launch specification",
        "url": "https://www.hyundai.com/content/dam/hyundai/au/en/documents/NEXO_Emergency_Response_Guide_Australia_2020.pdf",
        "power_url": "https://www.hyundai.news/uk/articles/press-releases/nexo-the-next-generation-fuel-cell-vehicle-from-hyundai.html",
        "qualification": "Power duration and charge limit unspecified; market variants differ.",
    },
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_write(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def maximum_event_energy(power_kw):
    """Largest uninterrupted charging event in a one-second trace, in kWh.

    Does not account for simultaneous fuel-cell charging or an SOC controller.
    """
    best = current = 0.0
    for value in power_kw:
        current = current + value if value > 1e-8 else 0.0
        best = max(best, current)
    return best / 3600


def prototype_class(base):
    """Keep experimental pack choices confined to this offline subclass."""

    class CandidateCar(base):
        def __init__(self, *args, profile=None, charge_ratio=None, **kwargs):
            self.audit_profile = profile
            self.audit_charge_ratio = charge_ratio
            super().__init__(*args, **kwargs)

        def set_fuel_cell_mass(self):
            super().set_fuel_cell_mass()
            if self.audit_profile is None:
                return
            reference = REFERENCES[self.audit_profile]
            selection = dict(powertrain="FCEV")
            power = self["battery power"].sel(**selection)
            share = self["battery cell mass share"].sel(**selection)
            factor = power / reference["discharge_kw"]
            pack = factor * reference["pack_kg"]
            capacity = factor * reference["nominal_kwh"]
            for parameter, value in {
                "energy battery mass": pack,
                "battery cell mass": pack * share,
                "battery BoP mass": pack * (1 - share),
                "electric energy stored": capacity,
                "battery cell energy density": capacity / (pack * share),
                "battery cell power density": power / (pack * share),
            }.items():
                self.array.loc[dict(parameter=parameter, **selection)] = value

        def calculate_ttw_energy(self):
            if self.audit_charge_ratio is None:
                return super().calculate_ttw_energy()
            original = self.ecm.motive_energy_per_km
            limit = self["battery power"] * self.audit_charge_ratio

            def constrained(*args, **kwargs):
                return original(*args, battery_charge_power=limit, **kwargs)

            with patch.object(self.ecm, "motive_energy_per_km", constrained):
                return super().calculate_ttw_energy()

    return CandidateCar


def inspect_model(model, variant, profile, ratio):
    rows = []
    for index, size in enumerate(model.array.coords["size"].values):
        selection = dict(size=size, powertrain="FCEV", year=2020, value=0)
        cell = model.array.sel(selection)
        p = lambda name: float(cell.sel(parameter=name))
        trace = model.energy.sel(selection)
        t = lambda name: np.asarray(trace.sel(parameter=name), float)
        a = lambda name: np.asarray(getattr(model.ecm, name)[:, 0, 0, 0, index], float)
        eta_c, eta_d, eta_fc = [
            p(name)
            for name in (
                "battery charge efficiency",
                "battery discharge efficiency",
                "fuel cell system efficiency",
            )
        ]
        generator = a("regenerative_generator_dc_kw")
        direct = a("regenerative_auxiliary_dc_kw")
        charge = a("regenerative_charge_dc_kw")
        curtailed = a("regenerative_curtailed_dc_kw")
        auxiliary = a("auxiliary_dc_demand_kw")
        demand = (
            t("motive energy at wheels")
            / t("transmission efficiency")
            / t("engine efficiency")
            + auxiliary
        )
        stack = p("fuel cell power") / p("fuel cell own consumption")
        np.testing.assert_allclose(generator, direct + charge + curtailed, atol=1e-5)
        np.testing.assert_allclose(
            -t("recuperated energy"), charge * eta_c * eta_d, atol=1e-5, rtol=3e-6
        )
        np.testing.assert_allclose(
            t("auxiliary energy") * eta_fc + direct, auxiliary, atol=1e-5
        )
        np.testing.assert_allclose(
            t("motive energy") * eta_fc + auxiliary, demand, atol=1e-5, rtol=3e-6
        )
        distance = t("velocity").sum() / 1000
        recovered = min(charge.sum() * eta_c * eta_d / eta_fc, t("motive energy").sum())
        expected_fuel = (
            t("motive energy").sum() + t("auxiliary energy").sum() - recovered
        ) / distance
        np.testing.assert_allclose(p("TtW energy"), expected_fuel, rtol=3e-6)
        np.testing.assert_allclose(
            p("energy battery mass"), p("battery cell mass") + p("battery BoP mass")
        )
        np.testing.assert_allclose(
            p("electric energy stored"),
            p("battery cell mass") * p("battery cell energy density"),
            rtol=3e-6,
        )
        if profile:
            reference = REFERENCES[profile]
            scale = p("battery power") / reference["discharge_kw"]
            np.testing.assert_allclose(
                [p("electric energy stored"), p("energy battery mass")],
                [scale * reference["nominal_kwh"], scale * reference["pack_kg"]],
                rtol=3e-6,
            )
        if ratio is not None:
            assert charge.max() <= p("battery power") * ratio * (1 + 3e-6)
        np.testing.assert_allclose(
            p("electric power") / p("electric motor efficiency") + auxiliary.max(),
            stack + p("battery power"),
            rtol=3e-6,
        )
        assert a("power_deficit_kw").max() == 0
        rows.append(
            dict(
                variant=variant,
                size=str(size),
                nominal_kwh=p("electric energy stored"),
                pack_kg=p("energy battery mass"),
                rated_buffer_kw=p("battery power"),
                motor_kw=p("electric power"),
                net_stack_kw=stack,
                curb_kg=p("curb mass"),
                cycle_peak_dc_kw=float(demand.max()),
                cycle_minimum_peak_buffer_kw=float(np.maximum(demand - stack, 0).max()),
                generator_peak_kw=float(generator.max()),
                net_regen_peak_before_limit_kw=float(
                    np.maximum(generator - auxiliary, 0).max()
                ),
                charge_peak_kw=float(charge.max()),
                hypothetical_charge_ratio=ratio,
                curtailed_fraction=float(curtailed.sum() / generator.sum()),
                largest_regen_event_kwh=maximum_event_energy(charge * eta_c),
                ten_second_rated_discharge_kwh=p("battery power") * 10 / 3600 / eta_d,
                hydrogen_kg_100km=p("TtW energy") / p("LHV fuel MJ per kg") / 10,
                ttw_kj_km=p("TtW energy"),
                range_km=p("range"),
                lifetime_replacements=p("battery lifetime replacements"),
                battery_dod=p("battery DoD"),
                pack_balance_pass=True,
                dc_balance_pass=True,
                fuel_balance_pass=True,
            )
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    for package in ("carculator_utils", "carculator"):
        sys.path.insert(0, str(ROOT.parent / package))
    from audit_premise_vehicle_workbooks import read_workbook
    from carculator import (
        CarInputParameters,
        CarModel,
        fill_xarray_from_input_parameters,
    )

    folder = ROOT.parent / "premise/premise/data/additional_inventories"
    parameters = folder / "lci-pass_cars.parameters.csv"
    workbook = folder / "lci-pass_cars.xlsx"
    with parameters.open() as stream:
        installed = {
            row["size"]: row
            for row in csv.DictReader(stream)
            if row["powertrain"] == "FCEV"
        }
    before = {str(path): digest(path) for path in (parameters, workbook)}
    inputs = CarInputParameters()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={"size": sorted(installed), "powertrain": ["FCEV"], "year": [2020]},
    )
    candidate = prototype_class(CarModel)
    variants = [
        ("installed_baseline", None, None),
        ("mirai_pack_only", "mirai", None),
        ("nexo_pack_only", "nexo", None),
        ("mirai_charge_0.5_diagnostic", "mirai", 0.5),
        ("mirai_charge_1.0_diagnostic", "mirai", 1.0),
        ("mirai_direct_aux_only_diagnostic", "mirai", 1e6),
    ]
    rows, templates = [], []
    for variant, profile, ratio in variants:
        print("RUN", variant, flush=True)
        model = candidate(
            array, country="CH", starts_per_day=1.8, profile=profile, charge_ratio=ratio
        )
        model.set_all()
        current = inspect_model(model, variant, profile, ratio)
        rows.extend(current)
        if variant != "installed_baseline":
            continue
        for size, record in installed.items():
            cell = model.array.sel(size=size, powertrain="FCEV", year=2020, value=0)
            for field in (
                "electric energy stored",
                "energy battery mass",
                "battery power",
                "TtW energy",
                "curb mass",
                "fuel cell power",
            ):
                np.testing.assert_allclose(
                    float(cell.sel(parameter=field)), float(record[field]), rtol=3e-6
                )
        for ds in read_workbook(workbook)[0]:
            name = ds["name"]
            if not name.startswith("Passenger car, fuel cell electric, "):
                continue
            size = name.removeprefix("Passenger car, fuel cell electric, ")
            record = installed[size]
            batteries = [e for e in ds["exchanges"] if "battery" in e["name"].lower()]
            purchases = [
                e
                for e in batteries
                if e["name"].startswith("market for battery capacity")
            ]
            assert len(purchases) == 1
            assert purchases[0]["unit"] == "kilowatt hour"
            assert not [
                e
                for e in batteries
                if e["type"] == "technosphere" and e["unit"] == "kilogram"
            ]
            expected = float(record["electric energy stored"]) * (
                1 + float(record["battery lifetime replacements"])
            )
            np.testing.assert_allclose(purchases[0]["amount"], expected, rtol=3e-6)
            templates.append(
                dict(
                    size=size,
                    name=name,
                    lifetime_capacity_kwh=expected,
                    capacity_link_pass=True,
                )
            )
    assert len(templates) == len(installed) == 8
    baseline = {r["size"]: r for r in rows if r["variant"] == "installed_baseline"}
    for row in rows:
        old = baseline[row["size"]]
        for field in ("nominal_kwh", "pack_kg", "hydrogen_kg_100km"):
            row[field + "_change_percent"] = (row[field] / old[field] - 1) * 100
    assert before == {str(path): digest(path) for path in (parameters, workbook)}
    csv_write(args.output / "model_screen.csv", rows)
    csv_write(args.output / "installed_capacity_links.csv", templates)
    (args.output / "reference_packs.json").write_text(
        json.dumps(REFERENCES, indent=2) + "\n"
    )
    source_files = [
        Path(__file__),
        ROOT / "carculator_utils/model.py",
        ROOT / "carculator_utils/energy_consumption.py",
        ROOT.parent / "carculator/carculator/model.py",
        ROOT.parent / "carculator/carculator/data/default_parameters.json",
    ]
    run = dict(
        python=sys.version,
        executable=sys.executable,
        numpy=np.__version__,
        model_path=sys.modules[CarModel.__module__].__file__,
        year=2020,
        country="CH",
        cycle="WLTC",
        sizes=sorted(installed),
        variants=variants,
        installed_hashes=before,
        source_hashes={str(p): digest(p) for p in source_files},
        commits={
            repo: subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT.parent / repo, text=True
            ).strip()
            for repo in ("carculator", "carculator_utils", "premise")
        },
        templates_verified=8,
        independent_model_checks=48,
        inventories_changed=False,
        runtime_changed=False,
        databases_rebuilt=False,
        qualification="Power-scaled manufacturer packs are unapproved sensitivities. Charging ratios are arbitrary diagnostics, not published limits. No SOC, thermal, ramp, calendar or cycling certification.",
    )
    (args.output / "run.json").write_text(json.dumps(run, indent=2) + "\n")
    print("PASS: 48 vehicle cases; eight installed packs and capacity links unchanged.")


if __name__ == "__main__":
    main()
