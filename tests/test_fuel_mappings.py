"""Fuel mapping failures should precede costly inventory allocation."""

from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from carculator_utils.background_systems import BackgroundSystemModel
from carculator_utils.inventory import Inventory, get_dict_input, validate_fuel_mappings


def test_default_fuel_suppliers_exist_in_the_bundled_index():
    background = BackgroundSystemModel()
    blends = background.define_fuel_blends(
        ["ICEV-d", "ICEV-p", "ICEV-g", "FCEV"], "CH", [2020, 2030]
    )
    validate_fuel_mappings(blends, get_dict_input())


def test_missing_supplier_fails_before_inventory_matrix_allocation(monkeypatch):
    supplier = ("missing supplier", "CH", "kilogram", "fuel")
    component = {"type": "test fuel", "name": supplier}
    model = SimpleNamespace(
        array=xr.DataArray(
            np.ones((1, 1, 1, 1, 1)),
            dims=("size", "powertrain", "parameter", "year", "value"),
            coords={
                "size": ["Small"],
                "powertrain": ["ICEV-p"],
                "parameter": ["TtW energy"],
                "year": [2020],
                "value": [0],
            },
        ),
        fuel_blend={"petrol": {"primary": component, "secondary": component}},
    )

    class MinimalModel:
        array = model.array
        fuel_blend = model.fuel_blend
        _fuel_blend_years = (2020,)

        def __getitem__(self, parameter):
            return self.array.sel(parameter=parameter)

    def unexpected_allocation(*args):
        pytest.fail("Inventory allocation must not run with an unresolved supplier")

    monkeypatch.setattr(Inventory, "get_A_matrix", unexpected_allocation)
    with pytest.raises(KeyError, match="petrol.*primary.*test fuel.*missing supplier"):
        Inventory(MinimalModel())
