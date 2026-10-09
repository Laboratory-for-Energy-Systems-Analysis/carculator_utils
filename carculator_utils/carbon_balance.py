"""Physical carbon diagnostics kept separate from legacy climate accounting."""

import numpy as np
import xarray as xr

# Integer atomic masses are consistent with the CO2 factors' 12/44 convention.
# Values are (number of C, H, O atoms), not fitted emission coefficients.
FORMULAS = {
    "Carbon monoxide": (1, 0, 1),
    "Methane": (1, 4, 0),
    "Ethane": (2, 6, 0),
    "Propane": (3, 8, 0),
    "Butane": (4, 10, 0),
    "Pentane": (5, 12, 0),
    "Hexane": (6, 14, 0),
    "Heptane": (7, 16, 0),
    "Cyclohexane": (6, 12, 0),
    "Ethene": (2, 4, 0),
    "Propene": (3, 6, 0),
    "1-Pentene": (5, 10, 0),
    "Benzene": (6, 6, 0),
    "Toluene": (7, 8, 0),
    "m-Xylene": (8, 10, 0),
    "o-Xylene": (8, 10, 0),
    "Styrene": (8, 8, 0),
    "Formaldehyde": (1, 2, 1),
    "Acetaldehyde": (2, 4, 1),
    "Acetone": (3, 6, 1),
    "Acrolein": (3, 4, 1),
    "Benzaldehyde": (7, 6, 1),
    "Methyl ethyl ketone": (4, 8, 1),
}
UNSPECIFIED = (
    "Non-methane hydrocarbon",
    "Hydrocarbons",
    "PAH, polycyclic aromatic hydrocarbons",
    "Particulate matters",
)
ENVIRONMENTS = ("urban", "suburban", "rural")


def carbon_origin(component):
    """Describe fuel provenance without treating accounting shares as biology.

    Classification is based on the named fuel route. A custom supplier requires
    its own source audit and is not authenticated by this description.
    """
    name = component["type"]
    if name.startswith("hydrogen"):
        return "no carbon in hydrogen"
    if "cement" in name:
        return (
            "recycled industrial carbon; fossil/biogenic split needs supplier evidence"
        )
    if (
        name == "methane - synthetic - biological"
        or "electrolysis" in name
        or "electrochemical" in name
    ):
        return "captured atmospheric carbon for the supported default route; not biogenic carbon"
    if any(
        term in name
        for term in ("bioethanol", "biodiesel", "biomethane", "wood", "forest")
    ):
        return "biogenic carbon"
    return "fossil carbon"


def inventory_carbon_balance(inventory):
    """Return carbon bounds in kg C/vkm for engine fuel and direct exhaust.

    Fuel carbon is inferred from the specified full-oxidation CO2 factor, not
    independently measured elemental composition. Unspecified HC/PM carbon is
    bounded by zero and the species' entire mass; no unsupported carbon fraction
    is invented. Evaporation, lubricants and non-exhaust carbon are outside this
    diagnostic. It never changes the inventory or allocates capture credits.
    """
    array = inventory.array
    template = array.sel(parameter="fuel consumption", drop=True).transpose(
        "value", "combined_dim", "year"
    )
    burned = template * array.sel(parameter="fuel density per kg", drop=True)
    fuel_carbon = xr.zeros_like(template, dtype=float)
    accounting_nonfossil = xr.zeros_like(template, dtype=float)
    routes = {}
    for label in array.combined_dim.values:
        powertrain = str(label).split(" - ")[-1]
        fuel = (
            "petrol"
            if powertrain.endswith("-p")
            else (
                "diesel"
                if powertrain.endswith("-d")
                else "methane" if powertrain == "ICEV-g" else None
            )
        )
        if fuel is None or fuel not in inventory.fuel_blend:
            continue
        blend = inventory.fuel_blend[fuel]
        total = (
            sum(np.asarray(c["share"]) * np.asarray(c["CO2"]) for c in blend.values())
            * 12
            / 44
        )
        nonfossil = (
            sum(
                np.asarray(c["share"])
                * np.asarray(c["CO2"])
                * np.asarray(c["biogenic share"])
                for c in blend.values()
            )
            * 12
            / 44
        )
        fuel_carbon.loc[dict(combined_dim=label)] = (
            burned.sel(combined_dim=label) * total
        )
        accounting_nonfossil.loc[dict(combined_dim=label)] = (
            burned.sel(combined_dim=label) * nonfossil
        )
        routes[fuel] = [
            {
                "fuel": c["type"],
                "origin": carbon_origin(c),
                "accounting_field": "biogenic share (legacy non-fossil accounting allocation)",
            }
            for c in blend.values()
        ]
    known = xr.zeros_like(template, dtype=float)
    unknown_mass = xr.zeros_like(template, dtype=float)
    for species in (*FORMULAS, *UNSPECIFIED):
        names = [
            f"{species} direct emissions, {environment}" for environment in ENVIRONMENTS
        ]
        names = [name for name in names if name in array.parameter.values]
        if not names:
            continue
        mass = array.sel(parameter=names).sum("parameter").transpose(*template.dims)
        if not np.isfinite(mass).all() or bool((mass < 0).any()):
            raise ValueError(f"Invalid direct-exhaust mass for {species}.")
        if species in FORMULAS:
            c, h, o = FORMULAS[species]
            known += mass * (12 * c / (12 * c + h + 16 * o))
        else:
            unknown_mass += mass
    co2 = xr.zeros_like(template, dtype=float)
    for label in array.combined_dim.values:
        size, powertrain = str(label).rsplit(" - ", 1)
        columns = [
            index
            for key, index in inventory.inputs.items()
            if key[0] == f"transport, {inventory.vm.vehicle_type}, {powertrain}, {size}"
        ]
        if len(columns) != 1:
            raise ValueError(f"Expected one transport activity for {label}.")
        rows = [
            inventory.inputs[(f"Carbon dioxide, {origin}", ("air",), "kilogram")]
            for origin in ("fossil", "non-fossil")
        ]
        values = -inventory.A[:, rows, columns[0], :].sum(axis=1) * 12 / 44
        co2.loc[dict(combined_dim=label)] = values
    report = xr.Dataset(
        {
            "fuel_carbon_implied": fuel_carbon,
            "co2_carbon": co2,
            "known_exhaust_carbon": known,
            "unspecified_exhaust_mass": unknown_mass,
            "carbon_excess_lower_bound": co2 + known - fuel_carbon,
            "carbon_excess_upper_bound": co2 + known + unknown_mass - fuel_carbon,
            "legacy_nonfossil_accounting_carbon": accounting_nonfossil,
        }
    )
    for variable in report.data_vars:
        report[variable].attrs["unit"] = (
            "kg C/vkm" if variable != "unspecified_exhaust_mass" else "kg/vkm"
        )
    report.attrs.update(
        boundary="engine fuel and direct exhaust; full oxidation CO2 plus independently estimated pollutants",
        carbon_routes=routes,
        closed_elemental_balance=False,
        qualification="A positive excess exposes double counting. This diagnostic does not validate capture-credit allocation or assume unknown exhaust composition.",
    )
    return report


def reconcile_exhaust_carbon(inventory, carbon_fractions, *, source):
    """Replace full-oxidation CO2 with a carbon-conserving exhaust balance.

    Supply kg C/kg for every present unspecified exhaust group and document
    their source/boundary. This treats all counted exhaust carbon as originating
    in engine fuel. It retains the selected legacy fossil/non-fossil accounting
    allocation: physical origin and upstream capture credits need separate review.
    Repeated calls recompute from engine fuel, never subtract twice.
    """
    if not isinstance(source, str) or not source.strip():
        raise ValueError(
            "A source and boundary description for exhaust carbon fractions is required."
        )
    if set(carbon_fractions) - set(UNSPECIFIED):
        raise ValueError("Carbon fractions contain unsupported exhaust groups.")
    report = inventory_carbon_balance(inventory)
    other_carbon = xr.zeros_like(report.known_exhaust_carbon)
    for species in UNSPECIFIED:
        names = [
            f"{species} direct emissions, {environment}" for environment in ENVIRONMENTS
        ]
        names = [name for name in names if name in inventory.array.parameter.values]
        if not names:
            continue
        mass = (
            inventory.array.sel(parameter=names)
            .sum("parameter")
            .transpose(*other_carbon.dims)
        )
        if bool((mass != 0).any()) and species not in carbon_fractions:
            raise ValueError(f"Provide an explicit carbon fraction for {species}.")
        try:
            fraction = float(carbon_fractions.get(species, 0))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid carbon fraction for {species}.") from error
        if not np.isfinite(fraction) or not 0 <= fraction <= 1:
            raise ValueError(f"Carbon fraction for {species} must be within [0, 1].")
        other_carbon += mass * fraction
    remaining = report.fuel_carbon_implied - report.known_exhaust_carbon - other_carbon
    if bool((remaining < -1e-10).any()) or not np.isfinite(remaining).all():
        raise ValueError(
            "Exhaust carbon exceeds carbon implied by engine fuel; cannot reconcile CO2."
        )
    remaining = remaining.clip(min=0)
    nonfossil = xr.where(
        report.fuel_carbon_implied > 0,
        report.legacy_nonfossil_accounting_carbon
        / report.fuel_carbon_implied.where(report.fuel_carbon_implied > 0, 1),
        0,
    )
    # Validate all assumptions before changing any matrix entry.
    for label in inventory.array.combined_dim.values:
        size, powertrain = str(label).rsplit(" - ", 1)
        column = next(
            index
            for key, index in inventory.inputs.items()
            if key[0] == f"transport, {inventory.vm.vehicle_type}, {powertrain}, {size}"
        )
        for origin, share in [("fossil", 1 - nonfossil), ("non-fossil", nonfossil)]:
            row = inventory.inputs[(f"Carbon dioxide, {origin}", ("air",), "kilogram")]
            inventory.A[:, row, column, :] = (
                -(remaining * share).sel(combined_dim=label).values * 44 / 12
            )
    inventory.carbon_balance_provenance = {
        "source": source,
        "carbon_fractions": dict(carbon_fractions),
        "boundary": "All counted exhaust carbon assigned to engine fuel; legacy climate allocation retained.",
    }
    result = inventory_carbon_balance(inventory)
    result["specified_other_exhaust_carbon"] = other_carbon
    result["carbon_residual"] = (
        result.co2_carbon
        + result.known_exhaust_carbon
        + other_carbon
        - result.fuel_carbon_implied
    )
    result.attrs.update(
        closed_elemental_balance=True, **inventory.carbon_balance_provenance
    )
    return result
