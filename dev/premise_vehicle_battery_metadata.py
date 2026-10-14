"""Precompute the small battery-sizing contract during inventory generation.

Runtime Premise needs only the saved baseline and a few mass powers. The
native cycle, PHEV mode shares and recuperation are evaluated here, once.
"""

import copy
import math

import numpy as np

SPEC_KEY = "vehicle battery sizing"


def model_specification(model, size, powertrain):
    if powertrain not in {"BEV", "PHEV-p", "PHEV-d"}:
        return None
    selection = dict(size=size, year=2020, value=0)

    def value(parameter, mode=powertrain):
        return float(model.array.sel(**selection, powertrain=mode, parameter=parameter))

    share = value("electric utility factor") if powertrain.startswith("PHEV") else 1
    mode = "PHEV-e" if powertrain.startswith("PHEV") else "BEV"
    capacity = value("electric energy stored")
    depth = value("battery DoD")
    stored_per_km = value("TtW energy", mode) / 3600
    spec = {
        "version": 1,
        "baseline year": 2020,
        "family": model.vehicle_type,
        "powertrain": powertrain,
        "chemistry": model.energy_storage["electric"][(mode, size, 2020)],
        "capacity kWh": capacity,
        "pack mass kg": value("energy battery mass"),
        "cell density kWh/kg": value("battery cell energy density"),
        "cell mass share": value("battery cell mass share"),
        "curb mass kg": value("curb mass"),
        "driving mass kg": value("driving mass"),
        "electric range km": capacity * depth / stored_per_km,
        "electric share": share,
        "stored kWh per electric km": stored_per_km,
        "depth of discharge": depth,
        "charge efficiency": value("battery charge efficiency"),
        "charger efficiency": value("charger efficiency"),
        "replacements": value("battery lifetime replacements"),
        "lifetime km": value("lifetime kilometers"),
        "annual km": value("kilometers per year"),
        "wear source": "carculator_utils.particulates_emissions and inventory.add_abrasion_emissions; baseline mode/cycle/recuperation shares",
    }
    if model.vehicle_type == "truck":
        spec["gross mass kg"] = value("gross mass")
        spec["cargo mass kg"] = value("cargo mass")
    elif powertrain.startswith("PHEV"):
        # Calibrated PHEV pack density differs from the generic BEV chemistry
        # assumption. Apply the existing projection as a relative improvement.
        spec["density projection basis"] = "relative chemistry trend"
    modes = [(mode, share)]
    if powertrain.startswith("PHEV"):
        modes.append(("PHEV-c-" + powertrain[-1], 1 - share))
    terms = {kind: [] for kind in ("road", "tyre", "brake")}
    for mode, weight in modes:
        mass = value("driving mass", mode)
        tonnes = mass / 1000
        velocity = (
            model.energy.sel(**selection, powertrain=mode, parameter="velocity").values
            * 3.6
        )
        shares = [
            float(velocity[mask].sum() / velocity.sum())
            for mask in (
                velocity < 50,
                (velocity > 50) & (velocity <= 80),
                velocity > 80,
            )
        ]
        dust = 0.333 * 10.2 * tonnes ** (1 / 1.1)
        terms["road"].extend(
            [
                (weight * 7.9 * tonnes ** (1 / 1.5), mass, 1 / 1.5),
                (weight * dust, mass, 1 / 1.1),
            ]
        )
        tyre = sum(a * b for a, b in zip(shares, (14, 10.9, 9.3))) * tonnes ** (1 / 2.3)
        terms["tyre"].extend(
            [(weight * tyre, mass, 1 / 2.3), (weight * dust, mass, 1 / 1.1)]
        )
        regen = 1 - value("share recuperated energy", mode)
        for cycle_share, coefficient, exponent in zip(
            shares, (15.2, 6.3, 1.4), (1 / 1.9, 1 / 1.5, 1 / 1.3)
        ):
            terms["brake"].append(
                (
                    weight * regen * cycle_share * coefficient * tonnes**exponent,
                    mass,
                    exponent,
                )
            )
        terms["brake"].append((weight * dust, mass, 1 / 1.1))
    # Independently verify that the condensed formulas reproduce the native model.
    for kind, parameter in (
        ("road", "road wear emissions"),
        ("tyre", "tire wear emissions"),
        ("brake", "brake wear emissions"),
    ):
        total = sum(term[0] for term in terms[kind])
        expected = value(parameter) + 0.333 * value("road dust emissions")
        np.testing.assert_allclose(total / 1e6, expected, rtol=3e-6, atol=1e-12)
        terms[kind] = [
            [amount / total, mass, exponent]
            for amount, mass, exponent in terms[kind]
            if amount > 0
        ]
    spec["wear terms"] = terms
    return spec


def attach_specification(service, production, spec):
    if spec is None:
        return
    spec = copy.deepcopy(spec)
    spec["grid kWh per service"] = sum(
        e["amount"]
        for e in service["exchanges"]
        if e["type"] == "technosphere"
        and e.get("reference product") == "electricity, low voltage"
        and e["unit"] == "kilowatt hour"
    )
    assert (
        math.isfinite(spec["grid kWh per service"]) and spec["grid kWh per service"] > 0
    )
    service[SPEC_KEY] = spec
    production[SPEC_KEY] = copy.deepcopy(spec)
