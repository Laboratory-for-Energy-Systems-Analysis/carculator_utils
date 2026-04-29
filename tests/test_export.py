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
