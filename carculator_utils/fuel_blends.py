"""Select normalized fuel metadata by its original model-year labels."""

from copy import deepcopy

import numpy as np

YEAR_FIELDS = ("share", "lhv", "density", "CO2", "biogenic share")


def select_fuel_blend(blend, source_years, years):
    """Return an independent blend in the requested year order.

    :param blend: Normalized component specifications, in source-year order.
    :param source_years: Year labels captured when the model was constructed.
    :param years: Nonempty, unique subset of the source years, in desired order.
    :returns: A deep copy with year vectors selected and scalar properties retained.
    :raises ValueError: Labels are missing or values cannot be aligned unambiguously.
    """
    if not blend:
        return deepcopy(blend)
    if source_years is None:
        raise ValueError(
            "Fuel blend source-year labels are missing. Rebuild the vehicle model "
            "from its inputs before selecting years or constructing an inventory."
        )
    source, selected = np.asarray(source_years), np.asarray(years)
    for name, labels in (("source", source), ("selected", selected)):
        if labels.ndim != 1 or not labels.size or len(set(labels)) != labels.size:
            raise ValueError(f"Fuel blend {name} years must be nonempty and unique.")
    positions = {year: i for i, year in enumerate(source)}
    missing = [year for year in selected.tolist() if year not in positions]
    if missing:
        raise ValueError(
            f"Fuel blend has no source-year values for {missing}. "
            "Construct a new model with fuel inputs for those years."
        )
    indices = [positions[year] for year in selected]
    result = deepcopy(blend)
    for fuel, components in result.items():
        for role, component in components.items():
            for field in YEAR_FIELDS:
                if field not in component:
                    continue
                values = np.asarray(component[field])
                if values.ndim == 0:
                    continue
                if values.shape != source.shape:
                    raise ValueError(
                        f"Fuel blend {fuel!r}, {role}: {field} must be scalar or "
                        f"have one value per source year {source.tolist()}. "
                        "Keep the original blend vectors when selecting model years."
                    )
                component[field] = values[indices].copy()
    return result
