"""Trace emission coefficients and append exact characterized biosphere flows."""

import json

import numpy as np

from . import DATA_DIR


def get_emission_factor_provenance():
    """Return table fingerprints and the qualification of legacy adjustments."""
    with (DATA_DIR / "emission_factors" / "provenance.json").open(
        encoding="utf-8"
    ) as stream:
        return json.load(stream)


def load_biosphere_extensions():
    """Read exact Ethylene flows and same-method factors from ecoinvent 3.12."""
    with (DATA_DIR / "emission_factors" / "ethylene_characterization.json").open(
        encoding="utf-8"
    ) as stream:
        return json.load(stream)


def flow_label(record):
    name, compartments, unit = record["label"]
    return name, tuple(compartments), unit


def register_biosphere_extensions(inputs):
    """Append flows to a private index, preserving every bundled matrix position."""
    for record in load_biosphere_extensions()["flows"]:
        label = flow_label(record)
        if label not in inputs:
            inputs[label] = max(inputs.values()) + 1


def fill_biosphere_characterization(matrix, inputs, method, indicator, categories):
    """Populate private B columns with stationary elementary-flow factors.

    The method definitions are the same ones used to build the shipped B
    matrices. Direct-flow factors do not vary with the IAM supply scenario.
    Absence of an explicit factor is recorded in the provenance, not hidden.
    """
    for record in load_biosphere_extensions()["flows"]:
        label = flow_label(record)
        if label not in inputs:
            continue
        factors = record["factors"][f"{method}:{indicator}"]
        values = np.array([factors[category]["amount"] for category in categories])
        if not np.isfinite(values).all():
            raise ValueError(f"Nonfinite characterization for {label}.")
        matrix[:, :, inputs[label]] = values
