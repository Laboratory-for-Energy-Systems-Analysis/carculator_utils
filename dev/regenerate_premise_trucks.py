"""Regenerate the approved 2020 Regional delivery trucks for Premise.

The 52 original service identities are retained. Fuels and electricity belong
to Premise; battery capacity includes initial and replacement packs. Run with
matching Python 3.12 carculator sources. This script only writes its output folder.
"""

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import yaml

from audit_premise_vehicle_workbooks import identity, read_workbook, write_csv
from regenerate_premise_cars import (
    HYDROGEN_COMPRESSION_KEY,
    clean,
    hydrogen_compression_specification,
    relabel,
    validate_phev_battery,
    write_workbook,
)
from premise_vehicle_battery_metadata import attach_specification, model_specification
from premise_vehicle_lpg_metadata import attach_lpg_policy
from premise_vehicle_provenance import attach_legacy_provenance, enrich_export

ROOT = Path(__file__).resolve().parents[2]
CYCLE = "Regional delivery"
FUELS = {
    "petrol": (42.6, 0.0737, "petrol, low-sulfur"),
    "diesel": (43.0, 0.0732, "diesel, low-sulfur"),
    "methane": (46.5, 0.06, "natural gas, medium pressure, vehicle grade"),
    "hydrogen": (120.0, 0.0, "hydrogen, gaseous, low pressure"),
    "LPG": (45.5, 0.0631, "liquefied petroleum gas"),
}


def powertrain(recipe):
    if recipe["model_powertrain"]:
        return recipe["model_powertrain"]
    if "liquefied petroleum gas" in recipe["name"]:
        return "ICEV-g"
    return "HEV-d" if "gasoline hybrid" in recipe["name"] else "ICEV-d"


def electricity(amount, comment):
    return {
        "name": "market group for electricity, low voltage",
        "reference product": "electricity, low voltage",
        "location": "RER",
        "unit": "kilowatt hour",
        "type": "technosphere",
        "amount": amount,
        "comment": comment,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-raw", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    audit = ROOT / "carculator_utils/results/premise_vehicle_audit_20261012"
    recipes = [
        r
        for r in csv.DictReader((audit / "candidate_recipes.csv").open())
        if r["family"] == "truck" and r["selected_for_2020_update"] == "True"
    ]
    assert len(recipes) == 52
    old = {
        d["name"]: d
        for d in json.loads((audit / "parsed_inventories.json").read_text())
        if d["workbook"] == "lci-trucks.xlsx"
    }
    raw_path, par_path = args.output / "raw.json", args.output / "model_parameters.json"
    for package in ("carculator_utils", "carculator_truck"):
        sys.path.insert(0, str(ROOT / package))
    if not args.reuse_raw:
        from carculator_truck import (
            TruckInputParameters,
            TruckModel,
            InventoryTruck,
            fill_xarray_from_input_parameters,
        )

        inputs = TruckInputParameters()
        inputs.static()
        scope = {
            "size": sorted({r["model_size"] for r in recipes}),
            "powertrain": sorted({powertrain(r) for r in recipes}),
            "year": [2020],
        }
        _, array = fill_xarray_from_input_parameters(inputs, scope=scope)
        model = TruckModel(array, country="CH", cycle=CYCLE, drop_hybrids=False)
        model.set_all()
        parameters = {}
        labels = [
            "power",
            "rated power",
            "electric motor efficiency",
            "auxiliary power demand",
            "fuel cell power",
            "fuel cell power share",
            "fuel cell own consumption",
            "battery power",
            "battery cell power density",
            "TtW energy",
            "electricity consumption",
            "fuel consumption",
            "LHV fuel MJ per kg",
            "fuel density per kg",
            "curb mass",
            "driving mass",
            "gross mass",
            "cargo mass",
            "available payload",
            "lifetime kilometers",
            "kilometers per year",
            "energy battery mass",
            "battery cell mass",
            "battery BoP mass",
            "electric energy stored",
            "battery lifetime replacements",
            "fuel cell lifetime replacements",
            "target range",
            "battery DoD",
            "battery cycle life",
            "electric utility factor",
            "battery cell energy density",
            "battery cell mass share",
            "is_available",
            "is_compliant",
            "starter battery mass",
            "electric power",
            "energy battery cost",
            "energy battery cost per kWh",
        ]
        for size in scope["size"]:
            for power in scope["powertrain"]:
                cell = model.array.sel(size=size, powertrain=power, year=2020).isel(
                    value=0
                )
                p = {label: float(cell.sel(parameter=label)) for label in labels}
                assert all(np.isfinite(v) for v in p.values())
                assert p["cargo mass"] > 0 and p["TtW energy"] > 0
                assert p["is_available"] == p["is_compliant"] == 1
                p["cycle"] = CYCLE
                p["battery chemistry"] = model.energy_storage["electric"][
                    (power, size, 2020)
                ]
                # The shared model now reports the full physical PHEV pack.
                p["nominal battery capacity kWh"] = p["electric energy stored"]
                if power == "FCEV":
                    profile = model.fuel_cell_battery_profile
                    scale = p["electric energy stored"] / profile.nominal_kwh
                    p["FCEV continuous charge kW"] = scale * profile.charge_kw
                    p["FCEV continuous discharge kW"] = scale * profile.discharge_kw
                    p["FCEV 10s discharge kW"] = scale * profile.discharge_10s_kw
                    p["FCEV power minimum capacity kWh"] = float(
                        model.fuel_cell_battery_capacity_requirement().sel(
                            size=size, year=2020, value=0
                        )
                    )
                p["HEV discharged stored kWh per km"] = (
                    model.hybrid_buffer_results[
                        (size, 2020, model.array.value.values[0])
                    ]["discharged_stored_kwh_per_km"]
                    if power == "HEV-d"
                    else 0
                )
                p["HEV regeneration reuse fraction"] = (
                    model.hybrid_buffer_results[
                        (size, 2020, model.array.value.values[0])
                    ]["discharged_dc_kwh"]
                    / model.hybrid_buffer_results[
                        (size, 2020, model.array.value.values[0])
                    ]["unconstrained_reusable_dc_kwh"]
                    if power == "HEV-d"
                    else 0
                )
                parameters[f"{size}|{power}"] = p
        par_path.write_text(json.dumps(parameters, indent=2) + "\n")
        sizing = {
            f"{size}|{power}": model_specification(model, size, power)
            for size in scope["size"]
            for power in scope["powertrain"]
        }
        (args.output / "battery_sizing.json").write_text(
            json.dumps(sizing, indent=2) + "\n"
        )
        model.drop_hybrid()
        inventory = InventoryTruck(model, scenario="static", functional_unit="tkm")
        paths = inventory.export_lci(
            ecoinvent_version="3.12",
            software="brightway2",
            format="file",
            directory=str(args.output / "raw"),
            filename="trucks_2020_regional",
        )
        raw = []
        for path in paths if isinstance(paths, list) else [paths]:
            raw.extend(read_workbook(Path(path))[0])
        raw_path.write_text(json.dumps(raw, indent=2) + "\n")
    raw = json.loads(raw_path.read_text())
    parameters = json.loads(par_path.read_text())
    sizing = json.loads((args.output / "battery_sizing.json").read_text())
    assert all(p["cycle"] == CYCLE for p in parameters.values())
    for name, parameter in parameters.items():
        if name.endswith("|PHEV-d"):
            validate_phev_battery(parameter)
        np.testing.assert_allclose(
            parameter["nominal battery capacity kWh"],
            parameter["energy battery mass"]
            * parameter["battery cell mass share"]
            * parameter["battery cell energy density"],
            rtol=1e-6,
            atol=1e-6,
        )
    raw_index = {identity(d): d for d in raw}
    raw_names = {d["name"]: d for d in raw}
    powers = yaml.safe_load(
        (
            ROOT
            / "carculator_utils/carculator_utils/data/export/rename_powertrains.yaml"
        ).read_text()
    )
    datasets, productions, noise, balance = [], {}, [], []
    for recipe in recipes:
        original = old[recipe["name"]]
        size, power = recipe["model_size"], powertrain(recipe)
        p = parameters[f"{size}|{power}"]
        load = p["cargo mass"] / 1000
        proxy = not recipe["model_powertrain"]
        lpg = "liquefied petroleum gas" in recipe["name"]
        source_name = f"transport, truck, {powers[power]}, {size}"
        ds = clean(raw_names[source_name])
        relabel(ds, original)
        old_vehicle = next(
            e
            for e in original["exchanges"]
            if e["type"] == "technosphere" and e["name"].startswith("lorry production,")
        )
        production = clean(raw_names[source_name.removeprefix("transport, ")])
        relabel(production, old_vehicle)
        note = (
            f"2020 carculator_truck default parameters; {CYCLE} cycle, "
            f"400 km design range, {p['cargo mass']:.12g} kg payload, "
            f"{p['kilometers per year']:g} km/year; Swiss climate. Combustion factors: EURO-VI. "
            "Operating fuel blends and electricity supplied by Premise regional scenario markets. "
            "Energy-battery capacity includes replacements and end of life through Premise capacity markets. "
            "Noise retained in companion audit only. "
        )
        if power == "PHEV-d":
            note += (
                "PHEV electric mode is sized for 60 km, combustion mode for 400 km. "
                "Nominal battery kWh is the shared model's full physical pack capacity, "
                "verified against cell mass and energy density. Fractional replacement "
                "demand uses electric-share-weighted lifetime net stored energy, nominal "
                "capacity and cycle life; the initial pack is subtracted once before "
                "clipping to 0-3 replacements. No separate calendar-age or combustion-mode "
                "cycling correction is included in this inherited approximation. "
            )
            for activity in (ds, production):
                activity["comment"] = re.sub(
                    r"Battery capacity: [0-9.eE+-]+ kWh\.",
                    f"Battery capacity: {p['nominal battery capacity kWh']:.6g} kWh.",
                    activity.get("comment", ""),
                )
                activity["comment"] = re.sub(
                    r"Autonomy on a full tank/battery: [0-9.eE+-]+ km\.",
                    "PHEV mode ranges are recorded separately in the generation metadata.",
                    activity["comment"],
                )
        if power == "FCEV" and size in {"3.5t", "7.5t"}:
            reference, url = {
                "3.5t": (
                    "Renault Master Z.E. (1 July 2020)",
                    "https://www.renaultgroup.com/magazine/energies-et-motorisations/master-z-e/",
                ),
                "7.5t": (
                    "FUSO eCanter (31 March 2020)",
                    "https://www.daimlertruck.com/newsroom/pressemitteilung/hello-dublin-der-fuso-ecanter-liefert-post-in-irland-45975414",
                ),
            }[size]
            note += (
                f"Documented motor-only proxy: {reference}, {p['rated power']:g} kW "
                f"mechanical shaft output; source: {url}. "
                "This electric-commercial-vehicle motor is transferred to the FCEV; "
                "it is not a complete FCEV calibration. The original fuel-cell/battery "
                "DC shares are retained and component mass, storage and consumption "
                "are recalculated together. Regional-delivery shaft-power feasibility "
                "is checked at the stated payload; other loads and cycles may exceed "
                "the rating. Future Premise scenarios retain this baseline FCEV hardware. "
            )
        if power == "HEV-d":
            from carculator_truck.hybrid_battery import PROFILE_SOURCE

            note += (
                "HEV traction battery sized from retained motor-power design and cycle energy, "
                "with finite regenerative storage and continuous charging limits. "
                f"Nominal capacity {p['electric energy stored']:.8g} kWh; "
                f"physical pack {p['energy battery mass']:.8g} kg; "
                f"fractional replacements {p['battery lifetime replacements']:.8g}. "
                "High-power LFP cell profile: " + PROFILE_SOURCE + ". "
                "Continuous current ratings at 25 degrees C multiplied by the 2 V cutoff; "
                "conditioned pack assumed. 60% usable SOC window and 70% cell mass share. "
                "Cycle life is the inherited generic LFP assumption, not a guarantee for "
                "these high-rate operating conditions; no separate calendar-age correction. "
                "Generic chemistry prices are a cost proxy, not a high-power pack quotation. "
                "User-selected MIX capacity-market proxy: nominal kWh and replacements "
                "are preserved, but manufacturing chemistry and mass differ from the "
                "physical high-power LFP pack (19.7 kg/kWh versus 8.6 kg/kWh for Premise's "
                "ordinary 2020 LFP capacity recipe; MIX mass depends on chemistry shares). "
                "No mass-equivalence correction is applied to the MIX market. "
                "The lead-acid starter is separate and includes at least its initial battery. "
            )
        production["comment"] = note + production.get("comment", "")
        if proxy:
            note += (
                f"Explicit {('LPG' if lpg else 'gasoline')} proxy: {powers[power]} vehicle "
                "manufacture (including tank), efficiency, maintenance and non-CO2 combustion factors. "
                "Fuel energy preserved with target-fuel-specific LHV and CO2; "
                "this is not an independently modelled gasoline/LPG vehicle. "
            )
            if lpg:
                note += "CNG-specific pump-to-tank methane leakage excluded. "
        ds["comment"] = note + ds.get("comment", "")
        kept, energy, co2_total, h2_compression = [], 0.0, 0.0, 0.0
        for exc in ds["exchanges"]:
            if exc["type"] == "biosphere" and exc["unit"] == "joule":
                noise.append(
                    dict(vehicle=ds["name"], vehicle_location=ds["location"], **exc)
                )
                continue
            if exc["name"] in ("Carbon dioxide, fossil", "Carbon dioxide, non-fossil"):
                continue
            if (
                lpg
                and exc["name"].startswith("Methane,")
                and exc.get("categories") == "air"
            ):
                continue
            if exc["type"] == "production":
                relabel(exc, ds)
            elif exc["name"].startswith("truck, "):
                relabel(exc, production)
                np.testing.assert_allclose(
                    exc["amount"], 1 / (p["lifetime kilometers"] * load), rtol=1e-6
                )
            elif exc["name"].startswith("fuel supply for "):
                family = exc["name"].split()[3]
                fuel = "LPG" if lpg else "petrol" if proxy else family
                lhv, co2, product = FUELS[fuel]
                purchased_energy = exc["amount"] * p["LHV fuel MJ per kg"]
                engine_energy = (
                    p["fuel consumption"]
                    * p["fuel density per kg"]
                    * p["LHV fuel MJ per kg"]
                    / load
                )
                np.testing.assert_allclose(
                    purchased_energy,
                    engine_energy,
                    rtol=1e-6,
                    atol=1e-8,
                    err_msg="Pump-to-tank loss requires an explicit regional adapter",
                )
                energy += engine_energy
                co2_total += engine_energy * co2
                exc.update(
                    name=f"market for {product}",
                    location=(
                        "RER"
                        if fuel == "hydrogen"
                        else (
                            "GLO" if fuel == "methane" else "Europe without Switzerland"
                        )
                    ),
                    unit="kilogram",
                    amount=engine_energy / lhv,
                    **{"reference product": product},
                )
                exc["comment"] = (
                    f"Model fuel energy retained: {engine_energy:.12g} MJ/tkm; reference LHV {lhv} MJ/kg. Premise determines regional blends."
                )
                if family == "hydrogen":
                    specification = hydrogen_compression_specification()
                    ds[HYDROGEN_COMPRESSION_KEY] = specification
                    compression = specification["electricity kWh per kg H2"]
                    h2_compression = exc["amount"] * compression
                    kept.append(
                        electricity(
                            h2_compression,
                            f"Hydrogen tank compression, 30 to 700 bar: {compression:.12g} kWh/kg H2; model compressor assumptions and Premise delivery pressure.",
                        )
                    )
            elif exc["name"].startswith("electricity supply for electric vehicles"):
                np.testing.assert_allclose(
                    exc["amount"], p["electricity consumption"] / load, rtol=1e-6
                )
                exc = electricity(
                    exc["amount"],
                    "Grid purchase including model charging losses; Premise regional electricity.",
                )
            kept.append(exc)
        if co2_total:
            kept.append(
                dict(
                    name="Carbon dioxide, fossil",
                    amount=co2_total,
                    unit="kilogram",
                    categories="air",
                    type="biosphere",
                    comment="Reference-fuel full-oxidation CO2; Premise reclassifies fossil/biogenic carbon with regional blends. Pollutants are separate model estimates, not an elemental closure.",
                )
            )
        ds["exchanges"] = kept
        capacity = p["nominal battery capacity kWh"] * (
            1 + p["battery lifetime replacements"]
        )
        battery_mass = p["energy battery mass"] * (
            1 + p["battery lifetime replacements"]
        )
        packs = [
            e
            for e in production["exchanges"]
            if e["name"].startswith("market for battery, Li-")
        ]
        disposal = [
            e
            for e in production["exchanges"]
            if e["name"] == "market for used Li-ion battery"
        ]
        np.testing.assert_allclose(
            sum(e["amount"] for e in packs), battery_mass, rtol=1e-6, atol=1e-5
        )
        np.testing.assert_allclose(
            -sum(e["amount"] for e in disposal), battery_mass, rtol=1e-6, atol=1e-5
        )
        production["exchanges"] = [
            e for e in production["exchanges"] if e not in packs + disposal
        ]
        if capacity:
            production["exchanges"].append(
                {
                    "name": "market for battery capacity (MIX scenario)",
                    "reference product": "electricity storage capacity",
                    "location": "GLO",
                    "unit": "kilowatt hour",
                    "type": "technosphere",
                    "amount": capacity,
                    "comment": f"{p['nominal battery capacity kWh']:.12g} kWh nominal * (1 + {p['battery lifetime replacements']:.12g} replacements); capacity market includes manufacture and end of life, replacing kg pack and disposal exchanges.",
                }
            )
        for exc in production["exchanges"]:
            if exc["type"] == "production":
                relabel(exc, production)
        key = identity(production)
        if key in productions:
            assert production == productions[key], key
        productions[key] = production
        datasets.append(ds)
        attach_specification(ds, production, sizing.get(f"{size}|{power}"))
        attach_lpg_policy(ds)
        balance.append(
            dict(
                name=ds["name"],
                size=size,
                powertrain=power,
                proxy=proxy,
                fuel_energy_MJ_per_tkm=energy,
                reference_fossil_CO2_kg_per_tkm=co2_total,
                h2_compression_kWh_per_tkm=h2_compression,
                battery_capacity_with_replacements_kWh=capacity,
                **p,
            )
        )
    datasets.extend(productions.values())
    # Premise owns both traction-pack and depot-buffer capacity markets.
    # Do not freeze their chemistry recipes inside copied charger components.
    capacity_keys = {
        identity(d)
        for d in read_workbook(
            ROOT
            / "premise/premise/data/additional_inventories/lci-battery-capacity.xlsx"
        )[0]
    }
    queue, auxiliaries = list(datasets), {}
    while queue:
        ds = queue.pop()
        for exc in ds["exchanges"]:
            key = identity(exc)
            if (
                exc["type"] != "technosphere"
                or key not in raw_index
                or key in auxiliaries
                or key in capacity_keys
            ):
                continue
            assert not exc["name"].startswith(
                ("fuel supply", "electricity supply", "transport, truck", "truck, ")
            )
            aux = clean(raw_index[key])
            auxiliaries[key] = aux
            queue.append(aux)
    for aux in auxiliaries.values():
        aux["name"] += ", carculator regional truck 2020"
    datasets.extend(auxiliaries.values())
    for ds in datasets:
        for exc in ds["exchanges"]:
            if identity(exc) in auxiliaries:
                relabel(exc, auxiliaries[identity(exc)])
            assert np.isfinite(exc["amount"])
        prod = [e for e in ds["exchanges"] if e["type"] == "production"]
        assert len(prod) == 1 and prod[0]["amount"] == 1, (ds["name"], prod)
        assert identity(prod[0]) == identity(ds)
    assert len({identity(d) for d in datasets}) == len(datasets)
    path = args.output / "lci-trucks.xlsx"
    # Other supplementary inventories consume original truck component names.
    # Keep those recipes, with their original 3.7 import version, in a separate
    # compatibility workbook. New trucks use their own qualified components.
    legacy_components = [
        clean(d)
        for d in old.values()
        if not d["name"].startswith(("transport,", "lorry production,"))
    ]
    legacy_path = args.output / "lci-truck-legacy-components.xlsx"
    original_summary = json.loads((audit / "summary.json").read_text())
    original_hash = original_summary["truck"]["sha256"]
    attach_legacy_provenance(
        legacy_components, {identity(d): d for d in old.values()}, original_hash
    )
    write_workbook(
        legacy_path, legacy_components, database_name="lci-truck-legacy-components"
    )
    write_csv(args.output / "noise_audit.csv", noise)
    write_csv(args.output / "vehicle_parameters.csv", balance)
    source_files = [
        ROOT / "carculator_truck/carculator_truck/model.py",
        ROOT / "carculator_truck/carculator_truck/hybrid_battery.py",
        ROOT / "carculator_truck/carculator_truck/fuel_cell_battery.py",
        ROOT / "carculator_truck/carculator_truck/inventory.py",
        ROOT / "carculator_truck/carculator_truck/data/extra_parameters.json",
        ROOT / "carculator_truck/carculator_truck/data/default_parameters.json",
        ROOT / "carculator_truck/carculator_truck/data/payloads.yaml",
        ROOT / "carculator_utils/carculator_utils/hot_emissions.py",
        ROOT / "carculator_utils/carculator_utils/model.py",
        ROOT / "carculator_utils/carculator_utils/energy_consumption.py",
        Path(__file__),
        Path(__file__).with_name("premise_vehicle_battery_metadata.py"),
    ]
    from carculator_truck.hybrid_battery import HybridBatteryProfile, PROFILE_SOURCE
    from carculator_truck.fuel_cell_battery import (
        FuelCellBatteryProfile,
        PROFILE_SOURCE as FCEV_PROFILE_SOURCE,
    )

    record = dict(
        fcev_battery_policy={
            "profile": asdict(FuelCellBatteryProfile()),
            "source": FCEV_PROFILE_SOURCE,
            "power_boundary": "Continuous charging cap after direct auxiliary use; instantaneous cycle discharge bounded by the continuous RMS rating, without repeated pulse assumptions. Rated motor buffer also bounded by the 10-second discharge rating.",
            "sizing": "Maximum of inherited 20 kWh + 6% H2 energy floor, cycle continuous-discharge requirement and rated short-pulse requirement. Explicit capacity retained and validated.",
            "mass_boundary": "Complete pack 238 kg per 25 kWh; 70% cell allocation and NMC-622 manufacture are retained proxies, not measured AKASOL cell specifications.",
            "limits": "Conditioned-pack proxy; no electrothermal, ageing, SOC-window or fuel-cell ramp validation. Generic chemistry costs and replacement assumptions retained.",
            "lca_proxy": "MIX capacity market per nominal kWh including replacements; physical mass mismatch documented without mass-equivalence correction.",
            "future_hardware": "Premise retains the regenerated 2020 FCEV hardware; no runtime cycle simulation.",
            "approved_on": "2026-10-14",
        },
        hev_battery_policy={
            "profile": asdict(HybridBatteryProfile()),
            "source": PROFILE_SOURCE,
            "power_boundary": "Full motor discharge rating; excess braking power is curtailed at the pack continuous charge limit",
            "energy_boundary": "Periodic finite regenerative buffer, no grid or engine charging; actual stored discharge sets equivalent full cycles",
            "cycle_life_and_cost": "Inherited generic chemistry assumptions, not qualified for this high-power cell",
            "lca_proxy": "User explicitly retains MIX capacity market and documents physical mass/chemistry mismatch; no mass-equivalence correction",
            "approved_on": "2026-10-13",
        },
        phev_battery_replacement_policy={
            "formula": "clip(lifetime km * electric utility factor * electric-mode net stored kJ/km / 3600 / nominal kWh / cycle life - 1, 0, 3)",
            "cycle_basis": "equivalent full cycles of nominal capacity; no additional DoD divisor",
            "energy_boundary": "inherited net stored-energy approximation; not gross charge/discharge throughput",
            "calendar_ageing": "no separate truck calendar-age model",
            "explicit_inputs": "nonzero counts retained for the whole pack; conflicting PHEV inputs rejected",
        },
        hydrogen_compression_adaptation=hydrogen_compression_specification(),
        cng_supply_basis={
            "delivered_LHV_MJ_per_kg": 46.5,
            "source": "ecoinvent vehicle-grade natural gas market comment",
            "policy": "Preserve model energy and source compression recipe; upstream gas energy is not delivered LHV",
            "approved_on": "2026-10-13",
        },
        year=2020,
        country="CH",
        cycle=CYCLE,
        target_range_km=400,
        defaults="Current 2020 cycle-specific load/mileage, sizing, lifetime and replacement values",
        proxy_policy="Energy-preserving gasoline/LPG conversions approved by user 2026-10-13; retained diesel/diesel-hybrid/CNG manufacture and non-CO2 factors explicitly documented",
        transport_count=len(recipes),
        production_count=len(productions),
        auxiliary_count=len(auxiliaries),
        retained_legacy_components=len(legacy_components),
        legacy_components_version="3.7",
        legacy_components_sha256=hashlib.sha256(legacy_path.read_bytes()).hexdigest(),
        noise_exchanges=len(noise),
        sha256=None,
        export_version="3.12",
        commits={
            p: subprocess.check_output(
                ["git", "-C", str(ROOT / p), "rev-parse", "HEAD"], text=True
            ).strip()
            for p in ("carculator_truck", "carculator_utils", "premise")
        },
        source_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files
        },
    )
    enrich_export(datasets, "truck", ROOT, args.output, record, balance, args.reuse_raw)
    write_workbook(path, datasets, database_name="lci-trucks")
    record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (args.output / "adapted.json").write_text(json.dumps(datasets, indent=2) + "\n")
    (args.output / "provenance.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2), flush=True)


if __name__ == "__main__":
    main()
