"""Screen the refreshed 2020 cars against Euro 6 passenger-car mass limits.

This is an inventory plausibility screen, not a type-approval calculation.
Run with the matched Python 3.12 carculator environment. No data are modified.
"""

import argparse
import contextlib
import hashlib
import io
import json
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent / "carculator")]

import numpy as np
import pandas as pd
from carculator import CarInputParameters, CarModel, fill_xarray_from_input_parameters

from carculator_utils import DATA_DIR
from carculator_utils.hot_emissions import MAP_PWT, HotEmissionsModel

COMPONENTS = {
    "CO": "Carbon monoxide",
    "NOx": "Nitrogen oxides",
    "PM": "Particulate matters 2.5",
    "THC": "Hydrocarbon",
    "NMHC": "Non-methane hydrocarbon",
    "CH4": "Methane",
    "benzene": "Benzene",
}
LIMITS = {
    "PI": {"CO": 1000, "NOx": 60, "PM": 4.5, "THC": 100, "NMHC": 68},
    "CI": {"CO": 500, "NOx": 80, "PM": 4.5, "THC+NOx": 170},
}
SOURCES = {
    "mass_limits": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32012R0459",
    "rde_margin": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32018R1832",
}
FLOW_NAMES = {
    "CO": ["Carbon monoxide, fossil", "Carbon monoxide, non-fossil"],
    "NOx": ["Nitrogen oxides"],
    "PM": ["Particulate Matter, < 2.5 um"],
}
ORGANIC_FLOWS = [
    "NMVOC, non-methane volatile organic compounds",
    "Benzene",
    "PAH, polycyclic aromatic hydrocarbons",
    "Ethane",
    "Propane",
    "Butane",
    "Pentane",
    "Hexane",
    "Cyclohexane",
    "Heptane",
    "Ethylene",
    "Propylene",
    "1-Pentene",
    "Toluene",
    "m-Xylene",
    "o-Xylene",
    "Formaldehyde",
    "Acetaldehyde",
    "Benzaldehyde",
    "Acetone",
    "Methyl ethyl ketone",
    "Acrolein",
    "Styrene",
]


def coefficient(frame, **selection):
    for key, value in selection.items():
        if key in frame:
            frame = frame.loc[frame[key] == value]
    return float(frame.value.mean()) if len(frame) else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=ROOT / "results/premise_cars_evaporation_20261013"
    )
    args = parser.parse_args()
    out = args.input / "euro_screen"
    out.mkdir(exist_ok=True)
    recipes = pd.read_csv(
        ROOT / "results/premise_vehicle_audit_20261012/candidate_recipes.csv"
    ).fillna("")
    recipes = recipes.loc[
        (recipes.family == "car") & (recipes.selected_for_2020_update == True)
    ]
    native = recipes.loc[recipes.status.str.startswith("native")]
    inputs = CarInputParameters()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={
            "size": sorted(native.model_size.unique()),
            "powertrain": sorted(native.model_powertrain.unique()),
            "year": [2020],
        },
    )
    captured = {}
    original = HotEmissionsModel.get_hot_emissions

    def capture(hem, *args, **kwargs):
        result = original(hem, *args, **kwargs)
        captured.update(
            arguments=deepcopy(kwargs),
            distance=hem.velocity.sum("second") / 3600,
            result=result.copy(deep=True),
        )
        return result

    with contextlib.redirect_stdout(io.StringIO()):
        model = CarModel(array, country="CH")
        with patch.object(HotEmissionsModel, "get_hot_emissions", capture):
            model.set_all()

    directory = DATA_DIR / "emission_factors/car"
    exhaust = pd.read_csv(directory / "EF_HBEFA42_exhaust.csv")
    extra = pd.read_csv(directory / "EF_HBEFA42_non_exhaust.csv")
    degradation = pd.read_csv(directory / "degradation_EF.csv")
    species = pd.read_csv(directory / "NMHC_species.csv")
    arguments = captured["arguments"]
    euro = float(arguments["euro_class"][0])
    components, checks = [], []
    reference = {}
    for size in native.model_size.unique():
        for pt in captured["result"].powertrain.values:
            if pt in ("PHEV-p", "PHEV-d"):
                continue  # Their modes are combined after emissions calculation.
            selection = dict(size=size, powertrain=pt, year=2020, value=0)
            distance = float(captured["distance"].sel(**selection))
            mj_per_km = float(
                arguments["energy_consumption"].sel(**selection).sum()
            ) / (1000 * distance)
            annual = float(arguments["yearly_km"].sel(**selection))
            lifetime = float(arguments["lifetime_km"].sel(**selection))
            for pollutant, component in COMPONENTS.items():
                keys = dict(
                    powertrain=MAP_PWT[pt], euro_class=euro, component=component
                )
                ef = coefficient(exhaust, **keys)
                endpoint = max(
                    1.0,
                    coefficient(
                        degradation,
                        powertrain=MAP_PWT[pt],
                        euro_class=euro,
                        component=component,
                    ),
                )
                multiplier = 1 + (endpoint - 1) * lifetime / (2 * 200000)
                hot = ef * mj_per_km * multiplier * 1000  # g/MJ -> mg/km
                cold_factor = coefficient(extra, **keys, type="cold start")
                cold = cold_factor * 2.3 * 365 / annual * 1000
                evaporative = 1000 * (
                    coefficient(extra, **keys, type="soak") * 2.3 * 365 / annual
                    + coefficient(extra, **keys, type="diurnal") * 365 / annual
                    + coefficient(extra, **keys, type="running losses")
                )
                row = dict(
                    size=size,
                    powertrain=pt,
                    pollutant=pollutant,
                    euro_table_code=euro,
                    cycle_km=distance,
                    fuel_energy_MJ_per_km=mj_per_km,
                    annual_km=annual,
                    lifetime_km=lifetime,
                    hot_coefficient_g_per_MJ=ef,
                    deterioration_multiplier=multiplier,
                    cold_coefficient_g_per_start=cold_factor,
                    hot_mg_per_km=hot,
                    cold_mg_per_km=cold,
                    exhaust_mg_per_km=hot + cold,
                    evaporative_mg_per_km=evaporative,
                )
                components.append(row)
                reference[size, pt, pollutant] = row
                # Validate the independent integration against actual model output.
                actual = captured["result"].sel(**selection)
                wanted = [f"{component}, {c}" for c in ("urban", "suburban", "rural")]
                if pollutant == "NMHC":
                    # Undo the current exhaust speciation and evaporative-benzene
                    # subtraction to recover the parent hydrocarbon pool.
                    wanted += [
                        f"{s}, {c}"
                        for s in species.component.unique()
                        for c in ("urban", "suburban", "rural")
                    ]
                actual = float(actual.sel(component=wanted).sum()) * 1e6
                expected = hot + cold + evaporative
                if pollutant == "NMHC":
                    bz_keys = dict(keys, component="Benzene")
                    actual += 1000 * (
                        coefficient(extra, **bz_keys, type="soak") * 2.3 * 365 / annual
                        + coefficient(extra, **bz_keys, type="diurnal") * 365 / annual
                        + coefficient(extra, **bz_keys, type="running losses")
                    )
                checks.append(
                    dict(
                        check="independent coefficient integration",
                        vehicle=f"{size} {pt}",
                        pollutant=pollutant,
                        expected=expected,
                        actual=actual,
                        passed=bool(np.isclose(actual, expected, rtol=2e-6, atol=1e-8)),
                    )
                )

    adapted = {
        d["name"]: d for d in json.loads((args.input / "adapted.json").read_text())
    }
    old = {
        d["name"]: d
        for d in json.loads(
            (
                ROOT / "results/premise_vehicle_audit_20261012/parsed_inventories.json"
            ).read_text()
        )
        if d["workbook"] == "lci-pass_cars.xlsx"
    }
    vehicle_rows, limit_rows = [], []
    for recipe in recipes.to_dict("records"):
        proxy = "liquefied petroleum gas" in recipe["name"]
        size, pt = (
            ("Medium", "ICEV-g")
            if proxy
            else (recipe["model_size"], recipe["model_powertrain"])
        )
        mode = pt.replace("PHEV-", "PHEV-c-") if pt.startswith("PHEV-") else pt
        uf = (
            float(model["electric utility factor"].sel(size=size, powertrain=pt))
            if pt.startswith("PHEV-")
            else 0.0
        )
        weight = 1 - uf
        ignition = "CI" if pt.endswith("-d") else "PI"
        if pt in ("BEV", "FCEV"):
            ignition = "none"
        row = dict(
            vehicle=recipe["name"],
            size=size,
            powertrain=pt,
            ignition=ignition,
            proxy=proxy,
            electric_utility_factor=uf,
            classification="M1 screening assumption" if size == "Van" else "M1",
        )
        for pollutant in COMPONENTS:
            source = reference[size, mode, pollutant]
            row[pollutant + "_mg_per_km"] = source["exhaust_mg_per_km"] * weight
            row[pollutant + "_cold_mg_per_km"] = source["cold_mg_per_km"] * weight
            row[pollutant + "_hot_mg_per_km"] = source["hot_mg_per_km"] * weight
        row["THC+NOx_mg_per_km"] = row["THC_mg_per_km"] + row["NOx_mg_per_km"]
        row["HC_closure_mg_per_km"] = (
            row["THC_mg_per_km"] - row["NMHC_mg_per_km"] - row["CH4_mg_per_km"]
        )
        # A second, deliberately conservative mass screen exposes the unresolved
        # exhaust-benzene accounting boundary. The directly tabulated benzene
        # is additional to the speciated parent NMHC in the exported inventory.
        # Oxygenated species' mass is not a regulatory FID-equivalent measurement.
        organic_mass = 1e6 * sum(
            e["amount"]
            for e in adapted[recipe["name"]]["exchanges"]
            if e["type"] == "biosphere" and e["name"] in ORGANIC_FLOWS
        )
        evaporation = reference[size, mode, "NMHC"]["evaporative_mg_per_km"] * weight
        row["exported_organic_exhaust_mass_mg_per_km"] = organic_mass - evaporation
        row["organic_mass_to_NMHC_limit_ratio"] = (
            (organic_mass - evaporation) / 68 if ignition == "PI" else np.nan
        )
        for pollutant, names in FLOW_NAMES.items():
            actual = 1e6 * sum(
                e["amount"]
                for e in adapted[recipe["name"]]["exchanges"]
                if e["type"] == "biosphere" and e["name"] in names
            )
            expected = row[pollutant + "_mg_per_km"]
            checks.append(
                dict(
                    check="adapted workbook emissions",
                    vehicle=recipe["name"],
                    pollutant=pollutant,
                    expected=expected,
                    actual=actual,
                    passed=bool(np.isclose(actual, expected, rtol=2e-6, atol=1e-8)),
                )
            )
            row[f"old_{pollutant}_mg_per_km"] = 1e6 * sum(
                e["amount"]
                for e in old[recipe["name"]]["exchanges"]
                if e["type"] == "biosphere"
                and e["name"]
                in names
                + (
                    ["Particulates, < 2.5 um"]
                    if pollutant == "PM"
                    else ["Carbon monoxide"] if pollutant == "CO" else []
                )
            )
        vehicle_rows.append(row)
        if ignition == "none":
            continue
        for pollutant, limit in LIMITS[ignition].items():
            value = row[pollutant + "_mg_per_km"]
            case = dict(
                vehicle=recipe["name"],
                size=size,
                powertrain=pt,
                proxy=proxy,
                pollutant=pollutant,
                exhaust_mg_per_km=value,
                limit_mg_per_km=limit,
                ratio=value / limit,
                above_limit=bool(value > limit),
                above_1_5x=bool(value > 1.5 * limit),
                combustion_mode_mg_per_km=value / weight,
                combustion_mode_ratio=value / weight / limit,
                euro_6d_RDE_NOx_benchmark_mg_per_km=(
                    limit * 1.43 if pollutant == "NOx" else np.nan
                ),
                note=(
                    "PI PM limit applies only to direct-injection engines; injection type unspecified. "
                    if ignition == "PI" and pollutant == "PM"
                    else ""
                )
                + (
                    "Van legal category unknown; screened as M1. "
                    if size == "Van"
                    else ""
                )
                + ("CNG combustion proxy. " if proxy else "")
                + (
                    "PHEV inventory uses real-world utility factor; also screen combustion mode."
                    if pt.startswith("PHEV-")
                    else ""
                ),
            )
            limit_rows.append(case)

    pd.DataFrame(components).to_csv(out / "emission_components.csv", index=False)
    vehicles = pd.DataFrame(vehicle_rows)
    vehicles.to_csv(out / "vehicle_exhaust_totals.csv", index=False)
    limits = pd.DataFrame(limit_rows).sort_values("ratio", ascending=False)
    limits.to_csv(out / "euro6_screen.csv", index=False)
    regional = pd.read_csv(args.input / "comparison/template_to_EUR_emissions.csv")
    regional = regional.loc[regional.variant == "new"].copy()
    regional.to_csv(out / "premise_regional_emissions.csv", index=False)
    direct_names = sum(FLOW_NAMES.values(), [])
    written_check = regional.loc[regional.flow.isin(direct_names)]
    for item in written_check.to_dict("records"):
        checks.append(
            dict(
                check="EUR CO/NOx/PM no higher than screened template",
                vehicle=item["vehicle"],
                pollutant=item["flow"],
                expected=item["template"] * 1e6,
                actual=item["EUR"] * 1e6,
                passed=bool(item["EUR"] <= item["template"] * (1 + 2e-6) + 1e-14),
            )
        )
    # Screen all 30 written EUR activities, including the zero-exhaust vehicles.
    foreground = pd.read_csv(args.input / "comparison/foreground_exchanges.csv")
    eur = foreground.loc[(foreground.variant == "new") & (foreground.location == "EUR")]
    regional_rows = []
    for name in eur.vehicle.unique():
        recipe = vehicles.loc[vehicles.vehicle == name].iloc[0]
        for pollutant, flow_names in FLOW_NAMES.items():
            subset = eur.loc[
                (eur.vehicle == name)
                & (eur.type == "biosphere")
                & eur.name.isin(flow_names)
            ]
            actual = float(subset.amount.sum()) * 1e6
            bound = float(recipe[pollutant + "_mg_per_km"])
            assert actual <= bound * (1 + 2e-6) + 1e-8
            limit = LIMITS.get(recipe.ignition, {}).get(pollutant, np.nan)
            regional_rows.append(
                dict(
                    vehicle=name,
                    location="EUR",
                    pollutant=pollutant,
                    exhaust_mg_per_km=actual,
                    limit_mg_per_km=limit,
                    ratio=actual / limit,
                )
            )
    regional_screen = pd.DataFrame(regional_rows)
    regional_screen.to_csv(out / "EUR_euro6_screen.csv", index=False)
    check_frame = pd.DataFrame(checks)
    check_frame.to_csv(out / "checks.csv", index=False)
    with pd.ExcelWriter(out / "euro6_screen.xlsx") as writer:
        limits.to_excel(writer, sheet_name="Euro 6 screen", index=False)
        vehicles.to_excel(writer, sheet_name="Exhaust totals", index=False)
        pd.DataFrame(components).to_excel(
            writer, sheet_name="Hot and cold components", index=False
        )
        check_frame.to_excel(writer, sheet_name="Validation", index=False)
        regional_screen.to_excel(writer, sheet_name="EUR CO NOx PM", index=False)
        regional.to_excel(writer, sheet_name="Premise transformations", index=False)
    summary = dict(
        cycle=model.cycle,
        year=2020,
        country="CH",
        euro_table_code=euro,
        vehicle_count=len(vehicles),
        combustion_count=int((vehicles.ignition != "none").sum()),
        limits_compared=len(limits),
        values_above_limit=int(limits.above_limit.sum()),
        values_above_1_5x=int(limits.above_1_5x.sum()),
        checks=len(check_frame),
        checks_passed=bool(check_frame.passed.all()),
        regional_vehicles=int(eur.vehicle.nunique()),
        max_exported_organic_mass_ratio=float(
            vehicles.organic_mass_to_NMHC_limit_ratio.max()
        ),
        regional_PAH_multiplier=sorted(
            regional.loc[
                regional.flow == "PAH, polycyclic aromatic hydrocarbons", "ratio"
            ]
            .dropna()
            .round(6)
            .unique()
            .tolist()
        ),
        sources=SOURCES,
        source_sha256={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                Path(__file__),
                directory / "EF_HBEFA42_exhaust.csv",
                directory / "EF_HBEFA42_non_exhaust.csv",
                directory / "degradation_EF.csv",
                args.input / "adapted.json",
                args.input / "lci-pass_cars.xlsx",
            ]
        },
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(limits.loc[limits.above_limit].to_string(index=False))
    print(
        "Largest hydrocarbon closure discrepancy (THC - NMHC - CH4), mg/km:",
        vehicles.HC_closure_mg_per_km.abs().max(),
    )
    assert check_frame.passed.all(), check_frame.loc[~check_frame.passed].to_string()


if __name__ == "__main__":
    main()
