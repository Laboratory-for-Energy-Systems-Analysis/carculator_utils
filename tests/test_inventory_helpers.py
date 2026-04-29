from carculator_utils.inventory import get_dict_input


def test_get_dict_input_parses_compartment_tuples():
    inputs = get_dict_input()

    assert ("Copper ion", ("water", "ground-"), "kilogram") in inputs
