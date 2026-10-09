"""Exact species characterization and transparent legacy coefficient provenance."""

import hashlib

import numpy as np
import pytest

from carculator_utils import DATA_DIR
from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.emission_provenance import (
    get_emission_factor_provenance,
    load_biosphere_extensions,
)
from carculator_utils.inventory import get_dict_input


def test_emission_table_fingerprints_and_qualification():
    provenance = get_emission_factor_provenance()
    assert provenance["source_version"] == "unverified"
    assert not provenance["source_extraction_available"]
    for filename, record in provenance["files"].items():
        assert (
            hashlib.sha256(
                (DATA_DIR / "emission_factors" / filename).read_bytes()
            ).hexdigest()
            == record["sha256"]
        )
    assert provenance["manual_multipliers"]["truck"]["Ammonia"] == 10


@pytest.mark.family
@pytest.mark.parametrize(
    "method,indicator,category,factor",
    [
        ("recipe", "midpoint", "photochemical oxidant formation: human health", 0.363),
        ("ef", "midpoint", "photochemical oxidant formation: human health", 1.69),
    ],
)
def test_exact_ethylene_reaches_completed_inventory_and_lcia(
    method, indicator, category, factor, tmp_path
):
    car = pytest.importorskip("carculator")
    inputs = car.CarInputParameters()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs, scope={"size": ["Medium"], "powertrain": ["ICEV-p"], "year": [2025]}
    )
    model = car.CarModel(array)
    model.set_all()
    inventory = car.InventoryCar(
        model, scenario="static", method=method, indicator=indicator
    )
    original = get_dict_input()
    assert all(inventory.inputs[key] == index for key, index in original.items())
    assert np.isfinite(inventory.calculate_impacts()).all()
    (column,) = inventory.find_input_indices(("transport, car, ICEV-p, ",))
    amounts = []
    for environment, record in zip(
        ("urban", "suburban", "rural"), load_biosphere_extensions()["flows"]
    ):
        label = (record["label"][0], tuple(record["label"][1]), record["label"][2])
        row = inventory.inputs[label]
        expected = model[f"Ethene direct emissions, {environment}"].item()
        assert expected > 0
        np.testing.assert_allclose(-inventory.A[0, row, column, 0], expected)
        actual = inventory.B.sel(category=category).isel(activity=row).values
        np.testing.assert_allclose(actual, factor)
        amounts.append(expected)
    assert sum(amounts) > 0
    for version in ("3.9", "3.10"):
        content = inventory.export_lci(
            software="simapro",
            format="string",
            ecoinvent_version=version,
            directory=tmp_path,
        )
        assert "Ethylene" in content
