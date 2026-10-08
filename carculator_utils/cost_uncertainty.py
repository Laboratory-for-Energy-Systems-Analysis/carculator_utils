"""Retain projected-cost uncertainty with the input sample that owns it."""

import numpy as np

from .battery_costs import SENSITIVITY

GENERAL_FACTOR = "_cost_factor"
FCEV_FACTOR = "_cost_factor_fcev"
DISTRIBUTIONS = {
    GENERAL_FACTOR: (0.7, 1.0, 1.3),
    FCEV_FACTOR: (3.0, 5.0, 6.0),
}


def sample_cost_factors(iterations, seed=None, *, stochastic=True):
    """Draw dimensionless factors without consuming parameter or global RNGs.

    Independent child streams keep the general and bus fuel-cell factors
    separate, with stable prefixes when the requested sample count changes.
    Static and sensitivity calculations use the modes of these distributions.
    """
    if not stochastic:
        return {
            name: np.full(iterations, mode)
            for name, (_, mode, _) in DISTRIBUTIONS.items()
        }
    streams = np.random.SeedSequence(seed).spawn(len(DISTRIBUTIONS))
    return {
        name: np.random.default_rng(stream).triangular(*bounds, size=iterations)
        for (name, bounds), stream in zip(DISTRIBUTIONS.items(), streams)
    }


def attach_cost_factors(array, factors=None):
    """Return an array whose cost factors follow its labelled ``value`` axis.

    Existing factors take precedence over sample-count heuristics: selecting
    one Monte Carlo sample must retain its draw. Legacy arrays without these
    coordinates receive local, unseeded draws, or deterministic factors for
    single-sample and sensitivity arrays. The caller's array is not mutated.
    """
    present = [name in array.coords for name in DISTRIBUTIONS]
    if factors is None and not any(present):
        sensitivity = bool(array.attrs.get(SENSITIVITY, False)) or (
            "reference" in array.value.values.tolist()
        )
        factors = sample_cost_factors(
            array.sizes["value"],
            stochastic=array.sizes["value"] > 1 and not sensitivity,
        )
    if factors is not None:
        array = array.assign_coords(
            {
                name: ("value", np.array(values, copy=True))
                for name, values in factors.items()
            }
        )
    for name, (lower, _, upper) in DISTRIBUTIONS.items():
        if name not in array.coords:
            raise ValueError(f"Missing cost-factor coordinate {name!r}.")
        factor = array.coords[name]
        if factor.dims != ("value",):
            raise ValueError(
                f"Cost-factor coordinate {name!r} must have dimension 'value'."
            )
        values = factor.values
        if (
            not np.issubdtype(values.dtype, np.number)
            or np.iscomplexobj(values)
            or not np.isfinite(values).all()
            or np.any((values < lower) | (values > upper))
        ):
            raise ValueError(
                f"Cost-factor coordinate {name!r} must be finite and within "
                f"[{lower}, {upper}]."
            )
    return array
