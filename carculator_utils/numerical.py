"""Small numerical contracts shared by vehicle sizing models."""

import numpy as np


class ConvergenceError(ValueError):
    """Sizing could not produce a finite converged vehicle state."""


def iterate_until_converged(
    read_state, *, label, rtol=1e-3, atol=1e-6, max_iterations=100
):
    """Yield sizing steps until every cell converges, or raise with diagnostics.

    ``read_state`` returns a labelled array after each iteration. Absolute and
    relative tolerances avoid division by zero and cancellation between cells.
    """
    if max_iterations < 1 or rtol < 0 or atol < 0:
        raise ValueError(
            "Convergence tolerances must be nonnegative and iterations positive."
        )
    previous = np.asarray(read_state(), dtype=np.float64).copy()
    for iteration in range(1, max_iterations + 1):
        yield iteration
        state = read_state()
        current = np.asarray(state, dtype=np.float64)
        if current.shape != previous.shape:
            raise ConvergenceError(f"{label}: shape changed during sizing.")
        bad = ~np.isfinite(current)
        converged = np.abs(current - previous) <= atol + rtol * np.abs(current)
        if bad.any() or iteration == max_iterations and not converged.all():
            index = tuple(np.argwhere(bad if bad.any() else ~converged)[0])
            coordinates = (
                {
                    d: state.coords[d].values.tolist()[i]
                    for d, i in zip(state.dims, index)
                }
                if hasattr(state, "dims")
                else index
            )
            reason = "non-finite state" if bad.any() else "iteration limit reached"
            raise ConvergenceError(
                f"{label}: {reason} after {iteration} iterations at {coordinates}."
            )
        if converged.all():
            return
        previous = current.copy()


def capital_recovery_factor(rate, years):
    """Annual payment per unit of capital, for end-of-year payments.

    ``rate`` is the annual fractional interest rate and ``years`` the positive
    lifetime in years. Scalars, numpy arrays and labelled xarray arrays are
    supported. The zero-rate limit is ``1 / years``; log1p/expm1 avoid loss of
    precision near zero interest. Invalid financial inputs raise ValueError.
    """
    import xarray as xr

    rate = (
        rate.astype(float) if hasattr(rate, "astype") else np.asarray(rate, dtype=float)
    )
    years = (
        years.astype(float)
        if hasattr(years, "astype")
        else np.asarray(years, dtype=float)
    )
    if np.any(~np.isfinite(rate)) or np.any(rate <= -1):
        raise ValueError("Annual interest rate must be finite and greater than -1.")
    if np.any(~np.isfinite(years)) or np.any(years <= 0):
        raise ValueError("Lifetime in years must be positive and finite.")
    safe_rate = rate + (rate == 0)
    factor = safe_rate / -np.expm1(-years * np.log1p(safe_rate))
    where = (
        xr.where
        if isinstance(rate, xr.DataArray) or isinstance(years, xr.DataArray)
        else np.where
    )
    return where(rate == 0, 1 / years, factor)
