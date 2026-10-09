"""Keep model inputs separate from results when completing a model again."""

from functools import wraps

import numpy as np

from .input_completeness import validate_input_completeness


def repeatable_run(method):
    """Rebuild from retained inputs, preserving explicit edits to completed cells.

    Output parameters must never become the next run's physical assumptions.
    Select/reorder existing coordinates freely. New coordinates require a new
    model. PHEV intermediate inputs are retained privately after output removal.
    """

    @wraps(method)
    def run(self, *args, **kwargs):
        previous = getattr(self, "_completed_run_array", None)
        current = self.array
        if previous is None:
            inputs = current.copy(deep=True)
        else:
            selection = {dim: current[dim].values for dim in current.dims}
            old = previous.sel(selection)
            powertrains = list(selection["powertrain"])
            for aggregate, components in {
                "PHEV-p": ("PHEV-c-p", "PHEV-e"),
                "PHEV-d": ("PHEV-c-d", "PHEV-e"),
            }.items():
                if aggregate in powertrains:
                    powertrains.extend(p for p in components if p not in powertrains)
            if len(powertrains) != len(selection["powertrain"]):
                powertrains = [
                    p
                    for p in self._model_run_inputs.powertrain.values
                    if p in powertrains
                ]
            input_selection = dict(selection, powertrain=powertrains)
            inputs = self._model_run_inputs.sel(input_selection).copy(deep=True)
            # Comparing against the previous output distinguishes caller edits
            # from parameters calculated by the model itself.
            changed = ~((current == old) | (np.isnan(current) & np.isnan(old)))
            for aggregate in ("PHEV-p", "PHEV-d"):
                if aggregate in current.powertrain and bool(
                    changed.sel(powertrain=aggregate).any()
                ):
                    raise ValueError(
                        "Edit PHEV component inputs, not aggregated outputs; "
                        "construct a fresh model with the changed component inputs."
                    )
            inputs.loc[selection] = inputs.sel(selection).where(~changed, current)
        self.array = inputs.copy(deep=True)
        try:
            validate_input_completeness(self)
            result = method(self, *args, **kwargs)
            if previous is not None:
                order = [
                    p for p in current.powertrain.values if p in self.array.powertrain
                ]
                self.array = self.array.sel(powertrain=order)
        except Exception:
            self.array = current
            raise
        self._model_run_inputs = inputs
        self._completed_run_array = self.array.copy(deep=True)
        return result

    return run
