from types import SimpleNamespace

import numpy as np
import xarray as xr

from carculator_utils.export import ExportInventory


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
