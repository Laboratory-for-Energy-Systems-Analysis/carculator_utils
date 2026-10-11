"""Dry tank mass and MJ/kWh boundaries from Evangelisti (2017) supplementary data."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

from carculator_utils import DATA_DIR
from carculator_utils.inventory import get_dict_input

FOLDER = DATA_DIR / "IAM"
SPECIFICATION = json.loads((FOLDER / "hydrogen_tank_corrections.json").read_text())
RECIPES = SPECIFICATION["recipes"]


@pytest.mark.parametrize("recipe", RECIPES, ids=["HDPE", "aluminium"])
def test_export_references_record_the_corrected_boundary(recipe):
    references = json.loads((DATA_DIR / "export/references.json").read_text())
    record = references[recipe["label"][0]]
    assert "10.1016/j.jclepro.2016.11.159" in record["source"]
    assert str(recipe["dry_material_mass_kg"]) in record["comment"]
    assert "excluding stored hydrogen" in record["comment"]
    assert "MJ / 3.6" in record["comment"]


@pytest.mark.parametrize("recipe", RECIPES, ids=["HDPE", "aluminium"])
def test_packaged_tank_has_one_kg_of_material_not_processing_services(recipe):
    inputs = get_dict_input()
    matrix = sparse.load_npz(FOLDER / "A_matrix.npz")
    column = inputs[tuple(recipe["label"])]
    amounts = {
        key: -float(matrix[inputs[tuple(label)], column])
        for key, label in SPECIFICATION["suppliers"].items()
    }
    assert matrix[column, column] == 1
    assert sum(amounts[key] for key in recipe["materials_kg"]) == pytest.approx(1)
    assert amounts["steel_working"] == amounts["steel"]
    if "hdpe" in recipe["materials_kg"]:
        # Independent expectations transcribed from the published recipe.
        assert amounts["carbon_fibre"] == pytest.approx(19.78 / 87.71)
        assert amounts["hdpe"] == pytest.approx(10.26 / 87.71)
        assert amounts["electricity"] * 87.71 * 3.6 == pytest.approx(12.87)
        assert amounts["aluminium_rolling"] == 0
    else:
        assert amounts["aluminium"] == pytest.approx((35.7 + 7.021) / 113.169)
        assert amounts["aluminium_rolling"] == pytest.approx(35.7 / 113.169)
        assert amounts["electricity"] * 113.169 * 3.6 == pytest.approx(16.422)
        assert amounts["hdpe"] == 0


@pytest.fixture
def builder():
    path = Path(__file__).parents[1] / "dev/correct_hydrogen_tanks.py"
    if not path.exists():
        pytest.skip("Source-only build tool")
    spec = importlib.util.spec_from_file_location("correct_hydrogen_tanks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def legacy_matrix():
    # Small source fixture, independent of the packaged numerical matrix.
    labels = [tuple(row["label"]) for row in RECIPES]
    labels += [tuple(label) for label in SPECIFICATION["suppliers"].values()]
    labels += [("unrelated", "GLO", "kilogram", "unrelated")]
    matrix = sparse.eye(len(labels), format="lil")
    matrix[-1, 2] = -0.37  # An unrelated foreground column must survive.
    for column, recipe in enumerate(RECIPES):
        amounts = {k: sum(v) for k, v in recipe["materials_kg"].items()}
        amounts.update(recipe["processing_kg"])
        amounts["electricity"] = recipe["electricity_MJ"]
        for key, value in amounts.items():
            row = labels.index(tuple(SPECIFICATION["suppliers"][key]))
            matrix[row, column] = -np.float32(value / recipe["legacy_denominator_kg"])
    return labels, matrix.tocsr()


def test_correction_is_private_targeted_and_accepts_corrected_upstream(
    builder, legacy_matrix
):
    labels, matrix = legacy_matrix
    original = matrix.copy()
    updated, audit = builder.corrected_matrix(matrix, labels, SPECIFICATION)
    assert (matrix != original).nnz == 0
    assert (updated[:, 2:] != original[:, 2:]).nnz == 0
    again, second_audit = builder.corrected_matrix(updated, labels, SPECIFICATION)
    assert (again != updated).nnz == 0
    assert audit == second_audit
    # A future Brightway build imports the fixed premise workbook as float32.
    rebuilt, _ = builder.corrected_matrix(
        updated.astype("float32"), labels, SPECIFICATION
    )
    np.testing.assert_array_equal(rebuilt[:, :2].toarray(), updated[:, :2].toarray())


@pytest.mark.parametrize("change", ["amount", "extra", "production", "nonfinite"])
def test_changed_upstream_recipe_fails_before_overwrite(builder, legacy_matrix, change):
    labels, matrix = legacy_matrix
    matrix = matrix.tolil()
    if change == "extra":
        matrix[-1, 0] = -0.1
    elif change == "production":
        matrix[0, 0] = 2
    else:
        matrix[2, 0] = -0.3 if change == "amount" else np.nan
    with pytest.raises(ValueError, match="Unrecognized upstream"):
        builder.corrected_matrix(matrix.tocsr(), labels, SPECIFICATION)


def test_missing_and_duplicate_labels_fail(builder, legacy_matrix):
    labels, matrix = legacy_matrix
    with pytest.raises(LookupError, match="Missing tank correction label"):
        builder.corrected_matrix(
            matrix,
            [("missing", "GLO", "kilogram", "missing")] + labels[1:],
            SPECIFICATION,
        )
    with pytest.raises(ValueError, match="unique"):
        builder.corrected_matrix(matrix, labels[:-1] + [labels[0]], SPECIFICATION)


@pytest.mark.parametrize(
    "package_name,prefix,size,kwargs",
    [
        ("carculator", "Car", "Medium", {}),
        ("carculator_bus", "Bus", "13m-city", {}),
        ("carculator_truck", "Truck", "40t", {"cycle": "Long haul"}),
    ],
)
@pytest.mark.parametrize("tank_type,recipe", list(zip(["hdpe", "aluminium"], RECIPES)))
def test_completed_family_tank_materials_equal_model_mass(
    package_name, prefix, size, kwargs, tank_type, recipe
):
    package = pytest.importorskip(package_name)
    from carculator_utils.array import fill_xarray_from_input_parameters

    inputs = getattr(package, prefix + "InputParameters")()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs, scope={"size": [size], "powertrain": ["FCEV"], "year": [2025]}
    )
    model = getattr(package, prefix + "Model")(
        array, energy_storage={"hydrogen": {"tank type": tank_type}}, **kwargs
    )
    model.set_all()
    inv = getattr(package, "Inventory" + prefix)(model, method="ef")
    column = inv.inputs[tuple(recipe["label"])]
    (vehicle,) = [
        index
        for label, index in inv.inputs.items()
        if label[0].startswith(f"{model.vehicle_type}, ") and label[2] == "unit"
    ]
    tank_mass = float(model["fuel tank mass"].item())
    assert -inv.A[0, column, vehicle, 0] == pytest.approx(tank_mass)
    material_rows = [
        inv.inputs[tuple(SPECIFICATION["suppliers"][key])]
        for key in recipe["materials_kg"]
    ]
    assert -inv.A[0, material_rows, column, 0].sum() * tank_mass == pytest.approx(
        tank_mass
    )
    results = inv.calculate_impacts()
    assert np.isfinite(results.values).all()
    assert float(results.sel(impact_category="climate change").sum()) > 0
