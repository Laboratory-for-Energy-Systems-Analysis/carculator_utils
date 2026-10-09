import csv
import io
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from carculator_utils.export import ExportInventory


@pytest.mark.parametrize(
    "base_name,reference_product",
    [
        ("supply and refining of waste cooking oil", "vegetable oil, refined"),
        (
            "carbon fiber production, exhaust gas treatment 1",
            "carbon fiber production, exhaust gas treatment 1",
        ),
        (
            "carbon fiber production, exhaust gas treatment 2",
            "carbon fiber production, exhaust gas treatment 2",
        ),
    ],
)
def test_manufactured_products_with_waste_terms_keep_their_links(
    base_name, reference_product
):
    exporter = ExportInventory.__new__(ExportInventory)
    exporter.references = {}
    exporter.flow_map = {}
    name = f"{base_name} [for Medium - FCEV]"
    fuel = {
        "name": name,
        "location": "RER",
        "unit": "kilogram",
        "reference product": reference_product,
    }
    activity = {**fuel, "exchanges": [{**fuel, "type": "production", "amount": 1}]}
    consumer = {
        "name": "fuel supply example",
        "location": "CH",
        "unit": "kilogram",
        "reference product": "fuel",
        "exchanges": [{**fuel, "type": "technosphere", "amount": 0.5}],
    }
    rows = exporter.format_data_for_lci_for_simapro([activity, consumer], "3.10")
    product = f"{name.capitalize()} {{RER}} | Cut-off U"
    assert any(len(row) == 6 and row[0] == product for row in rows)
    assert any(len(row) == 7 and row[0] == product for row in rows)
    assert not any(len(row) == 5 and row[0] == product for row in rows)


@pytest.mark.parametrize(
    "metadata,reference,expected",
    [
        (
            {"comment": "Manufacture year: 2025. Battery capacity: 60 kWh."},
            {},
            "Manufacture year: 2025. Battery capacity: 60 kWh.",
        ),
        (
            {"comment": "Selected sample.", "source": "Vehicle-specific source"},
            {"comment": "Catalog comment.", "source": "Catalog source"},
            "Selected sample. Originally published in: Vehicle-specific source.",
        ),
        (
            {},
            {"comment": "Catalog comment.", "source": "Catalog source"},
            "Catalog comment. Originally published in: Catalog source.",
        ),
        (
            {"comment": "Selected sample."},
            {"source": "Catalog source"},
            "Selected sample. Originally published in: Catalog source.",
        ),
        (
            {"source": "Vehicle-specific source"},
            {"comment": "Catalog comment."},
            "Catalog comment. Originally published in: Vehicle-specific source.",
        ),
        (
            {"comment": None, "source": ""},
            {"comment": "Catalog comment.", "source": "Catalog source"},
            "",
        ),
        ({}, {}, ""),
    ],
    ids=[
        "vehicle",
        "activity-precedence",
        "catalog",
        "source-fallback",
        "comment-fallback",
        "explicit-empty",
        "missing",
    ],
)
def test_simapro_preserves_activity_metadata(metadata, reference, expected):
    exporter = ExportInventory.__new__(ExportInventory)
    name = "transport, car, example"
    exporter.references = {name: reference}
    exporter.flow_map = {}
    activity = {
        "name": name,
        "location": "CH",
        "unit": "kilometer",
        "reference product": "transport",
        "exchanges": [],
        **metadata,
    }
    before = deepcopy(activity)
    references_before = deepcopy(exporter.references)
    rows = exporter.format_data_for_lci_for_simapro([activity], "3.10")
    assert rows[rows.index(["Comment"]) + 1] == [expected]
    assert activity == before
    assert exporter.references == references_before


@pytest.mark.parametrize("export_format", ["file", "string"])
@pytest.mark.parametrize("has_metadata", [True, False], ids=["metadata", "empty"])
def test_simapro_metadata_survives_csv_serialization(
    export_format, has_metadata, tmp_path
):
    exporter = ExportInventory.__new__(ExportInventory)
    exporter.vm = SimpleNamespace(
        array=xr.DataArray([0], dims="year", coords={"year": [2025]})
    )
    exporter.references = {}
    exporter.flow_map = {}
    comment = '"Quoted"; manufacture year: 2025.\nConsumption: 15 kWh/100 km; 90\\%; €.'
    metadata = (
        {"comment": comment, "source": "Model-specific evidence"}
        if has_metadata
        else {}
    )
    exporter.write_lci = lambda **kwargs: [
        {
            "name": "transport, car, example",
            "location": "CH",
            "unit": "kilometer",
            "reference product": "transport",
            "exchanges": [],
            **metadata,
        }
    ]
    output = exporter.write_simapro_lci(
        "3.10", directory=tmp_path, export_format=export_format
    )
    content = (
        Path(output).read_text(encoding="utf-8") if export_format == "file" else output
    )
    rows = list(
        csv.reader(
            io.StringIO(content),
            delimiter=";",
        )
    )
    assert rows[rows.index(["Comment"]) + 1] == [
        (
            comment + " Originally published in: Model-specific evidence."
            if has_metadata
            else ""
        )
    ]


def test_simapro_export_returns_each_year_as_string():
    exporter = ExportInventory.__new__(ExportInventory)
    exporter.vm = SimpleNamespace(
        array=xr.DataArray(
            np.zeros(2),
            dims=("year",),
            coords={"year": [2020, 2030]},
        )
    )
    exporter.write_lci = lambda ecoinvent_version, year: [{"year": year}]
    exporter.format_data_for_lci_for_simapro = lambda data, ei_version: [
        ["year", data[0]["year"]]
    ]

    result = exporter.write_simapro_lci(
        ecoinvent_version="3.10", export_format="string"
    )

    assert len(result) == 2
    assert "2020" in result[0]
    assert "2030" in result[1]


def test_brightway_export_preserves_all_years(monkeypatch, tmp_path):
    import sys

    exporter = ExportInventory.__new__(ExportInventory)
    exporter.vm = SimpleNamespace(
        array=xr.DataArray([0, 0], dims="year", coords={"year": [2020, 2030]})
    )
    exporter.db_name = "example"
    exporter.write_lci = lambda **kwargs: [{"name": "example", "year": kwargs["year"]}]
    exporter.get_export_filepath = lambda name, directory: str(tmp_path / name)

    class Importer:
        def __init__(self, name):
            self.db_name = name

    monkeypatch.setitem(
        sys.modules,
        "bw2io",
        SimpleNamespace(
            importers=SimpleNamespace(base_lci=SimpleNamespace(LCIImporter=Importer))
        ),
    )
    result = exporter.write_bw2_lci(ecoinvent_version="3.10", export_format="bw2io")
    assert [item.db_name for item in result] == ["example_2020", "example_2030"]
    assert [item.data[0]["year"] for item in result] == [2020, 2030]
    exporter.vm.array = exporter.vm.array.sel(year=[2020])
    assert (
        exporter.write_bw2_lci(ecoinvent_version="3.10", export_format="bw2io").db_name
        == "example_2020"
    )


def test_brightway_missing_extra_is_actionable(monkeypatch, tmp_path):
    import sys

    import pytest

    exporter = ExportInventory.__new__(ExportInventory)
    exporter.vm = SimpleNamespace(
        array=xr.DataArray([0], dims="year", coords={"year": [2020]})
    )
    exporter.db_name = "example"
    exporter.write_lci = lambda **kwargs: []
    exporter.get_export_filepath = lambda name, directory: str(tmp_path / name)
    monkeypatch.setitem(sys.modules, "bw2io", None)
    with pytest.raises(ImportError, match=r"carculator_utils\[brightway\]"):
        exporter.write_bw2_lci(ecoinvent_version="3.10", export_format="bw2io")
