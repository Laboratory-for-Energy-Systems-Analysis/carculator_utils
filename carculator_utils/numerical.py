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
