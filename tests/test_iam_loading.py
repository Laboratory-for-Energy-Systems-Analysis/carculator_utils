"""Never mix matrix bundles or select an LCIA method from a directory name."""

import importlib

import numpy as np
import pytest
from scipy import sparse


@pytest.fixture
def inventory(tmp_path, monkeypatch):
    module = importlib.import_module("carculator_utils.inventory")
    folder = tmp_path / "reference-background" / "IAM"
    folder.mkdir(parents=True)
    monkeypatch.setattr(module, "IAM_FILES_DIR", folder)
    monkeypatch.setattr(module, "DATA_DIR", folder.parent)
    obj = module.Inventory.__new__(module.Inventory)
    obj.inputs = {
        ("example", "GLO", "kilogram", "example"): 0,
        ("Carbon dioxide, fossil", ("air",), "kilogram"): 1,
    }
    monkeypatch.setattr(module, "get_dict_input", lambda: obj.inputs.copy())
    obj.method, obj.indicator, obj.scenario = "ef", "midpoint", "static"
    obj.impact_categories = {"test category": {"unit": "test"}}
    # Keep this fixture about bundle selection/alignment, independently of the
    # separate elementary-flow extension rules and their published-CF tests.
    monkeypatch.setattr(module, "fill_biosphere_characterization", lambda *args: None)
    return obj, folder


def test_method_selection_ignores_parent_directory_names(inventory):
    obj, folder = inventory
    sparse.save_npz(
        folder / "B_matrix_ef_midpoint_static.npz", sparse.csr_matrix([[2, 3]])
    )
    sparse.save_npz(
        folder / "B_matrix_recipe_midpoint_static.npz", sparse.csr_matrix([[99, 99]])
    )
    result = obj.get_B_matrix()
    np.testing.assert_array_equal(result.values, [[[2, 3]]])


def test_missing_background_is_not_silently_zero(inventory):
    obj, _ = inventory
    with pytest.raises(FileNotFoundError, match="Missing required background matrix"):
        obj.get_B_matrix()


@pytest.mark.parametrize("values", [[[1]], [[1, 2, 3]], [[1, 2], [3, 4]]])
def test_characterization_must_match_index_and_categories(inventory, values):
    obj, folder = inventory
    sparse.save_npz(
        folder / "B_matrix_ef_midpoint_static.npz", sparse.csr_matrix(values)
    )
    with pytest.raises(ValueError, match="not aligned"):
        obj.get_B_matrix()


def test_a_must_match_the_same_index(inventory):
    obj, folder = inventory
    sparse.save_npz(folder / "A_matrix.npz", sparse.eye(3, format="csr"))
    with pytest.raises(ValueError, match="not aligned"):
        obj.get_A_matrix()


@pytest.mark.parametrize("matrix", ["A", "B"])
def test_packaged_nonfinite_coefficients_fail(inventory, matrix):
    obj, folder = inventory
    values = np.eye(2) if matrix == "A" else np.ones((1, 2))
    values[0, 0] = np.nan
    filename = "A_matrix.npz" if matrix == "A" else "B_matrix_ef_midpoint_static.npz"
    sparse.save_npz(folder / filename, sparse.csr_matrix(values))
    with pytest.raises(ValueError, match="[Nn]onfinite"):
        (obj.get_A_matrix if matrix == "A" else obj.get_B_matrix)()
