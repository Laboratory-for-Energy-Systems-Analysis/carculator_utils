"""Destination matching is exact and unused supplier chains are excluded."""

from copy import deepcopy

import pytest

from carculator_utils.export_matching import (
    match_export,
    reachable_foreground,
    validate_known_target_gaps,
)


def activity(name, product, *exchanges):
    record = {
        "name": name,
        "reference product": product,
        "location": "CH",
        "unit": "kilogram",
        "database": "foreground",
        "code": name,
    }
    record["exchanges"] = [{**record, "type": "production", "amount": 1}, *exchanges]
    return record


def exchange(name="supplier", product="product"):
    return {
        "name": name,
        "reference product": product,
        "location": "CH",
        "unit": "kilogram",
        "type": "technosphere",
        "amount": 2,
    }


def test_reachability_retains_supply_loops_but_excludes_unrelated_fuels():
    root = activity(
        "transport, car, BEV, Medium", "travel", exchange("battery", "battery")
    )
    battery = activity("battery", "battery", exchange("recycling", "recycling"))
    recycling = activity("recycling", "recycling", exchange("battery", "battery"))
    unused = activity("unused coal fuel", "fuel", exchange())
    data = [root, battery, recycling, unused]
    before = deepcopy(data)
    assert reachable_foreground(data, "car") == [root, battery, recycling]
    assert data == before


def test_exact_match_does_not_mutate_and_rejects_ambiguity():
    data = [activity("consumer", "product", exchange())]
    key = ("supplier", "product", "CH", "kilogram")
    before = deepcopy(data)
    linked, missing = match_export(data, {key: [("ecoinvent-3.10", "abc")]}, {})
    assert not missing
    assert linked[0]["exchanges"][1]["input"] == ("ecoinvent-3.10", "abc")
    assert data == before
    with pytest.raises(ValueError, match="ambiguous"):
        match_export(data, {key: [("a", "b"), ("a", "c")]}, {})
    result, missing = match_export(data, {}, {}, strict=False)
    assert len(missing) == 1
    assert "input" not in result[0]["exchanges"][1]


def test_unavailable_coal_route_is_not_silently_substituted_for_39():
    coal = exchange("methanol production, coal gasification", "methanol")
    coal["location"] = "RoW"
    data = [activity("fuel", "fuel", coal)]
    with pytest.raises(ValueError, match="No verified ecoinvent 3.9"):
        validate_known_target_gaps(data, "3.9")
    validate_known_target_gaps(data, "3.10")
