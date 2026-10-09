"""Independent generation balances, source snapshots and inventory integration."""

import hashlib
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from carculator_utils import DATA_DIR
from carculator_utils.electricity import (
    DEFAULT_SCENARIO,
    SCENARIOS,
    ElectricityDataWarning,
    electricity_source_metadata,
    get_electricity_mix,
    select_electricity_mix,
    validate_shares,
)


@pytest.fixture(scope="module")
def builder():
    path = Path(__file__).resolve().parents[1] / "scripts" / "refresh_electricity.py"
    spec = importlib.util.spec_from_file_location("refresh_electricity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def shares():
    return pd.DataFrame(
        {"country": ["NA"], "year": [2025], "coal": [0.25], "wind": [0.75]}
    )


@pytest.mark.parametrize(
    "values", [[-0.1, 1.1], [np.nan, 1], [np.inf, 0], [0, 0], [0.2, 0.3]]
)
def test_invalid_shares_are_rejected_without_repair(values):
    data = shares()
    data[["coal", "wind"]] = [values]
    with pytest.raises(ValueError, match="Invalid electricity shares.*NA.*2025"):
        validate_shares(data, ["country", "year"], ["coal", "wind"])


def test_duplicate_and_unknown_technology_records_fail():
    with pytest.raises(ValueError, match="Duplicate"):
        validate_shares(
            pd.concat([shares(), shares()]), ["country", "year"], ["coal", "wind"]
        )
    with pytest.raises(ValueError, match="columns differ"):
        validate_shares(
            shares().assign(unmapped=0.1), ["country", "year"], ["coal", "wind"]
        )


def test_rounding_only_normalization_preserves_input():
    data = shares()
    data.loc[0, "wind"] += 1e-9
    before = data.copy(deep=True)
    result = validate_shares(data, ["country", "year"], ["coal", "wind"])
    assert result[["coal", "wind"]].sum(axis=1).item() == pytest.approx(1)
    pd.testing.assert_frame_equal(data, before)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_bundled_scenarios_are_finite_and_normalized(scenario):
    mix = get_electricity_mix(scenario)
    assert mix.dims == ("country", "year", "variable")
    assert np.isfinite(mix).all()
    assert (mix >= 0).all()
    np.testing.assert_allclose(mix.sum("variable"), 1, atol=1e-12)


def test_snapshot_matches_observations_and_preserves_namibia_code():
    mix = get_electricity_mix()
    # Independently published annual shares, rounded in Ember's share column.
    for country, technology, share in [
        ("US", "Gas", 42.59),
        ("CN", "Nuclear", 4.5),
        ("PL", "Solar", 10.26),
    ]:
        assert mix.sel(
            country=country, year=2024, variable=technology
        ).item() * 100 == pytest.approx(share, abs=0.01)
    assert mix.sel(country="DE", year=2024, variable="Nuclear").item() == 0
    assert "NA" in mix.country and "NM" not in mix.country
    for country in ["SZ", "UG", "ZM"]:
        assert (
            mix.sel(country=country, year=2020, variable="Wind, offshore").item() == 0
        )
    assert {"ID", "KR", "MX", "NZ", "TR"}.issubset(mix.country.values)


def test_history_is_shared_but_future_scenarios_differ_and_caches_are_private():
    reference = get_electricity_mix()
    mitigation = get_electricity_mix("geco-2025-1.5c")
    xr.testing.assert_equal(reference.sel(year=2024), mitigation.sel(year=2024))
    assert not np.allclose(
        reference.sel(country="US", year=2050), mitigation.sel(country="US", year=2050)
    )
    reference[:] = 0
    assert get_electricity_mix().sel(
        country="US", year=2024
    ).sum().item() == pytest.approx(1)


def test_unknown_scenario_and_geography_are_not_silent_european_defaults():
    with pytest.raises(ValueError, match="Electricity scenario"):
        get_electricity_mix("SSP2-NPi")
    mix = get_electricity_mix()
    with pytest.raises(ValueError, match="explicit.*electricity fallback country"):
        select_electricity_mix(mix, "ZZ")
    with pytest.warns(ElectricityDataWarning, match="uses GLO"):
        selected, provenance = select_electricity_mix(mix, "ZZ", fallback="GLO")
    assert selected.country.item() == "GLO"
    assert provenance["requested_country"] == "ZZ"


def test_regional_projection_provenance_is_visible():
    with pytest.warns(
        ElectricityDataWarning, match="European Union.*not a national forecast"
    ):
        _, provenance = select_electricity_mix(get_electricity_mix(), "DE")
    assert provenance["projection_region"] == "European Union"
    assert provenance["projection_kind"] == "regional-proxy"
    _, provenance = select_electricity_mix(get_electricity_mix(), "CH")
    assert provenance["projection_kind"] == "country"
    assert provenance["projection_region"] == "Switzerland"


def test_legacy_retains_original_data_and_horizon_convention():
    mix = get_electricity_mix("legacy")
    assert mix.attrs["horizon_policy"] == "truncate"
    assert mix.sel(country="US", year=2025, variable="Gas").item() == pytest.approx(
        0.16
    )
    assert (
        hashlib.sha256(
            (DATA_DIR / "electricity" / "electricity_mixes.csv").read_bytes()
        ).hexdigest()
        == "b6939fda4b4971565a0dcdd43471079dcc427e0c82129ee46c34d8f1ef27789d"
    )


def test_resource_hashes_and_explicit_source_exclusions():
    metadata = electricity_source_metadata()
    for filename, digest in metadata["resources"].items():
        assert (
            hashlib.sha256(
                (DATA_DIR / "electricity" / filename).read_bytes()
            ).hexdigest()
            == digest
        )
    assert all(s["license"] == "CC BY 4.0" for s in metadata["sources"].values())
    excluded = metadata["excluded_history"]
    assert any(r["country"] == "ES" and r["year"] == 2025 for r in excluded)
    mix = get_electricity_mix()
    assert mix.sel(country="ES").history_last_year.item() == 2024


def ember_fixture(tmp_path):
    path = tmp_path / "ember.csv"
    pd.DataFrame(
        [
            {
                "Area": "Namibia",
                "ISO 3 code": "NAM",
                "Year": 2024,
                "Area type": "Country or economy",
                "Electricity source": technology,
                "Generation (TWh)": amount,
                "Ember region": "Africa",
            }
            for technology, amount in [
                ("Hydro", 6),
                ("Solar", 2),
                ("Coal", 2),
                ("Total generation", 10),
                ("Renewables", 8),
            ]
        ]
    ).to_csv(path, index=False)
    return path


def test_ember_import_uses_generation_and_excludes_aggregate_double_counting(
    builder, tmp_path
):
    history, _, exclusions = builder.read_ember(ember_fixture(tmp_path))
    assert history.country.tolist() == ["NA"]
    assert history.Hydro.item() == pytest.approx(0.6)
    assert history.Solar.item() == pytest.approx(0.2)
    assert history.Coal.item() == pytest.approx(0.2)
    assert not exclusions


def test_ember_missing_components_must_reconcile_and_negatives_require_explicit_exclusion(
    builder, tmp_path
):
    path = ember_fixture(tmp_path)
    data = pd.read_csv(path)
    data.loc[data["Electricity source"] == "Coal", "Generation (TWh)"] = 0
    data.to_csv(path, index=False)
    with pytest.raises(ValueError, match="Generation balance"):
        builder.read_ember(path)
    data.loc[data["Electricity source"] == "Coal", "Generation (TWh)"] = -1
    data.to_csv(path, index=False)
    with pytest.raises(ValueError, match="Negative Ember"):
        builder.read_ember(path)


def geco_fixture(other=10):
    # Total 100: coal 30 (including 5 CCS), gas 20 (including 2 CCS),
    # biomass 10 (including 3 CCS), nuclear 10, hydro 10, wind 10, Other 10.
    entries = [
        ("Gross Elec. Generation (TWhe)", 100),
        ("Coal", 30),
        ("of which CCS", 5),
        ("Oil", 0),
        ("Gas", 20),
        ("of which CCS", 2),
        ("Biomass & Waste", 10),
        ("of which CCS", 3),
        ("Nuclear", 10),
        ("Hydro", 10),
        ("Wind", 10),
        ("Solar", 0),
        ("Other", other),
        ("Share of Renewables (%)", 0.4),
    ]
    return pd.DataFrame(
        [
            ["Example", 2023, 2030, 2035, 2040, 2050, 2060, 2070],
            *[[label, *([value] * 7)] for label, value in entries],
        ]
    )


def test_geco_ccs_subgroups_do_not_double_count(builder):
    rows = builder.read_geco_sheet(geco_fixture(), DEFAULT_SCENARIO, "Example")
    assert len(rows) == 6
    row = rows[0]
    assert row["Coal"] == pytest.approx(0.25)
    assert row["Coal CCS"] == pytest.approx(0.05)
    assert row["Gas"] == pytest.approx(0.18)
    assert row["Gas CCS"] == pytest.approx(0.02)
    assert row["Biomass"] == pytest.approx(0.07)
    assert row["Biomass CCS"] == pytest.approx(0.03)


def test_geco_other_reconciliation_is_explicit_and_audited(builder):
    with pytest.raises(ValueError, match="Generation balance"):
        builder.read_geco_sheet(geco_fixture(other=15), DEFAULT_SCENARIO, "Example")
    audit = []
    rows = builder.read_geco_sheet(
        geco_fixture(other=15),
        DEFAULT_SCENARIO,
        "Example",
        other_residual=True,
        audit=audit,
    )
    assert rows[0]["Geothermal"] == pytest.approx(0.1)
    assert audit[0]["other_surplus_twh"] == 5
    assert audit[0]["reported_total_twh"] == 100


def test_tyndp_keeps_storage_and_unknown_generation_out_of_runtime_mixes():
    audit = pd.read_csv(
        DATA_DIR / "electricity" / "tyndp_2026_mapping_audit.csv", sep=";"
    )
    assert set(audit.loc[audit.technology == "Hydrogen GT", "status"]) <= {
        "unresolved LCI mapping",
        "not reported",
    }
    assert set(audit.loc[audit.technology == "PS Turbine", "status"]) <= {
        "storage output",
        "not reported",
    }
    assert not any("tyndp" in s for s in SCENARIOS)


@pytest.mark.family
@pytest.mark.parametrize(
    "name,prefix,size,powertrain,kwargs",
    [
        ("carculator", "Car", "Medium", "BEV", {}),
        ("carculator_bus", "Bus", "13m-city", "BEV-depot", {}),
        ("carculator_truck", "Truck", "40t", "BEV", {"cycle": "Regional delivery"}),
        ("carculator_two_wheeler", "TwoWheeler", "Motorcycle 11-35kW", "BEV", {}),
    ],
)
def test_completed_family_scenarios_preserve_energy_and_change_electricity(
    name, prefix, size, powertrain, kwargs
):
    module = pytest.importorskip(name)
    inputs = getattr(module, prefix + "InputParameters")()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs, scope={"size": [size], "powertrain": [powertrain], "year": [2030]}
    )
    model = getattr(module, prefix + "Model")(array, country="US", **kwargs)
    model.set_all()
    original = model.array.copy(deep=True)
    inventory_type = getattr(module, "Inventory" + prefix)
    baseline = inventory_type(model, scenario="static")
    config = {"electricity scenario": "geco-2025-1.5c"}
    mitigation = inventory_type(
        model, scenario="static", background_configuration=config
    )
    assert config == {"electricity scenario": "geco-2025-1.5c"}
    xr.testing.assert_identical(model.array, original)
    assert not np.allclose(baseline.electricity_mix, mitigation.electricity_mix)
    a, b = baseline.calculate_impacts(), mitigation.calculate_impacts()
    assert np.isfinite(a).all() and np.isfinite(b).all()
    assert not np.allclose(
        a.sel(impact_category="climate change"), b.sel(impact_category="climate change")
    )


@pytest.mark.family
@pytest.mark.export
def test_scenario_provenance_survives_brightway_and_simapro_export():
    module = pytest.importorskip("carculator")
    pytest.importorskip("bw2io")
    inputs = module.CarInputParameters()
    inputs.static()
    _, array = module.fill_xarray_from_input_parameters(
        inputs, scope={"size": ["Medium"], "powertrain": ["BEV"], "year": [2030]}
    )
    model = module.CarModel(array, country="US")
    model.set_all()
    inventory = module.InventoryCar(model, scenario="static")
    original = inventory.A.copy()
    impacts = inventory.calculate_impacts()
    importer = inventory.export_lci(software="brightway2", format="bw2io")
    supplies = [
        r for r in importer.data if r["name"].startswith("electricity supply for")
    ]
    assert supplies
    assert all(DEFAULT_SCENARIO in r["comment"] for r in supplies)
    assert all("loss_multiplier" in r["comment"] for r in supplies)
    content = inventory.export_lci(software="simapro", format="string")
    assert DEFAULT_SCENARIO in content
    np.testing.assert_array_equal(inventory.A, original)
    xr.testing.assert_identical(inventory.calculate_impacts(), impacts)
