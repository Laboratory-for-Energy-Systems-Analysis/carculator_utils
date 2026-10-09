"""Packaged coefficient provenance, alignment and scientific unit boundaries."""

import hashlib
import json

import numpy as np
import pytest
from scipy import sparse

from carculator_utils import DATA_DIR
from carculator_utils.inventory import get_dict_impact_categories, get_dict_input


def test_complete_bundle_matches_its_verified_manifest():
    folder = DATA_DIR / "IAM"
    manifest = json.loads((folder / "build_manifest.json").read_text())
    assert manifest["complete"] is True
    assert manifest["ecoinvent_version"] == "3.12"
    assert manifest["system_model"] == "cutoff"
    assert manifest["packages"]["premise"] == "2.5.4"
    assert len(manifest["databases"]) == 13
    assert len(list(folder.glob("B_matrix_*.npz"))) == 57
    for name, checksum in manifest["resource_hashes"].items():
        assert (
            hashlib.sha256((folder / name).read_bytes()).hexdigest() == checksum
        ), name
    inputs = get_dict_input()
    assert len(inputs) == manifest["label_count"]
    matrix = sparse.load_npz(folder / "A_matrix.npz")
    assert matrix.shape == (len(inputs), len(inputs))
    assert np.isfinite(matrix.data).all()
    for method, indicator in (
        ("recipe", "midpoint"),
        ("recipe", "endpoint"),
        ("ef", "midpoint"),
    ):
        expected = (len(get_dict_impact_categories(method, indicator)), len(inputs))
        for path in folder.glob(f"B_matrix_{method}_{indicator}_*.npz"):
            coefficients = sparse.load_npz(path)
            assert coefficients.shape == expected, path.name
            assert np.isfinite(coefficients.data).all(), path.name


def test_nmc532_market_purchases_one_kg_of_the_selected_chemistry():
    """A kg of traded battery must purchase a kg of packs, not kg of cells."""
    inputs = get_dict_input()
    name = "market for battery, Li-ion, NMC532, rechargeable"
    product = "battery, Li-ion, NMC532, rechargeable"
    column = inputs[(name, "GLO", "kilogram", product)]
    matrix = sparse.load_npz(DATA_DIR / "IAM/A_matrix.npz")
    rows = [
        index
        for label, index in inputs.items()
        if len(label) == 4
        and label[0] == "battery production, Li-ion, NMC532, rechargeable"
    ]
    assert len(rows) == 2  # CN and RoW production in the global market.
    assert matrix[column, column] == 1
    assert -float(matrix[rows, column].sum()) == pytest.approx(1, abs=1e-7)
    assert not any("NMC523" in label[0] for label in inputs)


def test_expanded_foreground_has_no_direct_burdens_in_b():
    folder = DATA_DIR / "IAM"
    inputs = get_dict_input()
    manifest = json.loads((folder / "build_manifest.json").read_text())
    columns = [inputs[tuple(row["label"])] for row in manifest["foreground"]]
    for path in folder.glob("B_matrix_*.npz"):
        assert sparse.load_npz(path)[:, columns].nnz == 0, path.name


def test_historical_scenarios_share_the_same_npI_background():
    folder = DATA_DIR / "IAM"
    for year in (2005, 2010, 2020):
        original = sparse.load_npz(
            folder / f"B_matrix_recipe_midpoint_remind_SSP2-NPi_{year}.npz"
        )
        for scenario in ("SSP2-PkBudg1000", "SSP2-PkBudg650"):
            other = sparse.load_npz(
                folder / f"B_matrix_recipe_midpoint_remind_{scenario}_{year}.npz"
            )
            assert (original != other).nnz == 0
