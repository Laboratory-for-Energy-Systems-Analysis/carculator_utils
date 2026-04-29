import pytest

from carculator_utils.inventory import check_scenario, get_dict_input


def test_get_dict_input_parses_compartment_tuples():
    inputs = get_dict_input()

    assert ("Copper ion", ("water", "ground-"), "kilogram") in inputs


@pytest.mark.parametrize(
    "scenario",
    ["SSP2-NPi", "SSP2-PkBudg1000", "SSP2-PkBudg650", "static"],
)
def test_check_scenario_accepts_current_scenarios(scenario):
    assert check_scenario(scenario) == scenario


@pytest.mark.parametrize("scenario", ["SSP2-PkBudg1150", "SSP2-PkBudg500"])
def test_check_scenario_rejects_legacy_scenarios(scenario):
    with pytest.raises(ValueError):
        check_scenario(scenario)
