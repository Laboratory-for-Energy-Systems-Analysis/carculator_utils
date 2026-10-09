"""Scientific contracts for the offline A/B build helpers (no licensed data)."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.sparse.linalg import spsolve

SCRIPT = Path(__file__).parents[1] / "dev/iam_matrix_tools.py"
pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="Source-only build tools")


@pytest.fixture
def helpers():
    spec = importlib.util.spec_from_file_location("iam_matrix_tools", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def activity(name, location="GLO", unit="kilogram"):
    return name, location, unit, name


def metadata(label, **extra):
    return dict(zip(("name", "location", "unit", "reference product"), label), **extra)


def test_signed_nonunit_production_and_duplicate_inputs(helpers):
    """Two kg output need 3 kg material and emit 4 kg CO2; waste provides credit."""
    material, product, waste = map(activity, ("material", "product", "waste"))
    co2 = ("Carbon dioxide, fossil", ("air",), "kilogram")
    labels = [material, product, waste, co2]
    matrix = helpers.assemble_matrix(
        labels,
        {
            1: [
                (product, "production", 2),
                (material, "technosphere", 1),
                (material, "technosphere", 2),
                (co2, "biosphere", 4),
            ],
            2: [(waste, "production", -1), (material, "technosphere", 0.5)],
        },
    )
    np.testing.assert_allclose(spsolve(matrix, [0, 1, 0, 0]), [1.5, 0.5, 0, 2])
    np.testing.assert_allclose(spsolve(matrix, [0, 0, -1, 0]), [0.5, 0, 1, 0])
    # Material LCIA=10; direct CO2 CF=1; foreground B is zero.
    assert np.array([10, 0, 0, 1]) @ spsolve(matrix, [0, 1, 0, 0]) == 17


@pytest.mark.parametrize(
    "recipe, error",
    [
        ([(activity("unknown"), "technosphere", 1)], LookupError),
        ([(activity("a"), "production", float("nan"))], ValueError),
        ([(activity("a"), "production", 0)], ValueError),
        ([(activity("a"), "magic", 1)], ValueError),
        ([(activity("b"), "production", 1)], ValueError),
    ],
)
def test_invalid_recipe_fails_without_row_zero_fallback(helpers, recipe, error):
    with pytest.raises(error):
        helpers.assemble_matrix([activity("a"), activity("b")], {0: recipe})


def test_substitution_and_negative_consumption_keep_signs(helpers):
    a, b = activity("a"), activity("b")
    matrix = helpers.assemble_matrix(
        [a, b],
        {
            1: [
                (b, "production", 1),
                (a, "substitution", 2),
                (a, "technosphere", -3),
            ]
        },
    )
    assert matrix[0, 1] == 5


def test_migration_composes_disaggregation_without_losing_mass(helpers, tmp_path):
    a, b, c, d = map(activity, "abcd")
    first = tmp_path / "first.json"
    first.write_text(
        json.dumps(
            {
                "disaggregate": [
                    {
                        "source": metadata(a),
                        "targets": [
                            metadata(b, allocation=0.25),
                            metadata(c, allocation=0.75),
                        ],
                    }
                ]
            }
        )
    )
    second = tmp_path / "second.json"
    second.write_text(
        json.dumps({"replace": [{"source": metadata(b), "target": metadata(d)}]})
    )
    result, provenance = helpers.resolve_activity(
        a, {c: [object()], d: [object()]}, helpers.load_migrations([first, second])
    )
    assert dict(result) == {d: 0.25, c: 0.75}
    assert provenance == ["first.json", "second.json"]


@pytest.mark.parametrize("weight", [-0.1, 0.9, float("inf")])
def test_migration_rejects_invalid_weights(helpers, tmp_path, weight):
    path = tmp_path / "migration.json"
    path.write_text(
        json.dumps(
            {
                "disaggregate": [
                    {
                        "source": metadata(activity("a")),
                        "targets": [metadata(activity("b"), allocation=weight)],
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError):
        helpers.load_migrations([path])


def test_conflicting_official_rules_require_attributed_override(helpers, tmp_path):
    a, b, c = map(activity, "abc")
    path = tmp_path / "migration.json"
    path.write_text(
        json.dumps(
            {
                "replace": [
                    {"source": metadata(a), "target": metadata(b)},
                    {"source": metadata(a), "target": metadata(c)},
                ]
            }
        )
    )
    chain = helpers.load_migrations([path])
    with pytest.raises(LookupError, match="Conflicting"):
        helpers.resolve_activity(a, {b: [1], c: [2]}, chain)
    override = {
        a: {
            "targets": [{"label": b, "weight": 1}],
            "reason": "Same source product UUID",
            "source": "source metadata",
        }
    }
    assert helpers.resolve_activity(a, {b: [1], c: [2]}, chain, override)[0] == [(b, 1)]
    del override[a]["reason"]
    with pytest.raises(ValueError, match="reason and source"):
        helpers.resolve_activity(a, {b: [1]}, chain, override)


@pytest.mark.parametrize("index", [{}, {activity("a"): [1, 2]}])
def test_missing_and_duplicate_suppliers_are_errors(helpers, index):
    with pytest.raises(LookupError):
        helpers.resolve_activity(activity("a"), index, [])


def test_label_roundtrip_preserves_compartments_and_order(helpers, tmp_path):
    labels = [activity("semi;colon"), ("CO2", ("air", "urban"), "kilogram")]
    path = tmp_path / "index.csv"
    helpers.save_labels(path, labels)
    assert helpers.load_labels(path) == labels
    with pytest.raises(ValueError, match="unique"):
        helpers.save_labels(path, labels + labels)
