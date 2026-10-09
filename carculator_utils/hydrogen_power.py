"""Small, attributed hydrogen-power foregrounds using bundled LCI dependencies."""

import yaml

from . import DATA_DIR


def load_hydrogen_power():
    """Read the versioned conversion assumptions and full supplier keys."""
    with (DATA_DIR / "electricity" / "hydrogen_power.yaml").open(
        encoding="utf-8"
    ) as stream:
        return yaml.safe_load(stream)


def activity_key(key):
    """Preserve tuple-valued biosphere compartments."""
    return tuple(tuple(part) if isinstance(part, list) else part for part in key)


def register_hydrogen_power(inputs, country):
    """Append private activities, keeping all shipped A/B indices unchanged."""
    config = load_hydrogen_power()
    dependencies = list(config["fuels"].values())
    dependencies += [
        item["key"]
        for converter in config["converters"].values()
        for item in converter["inputs"]
    ]
    dependencies += [["Hydrogen", ["air"], "kilogram"]]
    for key in dependencies:
        if activity_key(key) not in inputs:
            raise KeyError(f"Missing hydrogen power dependency: {key}.")
    mapping = {
        f"Hydrogen {converter}, {fuel}": (
            f"electricity production, hydrogen {converter}, {fuel}, TYNDP proxy",
            country,
            "kilowatt hour",
            "electricity, high voltage",
        )
        for converter in config["converters"]
        for fuel in config["fuels"]
    }
    pem = (
        "hydrogen supply for electricity, PEM electrolysis",
        country,
        "kilogram",
        "hydrogen, gaseous, 30 bar",
    )
    for key in [pem, *mapping.values()]:
        inputs[key] = max(inputs.values()) + 1
    return mapping, pem


def fill_hydrogen_power(inventory, mapping, pem):
    """Fill fuel, infrastructure and emissions without fossil-power B factors.

    The electrolysis copy retains its original A inputs and B residuals, replacing
    only electricity. Its original supplier remains available to vehicle fuels.
    """
    inv = inventory
    config = load_hydrogen_power()
    template = inv.inputs[activity_key(config["fuels"]["electrolysis"])]
    column = inv.inputs[pem]
    inv.A[:, :, column, :] = inv.A[:, :, template, :]
    inv.A[:, template, column, :] = 0
    inv.A[:, column, column, :] = 1
    electricity_rows = [
        i
        for key, i in inv.inputs.items()
        if len(key) == 4 and key[2] == "kilowatt hour"
    ]
    demand = inv.A[:, electricity_rows, column, :].sum(axis=1)
    inv.A[:, electricity_rows, column, :] = 0
    prep = inv.inputs[
        (
            "electricity supply for fuel preparation",
            inv.vm.country,
            "kilowatt hour",
            "electricity, low voltage",
        )
    ]
    inv.A[:, prep, column, :] = demand
    inv.B.values[:, :, column] = inv.B.values[:, :, template]
    leakage = config["delivery_loss_fraction"]
    for converter, parameters in config["converters"].items():
        burned = 3.6 / config["lhv_mj_per_kg"] / parameters["efficiency"]
        supplied = burned / (1 - leakage)
        for fuel, supplier in config["fuels"].items():
            column = inv.inputs[mapping[f"Hydrogen {converter}, {fuel}"]]
            row = inv.inputs[pem if fuel == "electrolysis" else activity_key(supplier)]
            inv.A[:, row, column, :] = -supplied
            inv.A[:, inv.inputs[("Hydrogen", ("air",), "kilogram")], column, :] = -(
                supplied - burned
            )
            for item in parameters["inputs"]:
                inv.A[:, inv.inputs[activity_key(item["key"])], column, :] = -item[
                    "amount"
                ]
