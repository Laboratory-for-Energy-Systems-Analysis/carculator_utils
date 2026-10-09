"""Advertised road fuels must have physical properties and resolvable suppliers."""

from types import SimpleNamespace

import pytest
import xarray as xr

from carculator_utils.background_systems import (
    get_default_fuels,
    get_fuels_specs,
    get_unavailable_fuels,
)
from carculator_utils.fuel_supply import register_fuel_suppliers
from carculator_utils.inventory import get_dict_input, validate_fuel_mappings
from carculator_utils.model import VehicleModel


def test_every_advertised_fuel_has_a_resolvable_delivery_chain():
    specs = get_fuels_specs()
    unavailable = get_unavailable_fuels()
    for category, catalogue in get_default_fuels().items():
        assert catalogue["primary"] in catalogue["all"]
        assert catalogue["secondary"] in catalogue["all"]
        for name in catalogue["all"]:
            assert name not in unavailable
            specification = specs[name]
            assert specification["lhv"] > 0
            assert specification["density"] > 0
            blend = {
                category: {
                    role: {"type": name, "name": specification["name"]}
                    for role in ("primary", "secondary")
                }
            }
            index = get_dict_input()
            register_fuel_suppliers(index, blend)
            validate_fuel_mappings(blend, index)


@pytest.mark.parametrize("name,reason", list(get_unavailable_fuels().items()))
def test_unavailable_fuels_fail_at_model_input_with_a_reason(name, reason):
    model = SimpleNamespace(
        array=xr.DataArray([0], dims="year", coords={"year": [2025]}),
        bs=SimpleNamespace(fuel_specs=get_fuels_specs()),
    )
    with pytest.raises(ValueError) as error:
        VehicleModel.check_fuel_blend(
            model, {name.split(" - ")[0]: {"primary": {"type": name, "share": 1}}}
        )
    assert name in str(error.value)
    assert reason in str(error.value)
