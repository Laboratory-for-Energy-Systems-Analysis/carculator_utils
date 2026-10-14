"""Attach the approved LPG proxy and reference-energy contract to service exports."""

import math

SPEC_KEY = "vehicle lpg policy"
LPG = "liquefied petroleum gas"
NOTE = (
    "LPG operating-fuel policy: retain documented fossil LPG supply where no scenario "
    "LPG blend is represented. Apply only explicitly mapped LPG efficiency trends. "
    "The final supplier geography and scenario coverage are recorded by Premise. "
)


def attach_lpg_policy(dataset):
    name = dataset["name"]
    if not name.startswith(
        (f"transport, passenger car, {LPG},", f"transport, freight, lorry, {LPG},")
    ):
        return
    car = name.startswith("transport, passenger car,")
    fuel = [
        e
        for e in dataset["exchanges"]
        if e["type"] == "technosphere"
        and e.get("reference product", e.get("product")) == LPG
    ]
    assert fuel and all(e["unit"] == "kilogram" for e in fuel)
    output = sum(e["amount"] for e in dataset["exchanges"] if e["type"] == "production")
    amount = sum(e["amount"] for e in fuel) / output
    assert math.isfinite(amount) and amount > 0
    dataset[SPEC_KEY] = {
        "version": 1,
        "baseline year": 2020,
        "fuel": LPG,
        "reference unit": dataset["unit"],
        "fuel kg per service": amount,
        "energy MJ per service": amount * 45.5,
        "lhv MJ per kg": 45.5,
        "fossil CO2 kg per kg": 45.5 * 0.0631,
        "IAM technology": (
            "passenger car, liquefied petroleum gas, medium"
            if car
            else name.replace("transport, freight, lorry,", "truck,", 1)
        ),
        "original model": "carculator" if car else "carculator_truck",
        "proxy powertrain": "ICEV-g",
        "proxy boundary": "CNG manufacture including tank, efficiency, maintenance and non-CO2 combustion factors",
        "fuel conversion": "Modelled fuel energy preserved using LPG-specific LHV and full-oxidation CO2",
        "CNG pump-to-tank methane leakage": "excluded",
    }
    comment = dataset.get("comment", "").replace(
        "Operating fuel blends and electricity supplied by Premise regional scenario markets. ",
        "Electricity supplied through Premise; LPG supply follows the explicit fallback policy. ",
    )
    if NOTE not in comment:
        comment = NOTE + comment
    dataset["comment"] = comment
