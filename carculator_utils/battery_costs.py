"""Track battery-price inputs through labelled array transformations.

References and custom-record flags are auxiliary coordinates, so selection,
interpolation and sample reordering transform them with the data. Runtime
default curves remain separate from these input prices.
"""

import hashlib
import json
from itertools import product

import numpy as np
import xarray as xr

ENERGY_COST = "energy battery cost per kWh"
POWER_COST = "power battery cost per kW"
REFERENCE_PREFIX = "_battery_cost_reference_"
EXPLICIT_PREFIX = "_battery_cost_explicit_"
SENSITIVITY = "_battery_cost_sensitivity"
DISTRIBUTION_FIELDS = {
    "kind",
    "uncertainty_type",
    "amount",
    "loc",
    "minimum",
    "maximum",
}


def is_battery_cost(parameter):
    return parameter in (ENERGY_COST, POWER_COST) or parameter.startswith(
        ENERGY_COST + ", "
    )


def reference_name(parameter):
    return REFERENCE_PREFIX + hashlib.sha256(parameter.encode()).hexdigest()[:16]


def explicit_name(parameter):
    return EXPLICIT_PREFIX + hashlib.sha256(parameter.encode()).hexdigest()[:16]


def remember_samples(inputs):
    """Remember draws before callers can edit ``inputs.values``."""
    inputs._battery_cost_samples = {
        key: np.asarray(value, dtype=np.float32).copy()
        for key, value in inputs.values.items()
        if is_battery_cost(inputs.metadata[key]["name"])
    }


def attach_references(array, inputs):
    """Distinguish packaged definitions/draws from custom cost records."""
    labels = [p for p in array.parameter.values if is_battery_cost(p)]
    if not labels:
        return array
    defaults = {}
    if inputs.DEFAULT.exists():
        with inputs.DEFAULT.open(encoding="utf-8") as stream:
            for record in json.load(stream).values():
                if is_battery_cost(record["name"]):
                    definition = {
                        k: v for k, v in record.items() if k in DISTRIBUTION_FIELDS
                    }
                    for size, powertrain in product(
                        record["sizes"], record["powertrain"]
                    ):
                        defaults.setdefault(
                            (record["name"], size, powertrain, record["year"]),
                            definition,
                        )

    references = {
        p: xr.zeros_like(array.sel(parameter=p, drop=True)).reset_coords(drop=True)
        for p in labels
    }
    explicit = {
        p: xr.zeros_like(ref.isel(value=0, drop=True)) for p, ref in references.items()
    }
    seen = set()
    for key in inputs:
        metadata = inputs.metadata[key]
        parameter = metadata["name"]
        if parameter not in references:
            continue
        for size, powertrain in product(metadata["sizes"], metadata["powertrain"]):
            year = metadata["year"]
            cell = (parameter, size, powertrain, year)
            selection = dict(size=size, powertrain=powertrain, year=year)
            if cell in seen or any(
                v not in array[d].values for d, v in selection.items()
            ):
                continue
            seen.add(cell)
            references[parameter].loc[selection] = inputs._battery_cost_samples.get(
                key, inputs.values[key]
            )
            explicit[parameter].loc[selection] = inputs.data[key] != defaults.get(cell)
    coordinates = {reference_name(p): ref for p, ref in references.items()}
    coordinates.update(
        {explicit_name(p): flag for p, flag in explicit.items() if flag.any()}
    )
    return array.assign_coords(coordinates)


def capture_inputs(array):
    """Return immutable input values, explicit masks and sensitivity multipliers."""
    captured = {}
    for parameter in array.parameter.values:
        if not is_battery_cost(parameter):
            continue
        value = array.sel(parameter=parameter, drop=True).reset_coords(drop=True)
        name = reference_name(parameter)
        if name in array.coords:
            reference = array.coords[name].reset_coords(drop=True)
            custom = array.coords.get(explicit_name(parameter), 0)
            if isinstance(custom, xr.DataArray):
                custom = custom.reset_coords(drop=True)
            # A generated sensitivity sample changes the projected default by
            # 10%, rather than replacing it with a different legacy input price.
            perturbation = (
                (array.value == parameter)
                & bool(array.attrs.get(SENSITIVITY, False))
                & (abs(value - reference * 1.1) <= 5e-7 * abs(reference * 1.1))
                & (custom == 0)
            )
            explicit = ((value != reference) | (custom > 0)) & ~perturbation
            multiplier = xr.where(perturbation, 1.1, 1.0)
        else:
            # Old/hand-built arrays have no provenance: retain legacy defaults.
            # A documented constructor override can explicitly price these cells.
            explicit = xr.full_like(
                value,
                any(c.startswith(REFERENCE_PREFIX) for c in array.coords),
                dtype=bool,
            )
            multiplier = xr.ones_like(value)
        if ((~np.isfinite(value) | (value < 0)) & explicit).any():
            raise ValueError(f"Explicit {parameter!r} must be finite and nonnegative.")
        captured[parameter] = (value.copy(deep=True), explicit, multiplier)
    return captured
