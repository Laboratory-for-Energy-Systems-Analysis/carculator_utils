"""LCIA labels must describe the numerical coefficient rows without rescaling."""

import csv
import importlib
from dataclasses import replace
from pathlib import Path

import pytest

from carculator_utils import DATA_DIR, inventory
from carculator_utils.emission_provenance import load_biosphere_extensions


def test_cached_elementary_flow_factors_use_the_same_verified_units():
    for flow in load_biosphere_extensions()["flows"]:
        for group, factors in flow["factors"].items():
            categories = inventory.get_dict_impact_categories(*group.split(":"))
            assert set(factors) == set(categories)
            for category, metadata in categories.items():
                assert factors[category]["unit"] == metadata["unit"]


@pytest.mark.parametrize(
    "group", [("recipe", "midpoint"), ("recipe", "endpoint"), ("ef", "midpoint")]
)
def test_metadata_fields_and_order_match_the_documented_schema(group):
    fields = (
        "method",
        "indicator",
        "source",
        "category",
        "type",
        "abbreviation",
        "unit",
    )
    with (DATA_DIR / "lcia/dict_impact_categories.csv").open() as handle:
        rows = [
            dict(zip(fields, row))
            for row in csv.reader(handle)
            if tuple(row[:2]) == group
        ]
    actual = inventory.get_dict_impact_categories(*group)
    assert list(actual) == [row["category"] for row in rows]
    assert list(actual.values()) == rows
    assert all(row["unit"] for row in actual.values())


def test_units_are_the_units_of_the_verified_coefficients():
    recipe = inventory.get_dict_impact_categories("recipe", "midpoint")
    assert recipe["climate change"] == {
        "method": "recipe",
        "indicator": "midpoint",
        "source": "IPCC 2021",
        "category": "climate change",
        "type": "GWP 100a",
        "abbreviation": "GWP",
        "unit": "kg CO2-Eq",
    }
    assert recipe["energy resources depletion: non-renewable"]["unit"] == "kg oil-Eq"
    assert recipe["ionising radiation"]["unit"] == "kBq Co-60-Eq"
    assert (
        inventory.get_dict_impact_categories("ef", "midpoint")[
            "ecotoxicity: freshwater, organics "
        ]["unit"]
        == "CTUe"
    )


@pytest.mark.parametrize(
    "contents, error",
    [
        ("recipe,midpoint,source,category,type,abbr\n", "seven"),
        ("recipe,midpoint,source,category,type,abbr,unit,extra\n", "seven"),
        ("recipe,midpoint,source,category,type,abbr,\n", "Missing"),
        ("recipe,midpoint,source,category,type,abbr,unit\n" * 2, "Duplicate"),
    ],
)
def test_bad_metadata_fails_before_coefficient_rows_can_be_mislabelled(
    tmp_path, monkeypatch, contents, error
):
    (tmp_path / "lcia").mkdir()
    (tmp_path / "lcia/dict_impact_categories.csv").write_text(contents)
    monkeypatch.setattr(inventory, "DATA_DIR", tmp_path)
    with pytest.raises(ValueError, match=error):
        inventory.get_dict_impact_categories("recipe", "midpoint")


def test_coefficient_build_rejects_unit_mismatch_and_accepts_only_known_synonyms(
    monkeypatch,
):
    folder = Path(__file__).parents[1] / "dev"
    if not (folder / "update_iam_b_matrices.py").is_file():
        pytest.skip("Source-only build tools")
    monkeypatch.syspath_prepend(str(folder))
    helper = importlib.import_module("update_iam_b_matrices")
    category = helper.ImpactCategory(
        "recipe",
        "midpoint",
        "ReCiPe 2016",
        "fossil resources",
        "FFP",
        "FFP",
        "kg oil-Eq",
    )
    entry = helper.MappedMethod(
        ("recipe", "midpoint"), 0, category, ("method",), "mapped"
    )
    helper.validate_method_units([entry], {("method",): {"unit": "kg oil-Eq"}})
    for unit in ("MJ", "", None):
        with pytest.raises(ValueError, match="LCIA unit mismatch"):
            helper.validate_method_units([entry], {("method",): {"unit": unit}})
    water = replace(entry, category=replace(category, unit="cubic meter"))
    helper.validate_method_units([water], {("method",): {"unit": "m3"}})
    # Scaling is not a synonym: kBq and Bq must not be silently interchanged.
    radiation = replace(entry, category=replace(category, unit="kBq Co-60-Eq"))
    with pytest.raises(ValueError, match="LCIA unit mismatch"):
        helper.validate_method_units(
            [radiation], {("method",): {"unit": "Bq Co-60-Eq"}}
        )
