"""PV generation coefficients, geographic selection and export boundaries."""

import json
from copy import deepcopy

import numpy as np
import pytest
from scipy import sparse

from carculator_utils import DATA_DIR
from carculator_utils.electricity import ElectricityDataWarning
from carculator_utils.export_matching import migrate_background
from carculator_utils.inventory import get_dict_input
from carculator_utils.photovoltaic import select_photovoltaic


@pytest.fixture
def config():
    return json.loads((DATA_DIR / "IAM/photovoltaic.json").read_text())


def pv_key(config, country):
    return (
        config["activity_name"],
        country,
        "kilowatt hour",
        config["reference_product"],
    )


@pytest.mark.parametrize(
    "country,expected",
    [("CH", "CH"), ("UK", "GB"), ("NM", "NA"), ("EU27", "EU27"), ("GLO", "GLO")],
)
def test_country_selection_preserves_inputs(config, country, expected):
    inputs = get_dict_input()
    before = inputs.copy()
    configuration = {}
    key, provenance = select_photovoltaic(country, configuration, inputs)
    assert key == pv_key(config, expected)
    assert provenance["solar_location"] == expected
    assert inputs == before
    assert configuration == {}


def test_energy_geography_override_and_unknown_country(config):
    inputs = get_dict_input()
    assert select_photovoltaic("GLO", {"solar photovoltaic country": "CN"}, inputs)[
        0
    ] == pv_key(config, "CN")
    with pytest.warns(ElectricityDataWarning, match="GLO proxy"):
        assert select_photovoltaic("unavailable", {}, inputs)[0] == pv_key(
            config, "GLO"
        )
    with pytest.raises(ValueError, match="Unsupported"):
        select_photovoltaic("CH", {"solar photovoltaic country": "unavailable"}, inputs)
    with pytest.raises(ValueError, match="iea-pvps-2026"):
        select_photovoltaic("CH", {"solar photovoltaic": "unknown"}, inputs)


def test_legacy_proxy_remains_explicitly_available(config):
    key, _ = select_photovoltaic(
        "GLO", {"solar photovoltaic": "legacy"}, get_dict_input()
    )
    assert key == tuple(config["legacy_label"])


def test_pv_are_background_coefficients_not_expanded_inventories(config):
    inputs = get_dict_input()
    countries = config["countries"] + list(config["aggregate_members"])
    assert len(config["countries"]) == len(set(config["countries"])) == 250
    columns = [inputs[pv_key(config, country)] for country in countries]
    matrix = sparse.load_npz(DATA_DIR / "IAM/A_matrix.npz").tocsc()
    for column in columns:
        assert matrix[:, column].nnz == 1
        assert matrix[column, column] == 1
    for path in (DATA_DIR / "IAM").glob("B_matrix_*.npz"):
        factors = sparse.load_npz(path)[:, columns]
        assert np.isfinite(factors.data).all()
        assert np.all(np.asarray(abs(factors).sum(axis=0)).ravel() > 0)


def test_aggregates_use_generation_weighted_country_coefficients(config):
    inputs = get_dict_input()
    for path in (DATA_DIR / "IAM").glob("B_matrix_*.npz"):
        factors = sparse.load_npz(path).toarray()
        for region, members in config["aggregate_members"].items():
            weights = np.array([config["generation_gwh"].get(c, 0) for c in members])
            weights /= weights.sum()
            columns = [inputs[pv_key(config, c)] for c in members]
            expected = factors[:, columns] @ weights
            np.testing.assert_allclose(
                factors[:, inputs[pv_key(config, region)]],
                expected,
                rtol=1e-12,
                atol=1e-12,
            )


def test_exports_reference_the_same_premise_country_suppliers(config):
    mapping = json.loads((DATA_DIR / "IAM/background_mapping.json").read_text())
    keys = ("name", "location", "unit", "reference product")
    data = [
        {
            "name": "test electricity supply",
            "location": "GLO",
            "unit": "kilowatt hour",
            "reference product": "electricity",
            "exchanges": [
                dict(zip(keys, pv_key(config, "EU27")), type="technosphere", amount=1.1)
            ],
        }
    ]
    original = deepcopy(data)
    result = migrate_background(data, mapping, "3.12")[0]["exchanges"]
    assert sum(e["amount"] for e in result) == pytest.approx(1.1)
    volumes = config["generation_gwh"]
    total = sum(volumes.get(c, 0) for c in config["aggregate_members"]["EU27"])
    for exchange in result:
        assert exchange["name"] == config["activity_name"]
        assert exchange["reference product"] == config["reference_product"]
        assert exchange["amount"] == pytest.approx(
            1.1 * volumes[exchange["location"]] / total
        )
    assert data == original
    with pytest.raises(ValueError, match="No verified ecoinvent 3.10"):
        migrate_background(data, mapping, "3.10")
