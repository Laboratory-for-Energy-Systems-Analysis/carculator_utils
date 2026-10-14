"""Regression tests for the development adapters' metadata and Excel boundary."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest


def load(name):
    path = Path(__file__).resolve().parents[1] / "dev" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_writer_preserves_sources_structured_metadata_and_uncertainty(tmp_path):
    pytest.importorskip("openpyxl")
    bw = pytest.importorskip("bw2io")
    writer = load("premise_vehicle_excel")
    ds = {
        "name": "truck production",
        "reference product": "truck",
        "unit": "unit",
        "location": "RER",
        "comment": "Original comment",
        "source": "Component paper",
        "model": "carculator_truck",
        "vehicle inventory provenance": {"baseline year": 2020},
        "database": "incorrect old header",
        "row": 123,
        "exchanges": [
            dict(
                name="truck production",
                **{"reference product": "truck"},
                unit="unit",
                location="RER",
                type="production",
                amount=2,
            ),
            dict(
                name="Carbon dioxide, fossil",
                unit="kilogram",
                type="biosphere",
                categories=("air", "urban air close to ground"),
                amount=1.2,
                **{"uncertainty type": 3, "loc": 1.2, "scale": 0.1},
            ),
        ],
        "production amount": 2,
    }
    before = deepcopy(ds)
    path = tmp_path / "wrong-filename.xlsx"
    writer.write_workbook(path, [ds], database_name="lci-trucks")
    importer = bw.ExcelImporter(str(path))
    actual = importer.data[0]
    assert importer.db_name == actual["database"] == "lci-trucks"
    assert actual["source"] == "Component paper"
    assert json.loads(actual["vehicle inventory provenance"])["baseline year"] == 2020
    assert actual["production amount"] == 2
    assert actual["exchanges"][1]["scale"] == 0.1
    assert ds == before
    writer.write_workbook(tmp_path / "lci-truck-legacy-components.xlsx", [ds])
    assert (
        bw.ExcelImporter(str(tmp_path / "lci-truck-legacy-components.xlsx")).db_name
        == "lci-truck-legacy-components"
    )


def test_component_source_is_not_replaced_by_vehicle_publication():
    module = load("premise_vehicle_provenance")
    ds = dict(
        name="fuel cell stack",
        **{"reference product": "stack"},
        unit="unit",
        location="RER",
        source="Original stack study",
        comment="Recipe description",
        exchanges=[],
    )
    generation = {
        "libraries": {
            "carculator": {"version": "1.9.7"},
            "carculator_utils": {"version": "1.3.7"},
        }
    }
    module.attach_provenance([ds], "car", generation, [])
    assert ds["source"] == "Original stack study"
    assert ds[module.KEY]["role"] == "bundled component"
    assert "baseline vehicle parameters" not in ds[module.KEY]
    assert "not the component recipe" in ds["comment"]
    assert "10.1016/j.rser.2022.112475" in ds["model publication"]


def test_phev_pack_calibration_retains_sources_and_proxy_boundary():
    module = load("premise_vehicle_provenance")
    ds = dict(name="PHEV service", unit="kilometer", location="RER", exchanges=[])
    pack = {
        "capacity kWh": 12,
        "pack mass kg": 118.5,
        "capacity source": "Manufacturer capacity reference",
        "mass source": "Manufacturer mass reference",
        "boundary": "Pack mass excludes retaining brackets.",
    }
    generation = {
        "libraries": {
            "carculator": {"version": "1.9.7"},
            "carculator_utils": {"version": "1.3.7"},
        },
        "PHEV battery calibration": {"sizes": {"Medium": pack}},
    }
    parameters = [
        dict(name=ds["name"], size="Medium", powertrain="PHEV-p", proxy=False)
    ]
    module.attach_provenance([ds], "car", generation, parameters)
    assert ds[module.KEY]["PHEV battery calibration"] == pack
    assert pack["capacity source"] in ds["comment"]
    assert pack["mass source"] in ds["comment"]
    assert pack["boundary"] in ds["comment"]
    assert "same physical pack" in ds["comment"]
    assert "MIX capacity market" in ds["comment"]
    assert "relative chemistry-density trend" in ds["comment"]


def test_legacy_metadata_does_not_claim_current_model_generation():
    module = load("premise_vehicle_provenance")
    ds = dict(
        name="legacy tank",
        **{"reference product": "tank"},
        unit="unit",
        location="RER",
        exchanges=[],
    )
    source = dict(ds, source="Inherited tank study", description="Original description")
    module.attach_legacy_provenance([ds], {module.identity(ds): source}, "a" * 64)
    assert ds["source"] == "Inherited tank study"
    assert ds["description"] == "Original description"
    assert ds["inventory provenance"]["source database version"] == "3.7"
    assert "model" not in ds and module.KEY not in ds
    assert "not regenerated" in ds["comment"]


def test_shared_cng_production_remains_native_while_lpg_service_is_a_proxy():
    module = load("premise_vehicle_provenance")
    production = dict(
        name="lorry production, compressed gas",
        **{"reference product": "truck"},
        unit="unit",
        location="RER",
        exchanges=[],
    )
    services = [
        dict(
            name=n,
            **{"reference product": "transport"},
            unit="ton kilometer",
            location="RER",
            exchanges=[dict(production, type="technosphere", amount=1)],
        )
        for n in ("LPG service", "CNG service")
    ]
    pars = [
        dict(
            name=n,
            size="40t",
            powertrain="ICEV-g",
            proxy=i == 0,
            **{"kilometers per year": 78000},
        )
        for i, n in enumerate(("LPG service", "CNG service"))
    ]
    generation = {
        "libraries": {
            "carculator_truck": {"version": "0.5.2"},
            "carculator_utils": {"version": "1.3.7"},
        }
    }
    before = deepcopy([d["exchanges"] for d in services + [production]])
    module.attach_provenance(services + [production], "truck", generation, pars)
    assert services[0][module.KEY]["proxy"]
    assert not services[1][module.KEY]["proxy"]
    assert not production[module.KEY]["proxy"]
    assert production[module.KEY]["service templates"] == ["LPG service", "CNG service"]
    assert [d["exchanges"] for d in services + [production]] == before


@pytest.mark.parametrize(
    "family,model", [("car", "carculator"), ("truck", "carculator_truck")]
)
def test_fcev_metadata_distinguishes_power_requirement_from_validation(family, model):
    module = load("premise_vehicle_provenance")
    ds = dict(
        name="FCEV service",
        unit="kilometer",
        location="RER",
        exchanges=[],
        **{"reference product": "transport"},
    )
    parameters = [
        dict(
            name=ds["name"],
            size="Medium",
            powertrain="FCEV",
            proxy=False,
            **{
                "battery power": 50,
                "fuel cell power": 165,
                "fuel cell own consumption": 1.1,
            },
        )
    ]
    generation = {
        "libraries": {
            model: {"version": "test"},
            "carculator_utils": {"version": "test"},
        }
    }
    module.attach_provenance([ds], family, generation, parameters)
    baseline = ds[module.KEY]["baseline vehicle parameters"]
    assert baseline["battery power"] + baseline["fuel cell power"] / baseline[
        "fuel cell own consumption"
    ] == pytest.approx(200)
    assert "complement of net fuel-cell power" in ds["comment"]
    assert "does not independently validate" in ds["comment"]
    assert ("peak-power capability remains unverified" in ds["comment"]) == (
        family == "truck"
    )


@pytest.mark.parametrize("powertrain", ["HEV-p", "HEV-d", "PHEV-p", "PHEV-d"])
def test_hybrid_metadata_discloses_engine_ageing_proxy_and_mode_weighting(powertrain):
    module = load("premise_vehicle_provenance")
    ds = dict(
        name="hybrid service",
        unit="kilometer",
        location="RER",
        exchanges=[],
        **{"reference product": "transport"},
    )
    parameters = [
        dict(name=ds["name"], size="Medium", powertrain=powertrain, proxy=False)
    ]
    generation = {
        "libraries": {
            "carculator": {"version": "test"},
            "carculator_utils": {"version": "test"},
        }
    }
    module.attach_provenance([ds], "car", generation, parameters)
    assert "uncalibrated hybrid ageing proxy" in ds["comment"]
    assert "vehicle lifetime kilometres" in ds["comment"]
    assert "weighted once" in ds["comment"]
    assert "not multiplied by hot-exhaust deterioration" in ds["comment"]
