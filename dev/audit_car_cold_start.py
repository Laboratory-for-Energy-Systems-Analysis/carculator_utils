"""Read-only cold-start decomposition and EF 3.1 sensitivity of the saved cars.

Run ``model`` with the matched Python 3.12 carculator environment, then ``lcia``
with the Premise/Brightway environment. Sensitivities do not edit inventories.

This reconstructs the October 13 baseline at 2.3 starts/day and compares the
proposed 1.8-start sensitivity. It requires the saved baseline comparison files
and Brightway project named below; regenerated Premise templates use 1.8/day.
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

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/premise_cars_cold_start_20261013"
COMPARISON = ROOT / "results/premise_cars_emission_checks_20261013/comparison"
ENVS = {
    "urban": "air::urban air close to ground",
    "suburban": "air::non-urban air or from high stacks",
    "rural": "air::non-urban air or from high stacks",
}
FLOW_NAMES = yaml.safe_load(
    (
        ROOT / "carculator_utils/data/emission_factors/exhaust_and_noise_flows.yaml"
    ).read_text()
)["exhaust"]
FLOW_NAMES["Particulate matters 2.5"] = FLOW_NAMES["Particulate matters"]
FLOW_NAMES["PAH polycyclic aromatic hydrocarbons"] = (
    "PAH, polycyclic aromatic hydrocarbons"
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_audit():
    sys.path[:0] = [str(ROOT), str(ROOT.parent / "carculator")]
    import carculator
    from carculator import (
        CarInputParameters,
        CarModel,
        fill_xarray_from_input_parameters,
    )

    import carculator_utils
    from carculator_utils.hot_emissions import HotEmissionsModel

    inputs = CarInputParameters()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={
            "size": ["Mini"],
            "powertrain": ["ICEV-p", "HEV-p", "PHEV-p"],
            "year": [2020],
        },
    )
    original = HotEmissionsModel.get_hot_emissions
    captured = {}

    def capture(hem, *args, **kwargs):
        result = original(hem, *args, **kwargs)
        captured.update(hem=hem, args=deepcopy(kwargs), result=result.copy(deep=True))
        return result

    with contextlib.redirect_stdout(io.StringIO()):
        model = CarModel(array, country="CH", drop_hybrids=False)
        with patch.object(HotEmissionsModel, "get_hot_emissions", capture):
            model.set_all()
    hem, args, actual = captured["hem"], captured["args"], captured["result"]
    full_extra = hem.non_exhaust.copy(deep=True)
    hem.non_exhaust[:] = 0
    hot = original(hem, **args)
    parts = {"hot_exhaust_and_wear": hot}
    for process in full_extra.type.values:
        hem.non_exhaust[:] = 0
        hem.non_exhaust.loc[dict(type=process)] = full_extra.sel(type=process)
        parts[str(process)] = original(hem, **args) - hot
    hem.non_exhaust = full_extra.copy(deep=True)
    np.testing.assert_allclose(sum(parts.values()), actual, rtol=1e-12, atol=1e-18)
    checks = [
        {"check": "all process and compartment sums reproduce baseline", "passed": True}
    ]
    rows = []
    for process, result in parts.items():
        for pt in result.powertrain.values:
            if pt == "PHEV-p":
                continue  # Aggregate is assembled by CarModel from the two modes.
            weight = (
                1
                - float(
                    model["electric utility factor"].sel(
                        size="Mini", powertrain="PHEV-p", year=2020, value=0
                    )
                )
                if pt == "PHEV-c-p"
                else 1.0
            )
            for component in result.component.values:
                substance, env = str(component).rsplit(", ", 1)
                amount = float(
                    result.sel(
                        size="Mini",
                        powertrain=pt,
                        component=component,
                        year=2020,
                        value=0,
                    )
                )
                rows.append(
                    dict(
                        powertrain=str(pt),
                        process=process,
                        component=substance,
                        environment=env,
                        categories=ENVS[env],
                        kg_per_km=amount,
                        mg_per_km=amount * 1e6,
                        aggregate_phev_weight=weight,
                    )
                )
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "process_emissions.csv", index=False)
    p = dict(size="Mini", powertrain="ICEV-p", year=2020, value=0)
    annual = float(args["yearly_km"].sel(**p))
    euro = float(args["euro_class"][0])
    nmhc = float(
        full_extra.sel(
            powertrain="ICEV-p",
            euro_class=euro,
            type="cold start",
            component="Non-methane hydrocarbon",
        )
    )
    fraction = float(
        hem.nmhc_species.sel(powertrain="ICEV-p", component="Formaldehyde")
    )
    expected = nmhc * 2.3 * 365 / annual * fraction / 1000
    cold_form = float(
        frame.loc[
            (frame.powertrain == "ICEV-p")
            & (frame.process == "cold start")
            & (frame.component == "Formaldehyde"),
            "kg_per_km",
        ].sum()
    )
    np.testing.assert_allclose(cold_form, expected, rtol=1e-12)
    checks.append(
        dict(
            check="independent g/start to kg/km and formaldehyde fraction",
            expected=expected,
            actual=cold_form,
            passed=True,
        )
    )
    # Annual mileage is an allocation denominator, not a factor to multiply twice.
    twice = deepcopy(args)
    twice["yearly_km"] *= 2
    hem.non_exhaust[:] = 0
    hem.non_exhaust.loc[dict(type="cold start")] = full_extra.sel(type="cold start")
    doubled = original(hem, **twice) - hot
    np.testing.assert_allclose(doubled, parts["cold start"] / 2, rtol=1e-11, atol=1e-18)
    hem.non_exhaust = full_extra.copy(deep=True)
    checks.append(
        dict(check="doubling annual mileage halves cold-start mass", passed=True)
    )
    # Compare independently generated formaldehyde to the frozen current inventory.
    exchanges = pd.read_csv(COMPARISON / "foreground_exchanges.csv").fillna("")
    names = {
        "ICEV-p": "gasoline",
        "HEV-p": "gasoline hybrid",
        "PHEV-c-p": "plugin gasoline hybrid",
    }
    for pt, label in names.items():
        name = f"transport, passenger car, {label}, Mini, EURO-6"
        source = frame.loc[
            (frame.powertrain == pt) & (frame.component == "Formaldehyde")
        ].copy()
        source["kg_per_km"] *= source.aggregate_phev_weight
        for compartment, group in source.groupby("categories"):
            expected = group.kg_per_km.sum()
            match = exchanges.loc[
                (exchanges.variant == "new")
                & (exchanges.vehicle == name)
                & (exchanges.location == "RER")
                & (exchanges.name == "Formaldehyde")
                & (exchanges.categories == compartment)
            ]
            # Regionalized RER templates forward their unit demand to EUR.
            if not len(match):
                match = exchanges.loc[
                    (exchanges.variant == "new")
                    & (exchanges.vehicle == name)
                    & (exchanges.location == "EUR")
                    & (exchanges.name == "Formaldehyde")
                    & (exchanges.categories == compartment)
                ]
            actual_amount = match.amount.sum()
            np.testing.assert_allclose(actual_amount, expected, rtol=2e-6, atol=1e-18)
            checks.append(
                dict(
                    check="current template formaldehyde",
                    vehicle=name,
                    categories=compartment,
                    expected=expected,
                    actual=actual_amount,
                    passed=True,
                )
            )
    sources = [
        ROOT / "carculator_utils/hot_emissions.py",
        ROOT / "carculator_utils/model.py",
        ROOT.parent / "carculator/carculator/model.py",
    ]
    sources += list((ROOT / "carculator_utils/data/emission_factors/car").glob("*.csv"))
    meta = dict(
        python=sys.version,
        carculator=carculator.__file__,
        carculator_utils=carculator_utils.__file__,
        year=2020,
        country="CH",
        cycle=hem.cycle_name,
        euro_table_code=euro,
        annual_km=annual,
        starts_per_day=2.3,
        starts_per_year=2.3 * 365,
        implied_km_per_start=annual / (2.3 * 365),
        nmhc_g_per_start=nmhc,
        formaldehyde_fraction=fraction,
        hashes={str(path): sha(path) for path in sources},
        checks=checks,
    )
    (OUT / "model_checks.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in meta.items() if k not in {"hashes", "checks"}}, indent=2
        )
    )
    print("Model checks passed:", len(checks), flush=True)


def lcia_audit():
    import bw2calc as bc
    import bw2data as bd

    bd.projects.set_current("premise-cars-2020-ef31-20261012")
    scores = pd.read_csv(COMPARISON / "ef31_scores.csv")
    components = pd.read_csv(OUT / "process_emissions.csv")
    name = "transport, passenger car, gasoline, Mini, EURO-6"
    scores = scores.loc[(scores.name == name) & (scores.location == "EUR")]
    categories = [
        "human toxicity: carcinogenic",
        "human toxicity: non-carcinogenic",
        "photochemical oxidant formation: human health",
        "climate change",
    ]
    contributions, decomposed, total_rows, sensitivity, checks = [], [], [], [], []
    for variant in ("old", "new"):
        selected = scores.loc[scores.variant == variant]
        database, code = (
            selected[["database", "activity_code"]].drop_duplicates().iloc[0]
        )
        act = bd.get_activity((database, code))
        assert (
            act["name"],
            act["location"],
            act["reference product"],
            act["unit"],
        ) == (name, "EUR", "transport, passenger car, EURO-6", "kilometer")
        lca = bc.LCA({act: 1})
        lca.lci(factorize=True)
        for category in categories:
            methods = [
                m
                for m in bd.methods
                if m[:3] == ("ecoinvent-3.12", "EF v3.1", category)
            ]
            assert len(methods) == 1, methods
            method = methods[0]
            lca.switch_method(method)
            lca.lcia()
            expected = float(
                selected.loc[selected.category == category, "score"].iloc[0]
            )
            np.testing.assert_allclose(lca.score, expected, rtol=1e-10, atol=0)
            checks.append(
                dict(
                    check="saved database score",
                    variant=variant,
                    category=category,
                    passed=True,
                )
            )
            cf = np.asarray(lca.characterization_matrix.sum(axis=0)).ravel()
            direct_total = 0
            identities = {}
            amounts = {}
            for exc in act.biosphere():
                flow = exc.input
                compartment = "::".join(flow.get("categories", ()))
                factor = float(cf[lca.dicts.biosphere[flow.id]])
                direct = float(exc["amount"]) * factor
                direct_total += direct
                identities[flow["name"], compartment] = factor
                key = (flow["name"], compartment)
                amounts[key] = amounts.get(key, 0.0) + float(exc["amount"])
                contributions.append(
                    dict(
                        variant=variant,
                        category=category,
                        flow=flow["name"],
                        categories=compartment,
                        kg_per_km=exc["amount"],
                        cf=factor,
                        score=direct,
                    )
                )
            total_rows.append(
                dict(
                    variant=variant,
                    database=database,
                    activity_code=code,
                    name=name,
                    product=act["reference product"],
                    location="EUR",
                    functional_unit="1 vehicle-kilometre",
                    method=json.dumps(method),
                    category=category,
                    unit=bd.methods[method]["unit"],
                    score=lca.score,
                    direct_score=direct_total,
                    upstream_score=lca.score - direct_total,
                )
            )
            if variant == "old":
                continue
            cold_components = set(
                components.loc[
                    (components.powertrain == "ICEV-p")
                    & (components.process == "cold start")
                    & (components.kg_per_km != 0),
                    "component",
                ]
            )
            for substance in cold_components - {"Hydrocarbon", "Nitrogen dioxide"}:
                subset = components.loc[
                    (components.powertrain == "ICEV-p")
                    & (components.component == substance)
                ]
                for compartment, group in subset.groupby("categories"):
                    flow = FLOW_NAMES.get(substance, substance)
                    np.testing.assert_allclose(
                        amounts.get((flow, compartment), 0),
                        group.kg_per_km.sum(),
                        rtol=2e-6,
                        atol=1e-18,
                    )
            checks.append(
                dict(
                    check="all cold-start species match saved inventory masses",
                    category=category,
                    passed=True,
                )
            )
            # Characterize model process increments using exact database flow identities.
            cold_score = 0.0
            soak_score = 0.0
            formal_cold_score = 0.0
            for row in components.loc[components.powertrain == "ICEV-p"].itertuples():
                flow_name = FLOW_NAMES.get(row.component, row.component)
                key = (flow_name, row.categories)
                if not row.kg_per_km:
                    continue
                if row.component in {"Hydrocarbon", "Nitrogen dioxide"}:
                    continue  # Diagnostic totals already represented by component flows.
                if key not in identities:
                    raise AssertionError(("Missing emitted flow", row))
                impact = row.kg_per_km * identities[key]
                decomposed.append(
                    dict(
                        category=category,
                        process=row.process,
                        flow=flow_name,
                        categories=row.categories,
                        kg_per_km=row.kg_per_km,
                        score=impact,
                    )
                )
                if row.process == "cold start":
                    cold_score += impact
                    if row.component == "Formaldehyde":
                        formal_cold_score += impact
                if row.process == "soak":
                    soak_score += impact
            for label, delta in (
                (
                    "1.8 starts/day, cold start and soak only",
                    (1.8 / 2.3 - 1) * (cold_score + soak_score),
                ),
                ("1.8 starts/day, cold start only", (1.8 / 2.3 - 1) * cold_score),
                ("zero cold starts, diagnostic lower bound", -cold_score),
                (
                    "2024 formaldehyde profile 1.175%, diagnostic only",
                    (1.175 / 1.7 - 1)
                    * sum(
                        d["score"]
                        for d in decomposed
                        if d["category"] == category and d["flow"] == "Formaldehyde"
                    ),
                ),
            ):
                old = float(
                    scores.loc[
                        (scores.variant == "old") & (scores.category == category),
                        "score",
                    ].iloc[0]
                )
                sensitivity.append(
                    dict(
                        category=category,
                        scenario=label,
                        baseline=lca.score,
                        counterfactual=lca.score + delta,
                        delta=delta,
                        change_percent=100 * delta / lca.score,
                        counterfactual_vs_old_percent=100
                        * ((lca.score + delta) / old - 1),
                        cold_start_score=cold_score,
                        cold_formaldehyde_score=formal_cold_score,
                    )
                )
    for filename, rows in (
        ("direct_contributions.csv", contributions),
        ("process_impacts.csv", decomposed),
        ("totals.csv", total_rows),
        ("sensitivity.csv", sensitivity),
    ):
        pd.DataFrame(rows).to_csv(OUT / filename, index=False)
    paired = (
        pd.DataFrame(contributions)
        .pivot_table(
            index=["category", "flow", "categories"],
            columns="variant",
            values="score",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )
    paired["delta"] = paired["new"] - paired["old"]
    paired.to_csv(OUT / "direct_impact_changes.csv", index=False)
    meta = dict(
        project=bd.projects.current,
        mutated_databases=False,
        checks=checks,
        qualification="Static foreground sensitivities at fixed annual mileage and unchanged per-start factors. Not HBEFA recalibration or new saved databases.",
    )
    (OUT / "lcia_checks.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(
        pd.DataFrame(total_rows)[
            ["variant", "category", "score", "direct_score", "upstream_score"]
        ].to_string(index=False)
    )
    print(pd.DataFrame(sensitivity).to_string(index=False))
    with pd.ExcelWriter(OUT / "cold_start_audit.xlsx") as writer:
        for file, sheet in (
            ("process_emissions", "Model process masses"),
            ("direct_contributions", "Direct EF contributions"),
            ("direct_impact_changes", "Old new direct changes"),
            ("process_impacts", "New process EF impacts"),
            ("totals", "Saved EF scores"),
            ("sensitivity", "Unapplied sensitivities"),
        ):
            pd.read_csv(OUT / f"{file}.csv").to_excel(
                writer, sheet_name=sheet, index=False
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["model", "lcia"])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (model_audit if args.phase == "model" else lcia_audit)()
