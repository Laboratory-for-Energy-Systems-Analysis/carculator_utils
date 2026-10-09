"""Retain the distinction between an input zero and an absent input record."""

import numpy as np
import xarray as xr

STATUS = "input_status"
MISSING_INPUT = "missing_input"
MISSING, DERIVED, PROVIDED, NOT_APPLICABLE = -1, 0, 1, 2


def attach_input_status(array, inputs):
    """Attach labelled record coverage; status survives selection/interpolation.

    Required cells come from the vehicle subclass's bundled input schema. Extra
    output labels are derived; input names outside their declared scopes are not
    applicable. Missing required records remain distinguishable from real zeros.
    """
    template = array.isel(value=0, drop=True)
    status = xr.full_like(template, NOT_APPLICABLE, dtype=np.int8)
    expected = inputs._expected_input_records
    names = {r["name"] for r in expected}
    derived = [p for p in array.parameter.values if p not in names]
    status.loc[dict(parameter=derived)] = DERIVED

    def selection(record):
        selected = {"parameter": record["name"]}
        for dim, field in (
            ("size", "sizes"),
            ("powertrain", "powertrain"),
            ("year", "year"),
        ):
            labels = (
                record[field]
                if isinstance(record[field], (list, tuple))
                else [record[field]]
            )
            selected[dim] = [x for x in labels if x in array[dim]]
            if not selected[dim]:
                return None
        return selected if record["name"] in array.parameter else None

    for record in expected:
        selected = selection(record)
        if selected is not None:
            status.loc[selected] = MISSING
    for record in inputs.metadata.values():
        selected = selection(record)
        if selected is not None:
            status.loc[selected] = PROVIDED
    return array.assign_coords(
        {
            STATUS: status,
            MISSING_INPUT: (status == MISSING).astype(float),
        }
    )


def mark_inputs_provided(array, parameters, **selection):
    """Return a copy marking explicitly supplied cells (including zeros) as inputs.

    Use after assigning intentional zeros to cells whose records were missing.
    Nonzero array/constructor overrides are recognized automatically at preflight.
    """
    result = array.copy(deep=True)
    if STATUS not in result.coords:
        raise ValueError("Input coverage is unavailable; rebuild the input array.")
    result.coords[STATUS].loc[dict(parameter=parameters, **selection)] = PROVIDED
    result.coords[MISSING_INPUT].loc[dict(parameter=parameters, **selection)] = 0
    return result


def availability(array, vehicle_type):
    """Existing family technology policy, before sizing/compliance calculations."""
    size, powertrain, year = array.coords["size"], array.powertrain, array.year
    active = xr.ones_like(array.isel(parameter=0, value=0, drop=True), dtype=bool)
    if vehicle_type == "car":
        active &= ~(
            powertrain.isin(
                [
                    "BEV",
                    "FCEV",
                    "HEV-d",
                    "HEV-p",
                    "PHEV-p",
                    "PHEV-d",
                    "PHEV-e",
                    "PHEV-c-p",
                    "PHEV-c-d",
                ]
            )
            & (year < 2013)
        )
        active &= ~((size == "Micro") & (powertrain != "BEV"))
    elif vehicle_type == "truck":
        active &= ~(
            powertrain.isin(["BEV", "FCEV", "PHEV-d", "PHEV-e", "PHEV-c-d", "HEV-d"])
            & (year < 2020)
        )
    elif vehicle_type == "bus":
        active &= ~(
            powertrain.isin(["BEV-depot", "BEV-opp", "BEV-motion"]) & (year < 2020)
        )
        active &= ~(
            size.str.contains("coach") & powertrain.isin(["BEV-opp", "BEV-motion"])
        )
        active &= ~(
            (powertrain == "BEV-motion")
            & size.isin(["13m-city-double", "13m-coach", "13m-coach-double"])
        )
    elif vehicle_type == "two-wheeler":
        active &= ~((powertrain == "Human") & (size != "Bicycle <25"))
        active &= ~((powertrain == "BEV") & ((size == "Moped <4kW") | (year <= 2010)))
        active &= ~(
            (powertrain == "ICEV-p")
            & size.isin(["Kick-scooter", "Bicycle <25", "Bicycle <45", "Bicycle cargo"])
        )
    # Aggregated PHEVs are outputs of the component runs, not independent inputs.
    return active & ~powertrain.isin(["PHEV-p", "PHEV-d"])


def validate_input_completeness(model):
    """Fail before sizing if an active vehicle lacks a declared input record.

    Hand-built arrays without coverage retain compatibility. This validates
    record completeness, not the empirical correctness of provided values.
    """
    array = model.array
    if STATUS not in array.coords:
        return
    active = availability(array, model.vehicle_type)
    # Preserve a missing bracketing input during linear year interpolation.
    coverage = array.coords[MISSING_INPUT]
    missing = coverage > 0
    invalid = missing & active & ((coverage < 1) | (array == 0) | ~np.isfinite(array))
    if bool(invalid.any()):
        locations = np.argwhere(invalid.transpose(*array.dims).values)
        labels = [
            {
                dim: array[dim].values.tolist()[index]
                for dim, index in zip(array.dims, row)
            }
            for row in locations[:8]
        ]
        raise ValueError(
            f"Missing required input records for active {model.vehicle_type} cells: {labels}. "
            "Supply these records or explicit values; for intentional zero array "
            "overrides use mark_inputs_provided()."
        )
