"""Versioned supplier mapping preserves the exported physical demand."""

from copy import deepcopy

import pytest

from carculator_utils.export_matching import map_legacy_exchanges, migrate_background


def fixture():
    supplier = dict(name="old", location="GLO", unit="kg", **{"reference product": "p"})
    data = [
        dict(
            name="foreground",
            location="GLO",
            unit="kg",
            **{
                "reference product": "p",
                "exchanges": [dict(supplier, type="technosphere", amount=-4)],
            },
        )
    ]
    mapping = dict(
        ecoinvent_version="3.12",
        activities=[
            dict(
                label=["old", "GLO", "kg", "p"],
                targets=[
                    [["new", "CN", "kg", "p"], 0.25],
                    [["new", "RoW", "kg", "p"], 0.75],
                ],
            )
        ],
    )
    return data, mapping


def test_disaggregated_signed_demand_and_caller_preservation():
    data, mapping = fixture()
    before = deepcopy(data)
    exchanges = migrate_background(data, mapping, "3.12")[0]["exchanges"]
    assert [(x["location"], x["amount"]) for x in exchanges] == [
        ("CN", -1),
        ("RoW", -3),
    ]
    assert all(x["name"] == "new" for x in exchanges)
    assert data == before


def test_foreground_supplier_is_never_migrated():
    data, mapping = fixture()
    data.append(dict(data[0]["exchanges"][0], exchanges=[]))
    assert migrate_background(data, mapping, "3.12") == data


def test_unverified_older_suppliers_fail_explicitly():
    data, mapping = fixture()
    with pytest.raises(ValueError, match="No verified ecoinvent 3.10"):
        migrate_background(data, mapping, "3.10")
    mapping["activities"][0]["available_in_3.10"] = True
    assert migrate_background(data, mapping, "3.10") == data
    # Presence in 3.10 must never imply presence in 3.9.
    with pytest.raises(ValueError, match="No verified ecoinvent 3.9"):
        migrate_background(data, mapping, "3.9")


@pytest.mark.parametrize("weights", [(0.5, 0.6), (-1, 2), (float("nan"), 0)])
def test_invalid_weights_are_rejected(weights):
    data, mapping = fixture()
    for target, weight in zip(mapping["activities"][0]["targets"], weights):
        target[1] = weight
    with pytest.raises(ValueError, match="Invalid supplier migration"):
        migrate_background(data, mapping, "3.12")


def test_legacy_names_change_only_external_links():
    data, _ = fixture()
    production = {k: v for k, v in data[0].items() if k != "exchanges"}
    data[0]["exchanges"].append(dict(production, type="production", amount=-1))
    mapping = {
        ("old", "GLO", "", "kg", "p"): ("legacy", "RER", "", "kg", "p"),
        ("foreground", "GLO", "", "kg", "p"): ("wrong", "RER", "", "kg", "p"),
    }
    before = deepcopy(data)
    result = map_legacy_exchanges(data, mapping)
    assert result[0]["exchanges"][0]["name"] == "legacy"
    assert result[0]["exchanges"][0]["amount"] == -4
    assert result[0]["exchanges"][1]["name"] == "foreground"
    assert result[0]["exchanges"][1]["type"] == "production"
    assert data == before
