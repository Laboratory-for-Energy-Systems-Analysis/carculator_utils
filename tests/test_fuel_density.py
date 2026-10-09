"""Blend density closes the mass balance of known component volumes."""

from copy import deepcopy

import numpy as np
import pytest
import xarray as xr

from carculator_utils.background_systems import BackgroundSystemModel
from carculator_utils.model import VehicleModel

FUELS = {
    "petrol": ("petrol", "petrol - bioethanol - sugarbeet"),
    "diesel": ("diesel", "diesel - biodiesel - cooking oil"),
    "methane": ("methane", "methane - biomethane - sewage sludge"),
    "hydrogen": ("hydrogen - smr - natural gas", "hydrogen - electrolysis - PEM"),
}


def fuel_array(powertrain):
    coords = {
        "size": ["Small", "Medium"],
        "powertrain": [powertrain],
        "parameter": ["LHV fuel MJ per kg", "fuel density per kg"],
        "year": [2030, 2020, 2025],
        "value": [9, 2],
    }
    return xr.DataArray(
        np.zeros(tuple(len(v) for v in coords.values()), dtype=np.float32),
        coords=coords,
        dims=tuple(coords),
    )


@pytest.mark.parametrize(
    "powertrain,fuel",
    [
        ("ICEV-p", "petrol"),
        ("HEV-p", "petrol"),
        ("PHEV-c-p", "petrol"),
        ("ICEV-d", "diesel"),
        ("HEV-d", "diesel"),
        ("PHEV-c-d", "diesel"),
        ("ICEV-g", "methane"),
        ("FCEV", "hydrogen"),
    ],
)
def test_catalog_density_conserves_known_component_volumes(powertrain, fuel):
    specs = BackgroundSystemModel().fuel_specs
    # One mixed batch and both pure-component endpoints, in array.year order.
    volumes = np.array([[1.0, 3.0], [1.0, 0.0], [0.0, 1.0]])
    densities = np.array([specs[name]["density"] for name in FUELS[fuel]])
    masses = volumes * densities
    total_mass = masses.sum(axis=1)
    source = {
        fuel: {
            role: {"type": name, "share": (masses[:, i] / total_mass).tolist()}
            for i, (role, name) in enumerate(zip(("primary", "secondary"), FUELS[fuel]))
        }
    }
    before = deepcopy(source)
    array = fuel_array(powertrain)
    original = array.copy(deep=True)
    model = VehicleModel(array, fuel_blend=source)
    model.set_average_lhv()

    # Recover the input batch mass from its known total volume and model density.
    recovered_mass = model["fuel density per kg"] * xr.DataArray(
        volumes.sum(axis=1), dims="year", coords={"year": array.year}
    )
    expected = np.broadcast_to(total_mass.reshape(1, 1, 3, 1), (2, 1, 3, 2))
    np.testing.assert_allclose(recovered_mass, expected, rtol=2e-6)
    assert model.array.year.values.tolist() == [2030, 2020, 2025]
    assert model.array.value.values.tolist() == [9, 2]
    assert source == before
    xr.testing.assert_identical(array, original)


@pytest.mark.parametrize("shape", ["scalar", "one-element", "yearly"])
def test_density_overrides_conserve_component_volumes(shape):
    densities = np.array([[0.81, 0.89], [0.83, 0.90], [0.85, 0.92]])
    if shape != "yearly":
        densities[:] = densities[0]
    volumes = np.array([[2.0, 3.0], [5.0, 1.0], [1.0, 7.0]])
    masses = volumes * densities
    total_mass = masses.sum(axis=1)
    components = {}
    for i, (role, name) in enumerate(zip(("primary", "secondary"), FUELS["diesel"])):
        density = densities[:, i].tolist()
        if shape == "scalar":
            density = density[0]
        elif shape == "one-element":
            density = density[:1]
        components[role] = {
            "type": name,
            "share": (masses[:, i] / total_mass).tolist(),
            "density": density,
        }
    source = {"diesel": components}
    before = deepcopy(source)
    model = VehicleModel(fuel_array("ICEV-d"), fuel_blend=source)
    model.set_average_lhv()

    recovered_mass = model["fuel density per kg"] * xr.DataArray(
        volumes.sum(axis=1), dims="year", coords={"year": model.array.year}
    )
    expected = np.broadcast_to(total_mass.reshape(1, 1, 3, 1), (2, 1, 3, 2))
    np.testing.assert_allclose(recovered_mass, expected, rtol=2e-6)
    assert source == before


def test_primary_only_partial_model_keeps_density():
    model = VehicleModel(
        fuel_array("ICEV-d"),
        fuel_blend={"diesel": {"primary": {"type": "diesel", "share": 1}}},
    )
    # Exercise the shared method's existing support for partial model state.
    model.fuel_blend["diesel"].pop("secondary")
    with np.errstate(divide="raise", invalid="raise"):
        model.set_average_lhv()
    np.testing.assert_allclose(model["fuel density per kg"], 0.83, rtol=2e-6)
