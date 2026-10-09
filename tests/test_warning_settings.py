"""Importing model code must not silence warnings in the caller's application."""

import importlib
import warnings

import numpy as np
import pandas as pd
import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "carculator_utils.inventory",
        "carculator_utils.utils",
        "carculator.inventory",
        "carculator_bus.inventory",
        "carculator_bus.model",
        "carculator_truck.inventory",
        "carculator_truck.model",
        "carculator_two_wheeler.inventory",
    ],
)
def test_import_preserves_caller_warning_and_pandas_settings(module_name):
    module = pytest.importorskip(module_name)
    with (
        warnings.catch_warnings(record=True) as captured,
        pd.option_context("mode.chained_assignment", "warn"),
    ):
        warnings.simplefilter("always", FutureWarning)
        warnings.simplefilter("always", np.VisibleDeprecationWarning)
        importlib.reload(module)
        warnings.warn("future probe", FutureWarning)
        warnings.warn("numpy probe", np.VisibleDeprecationWarning)
        assert [str(item.message) for item in captured] == [
            "future probe",
            "numpy probe",
        ]
        assert pd.options.mode.chained_assignment == "warn"
