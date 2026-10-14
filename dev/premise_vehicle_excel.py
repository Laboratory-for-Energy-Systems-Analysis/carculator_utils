"""Write vehicle inventories without discarding source or structured metadata."""

import json
from pathlib import Path

import openpyxl


def cell(value):
    return (
        json.dumps(value, ensure_ascii=False)
        if isinstance(value, (dict, list, tuple))
        else value
    )


def write_workbook(path, datasets, *, database_name=None):
    database_name = Path(path).stem if database_name is None else database_name
    if not isinstance(database_name, str) or not database_name.strip():
        raise ValueError("A nonempty workbook database name is required")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "test"
    sheet.append(["Database", database_name])
    sheet.append([])
    internal = {"row", "sheet", "workbook", "database", "code", "input", "family"}
    for ds in datasets:
        sheet.append(["Activity", ds["name"]])
        fields = list(
            dict.fromkeys(
                [
                    "name",
                    "amount",
                    "location",
                    "unit",
                    "categories",
                    "type",
                    "reference product",
                    "comment",
                    *(k for exc in ds["exchanges"] for k in exc if k not in internal),
                ]
            )
        )
        for key, value in ds.items():
            if key not in internal | {"name", "exchanges"} and value is not None:
                sheet.append([key, cell(value)])
        for key, default in (("production amount", 1), ("type", "process")):
            if key not in ds:
                sheet.append([key, default])
        sheet.append(["Exchanges"])
        sheet.append(fields)
        for exc in ds["exchanges"]:
            row = []
            for field in fields:
                value = exc.get(field)
                if field == "categories" and isinstance(value, (tuple, list)):
                    value = "::".join(value)
                row.append(cell(value))
            sheet.append(row)
        sheet.append([])
    workbook.save(path)
    workbook.close()
