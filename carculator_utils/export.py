"""
export.py contains the class Export, which offers methods to export the inventories
in different formats.
"""

from __future__ import annotations

import datetime
import json
import uuid
import warnings
from numbers import Real
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, List, Tuple

import numpy as np
import pyprind
import xarray as xr
import yaml

from . import DATA_DIR
from .fuel_supply import load_fuel_supply_recipes


def safe_filename(name: str) -> str:
    """Return a filename-safe string without requiring bw2io at import time."""
    return "".join(
        char if char.isalnum() or char in " -_." else "_" for char in str(name)
    ).strip()


def _is_noise_exchange(exchange):
    """Recognize only carculator's 24 custom day-time noise flows."""
    categories = tuple(exchange.get("categories") or ())
    return (
        exchange.get("type") == "biosphere"
        and exchange.get("unit") == "joule"
        and len(categories) == 3
        and categories[0] in {f"octave {i}" for i in range(1, 9)}
        and categories[1] == "day time"
        and categories[2] in {"urban", "suburban", "rural"}
        and exchange.get("name") == "noise, " + ", ".join(categories)
    )


def load_references() -> dict:
    """
    Load LCIs to fetch metadata from.
    """
    filepath = DATA_DIR / "export" / "references.json"
    if not filepath.is_file():
        raise FileNotFoundError("The references file could not be found.")

    with open(filepath, encoding="utf-8") as f:
        references = json.load(f)

    for recipe in load_fuel_supply_recipes():
        references[recipe["name"][0]] = recipe["reference"]

    return references


def load_mapping(
    filename,
) -> Dict[Tuple[str, str, str, str], Tuple[str, str, str, str]]:
    """
    Load mapping dictionary between
    two versions of ecoinvent.
    """

    # Load the matching dictionary
    filepath = DATA_DIR / "export" / filename
    if not filepath.is_file():
        raise FileNotFoundError(
            "The dictionary of activities flows match " "could not be found."
        )
    with open(filepath, encoding="utf-8") as f:
        csv_list = [[val.strip() for val in r.split(";")] for r in f.readlines()]
    (_, _, *header), *data = csv_list

    dict_map = {}

    for row in data:
        (
            name_to,
            location_to,
            categories_to,
            unit_to,
            ref_prod_to,
            name_from,
            location_from,
            categories_from,
            unit_from,
            ref_prod_from,
        ) = row
        dict_map[
            (
                name_to,
                location_to,
                tuple(categories_to.split("::")) if categories_to != "" else "",
                unit_to,
                ref_prod_to,
            )
        ] = (
            name_from,
            location_from,
            tuple(categories_from.split("::")) if categories_from != "" else "",
            unit_from,
            ref_prod_from,
        )

    return dict_map


def rename_mapping(filename: str) -> Dict[str, str]:
    """
    Load the file rename_powertrains.yaml and return a dictionary
    """
    with open(DATA_DIR / "export" / filename, encoding="utf-8") as f:
        rename_map = yaml.safe_load(f)

    return rename_map


class ExportInventory:
    """
    Export the inventory to various formats

    """

    def __init__(
        self, array, vehicle_model, indices, db_name="carculator_utils export"
    ):
        self.array: xr.DataArray = array
        self.indices: Dict[int, Tuple[str, str, str, str]] = indices
        self.vm = vehicle_model
        self.rename_pwt = rename_mapping("rename_powertrains.yaml")
        self.rename_parameters = rename_mapping("rename_parameters.yaml")
        self.rename_vehicles()
        self.rev_rename_pwt = {v: k for k, v in self.rename_pwt.items()}
        self.db_name: str = db_name
        self.references = load_references()

        self.flow_map = {
            "3.9": load_mapping(filename="ei310_to_ei39.csv"),
        }

    def rename_vehicles(self) -> None:
        """
        Rename powertrain acronyms to full length descriptive terms

        """

        for k, value in self.indices.items():
            for key, val in self.rename_pwt.items():
                if key in value[0]:
                    new_val = list(value)
                    new_val[0] = new_val[0].replace(key, val)
                    self.indices[k] = tuple(
                        new_val,
                    )

    def write_lci(self, ecoinvent_version: str, year: int) -> List[Dict]:
        """
        Return activities and exchanges for a single retained value sample.

        Select one sample before constructing the vehicle model and inventory.
        Its label may be numeric or a sensitivity parameter name.

        :returns: activity dictionaries containing their exchanges
        :rtype: list[dict]
        :raises ValueError: if the inventory or model contains multiple samples
        """

        if self.array.shape[0] != 1 or self.vm.array.sizes["value"] != 1:
            raise ValueError(
                "Inventory export requires exactly one value sample in both the "
                "inventory and vehicle model. Select one sample with "
                "array.isel(value=[index]) before constructing the model and inventory."
            )

        idx_year = self.vm.array.coords["year"].values.tolist().index(year)

        list_act = []

        # List of coordinates for non-zero values
        non_zeroes = np.nonzero(self.array[0, :, :, idx_year])
        # List of coordinates where activities present more than once
        # (to filter out "empty" activities, that is,
        # activities with only one reference product exchange)
        u, c = np.unique(non_zeroes[1], return_counts=True)
        dup = u[c > 1]

        # Filter out coordinates of "empty" activities
        coords = np.column_stack(
            (
                non_zeroes[0][np.isin(non_zeroes[1], dup)],
                non_zeroes[1][np.isin(non_zeroes[1], dup)],
            )
        )

        # Iterate through activities
        bar = pyprind.ProgBar(len(dup))
        for d in dup:
            bar.update(item_id=d)
            list_exc = []
            for row, col in coords[coords[:, 1] == d]:
                tuple_output = self.indices[col]
                tuple_input = self.indices[row]
                mult_factor = 1

                # check migration dictionary self.flow_map
                if ecoinvent_version in self.flow_map:
                    if len(tuple_input) == 3:
                        tupled = (
                            tuple_input[0],
                            "",
                            tuple_input[1],
                            tuple_input[2],
                            "",
                        )
                        if tupled in self.flow_map[ecoinvent_version]:
                            tuple_input = self.flow_map[ecoinvent_version][tupled]
                            # remove the ""
                            tuple_input = (
                                tuple_input[0],
                                tuple_input[2],
                                tuple_input[3],
                            )
                    else:
                        tupled = (
                            tuple_input[0],
                            tuple_input[1],
                            "",
                            tuple_input[2],
                            tuple_input[3],
                        )
                        if tupled in self.flow_map[ecoinvent_version]:
                            tuple_input = self.flow_map[ecoinvent_version][tupled]
                            # remove the ""
                            tuple_input = (
                                tuple_input[0],
                                tuple_input[1],
                                tuple_input[3],
                                tuple_input[4],
                            )

                amount = self.array[0, row, col, idx_year] * mult_factor

                exc = {
                    "name": tuple_input[0],
                    "unit": tuple_input[2],
                    "amount": amount * -1,
                }

                if len(tuple_input) == 3:
                    # biosphere exchange
                    exc["type"] = "biosphere"
                    exc["database"] = "biosphere3"
                    exc["categories"] = tuple_input[1]

                else:
                    exc["location"] = tuple_input[1]
                    exc["reference product"] = tuple_input[3]
                    exc["database"] = self.db_name

                    if tuple_output == tuple_input:
                        # reference product exchange
                        exc["amount"] *= -1
                        exc["type"] = "production"
                    else:
                        exc["type"] = "technosphere"

                list_exc.append(exc)

            source, comment = None, None

            if tuple_output[0] in self.references:
                source = self.references[tuple_output[0]].get("source")
                comment = self.references[tuple_output[0]].get("comment")
            elif self.vm.vehicle_type in tuple_output[0].lower():
                pass
            elif tuple_output[0].startswith("fuel supply for") or tuple_output[
                0
            ].startswith("electricity supply for"):
                pass
            else:
                print(f"Missing reference for {tuple_output[0]}")

            string = ""

            if f"{self.vm.vehicle_type}, " in tuple_output[0].lower():
                available_powertrains = [
                    self.rename_pwt[p] for p in self.vm.array.powertrain.values.tolist()
                ]
                available_sizes = self.vm.array.coords["size"].values.tolist()

                if any([w in tuple_output[0] for w in available_powertrains]) and any(
                    [w in tuple_output[0] for w in available_sizes]
                ):
                    possible_pwt = [
                        w for w in available_powertrains if w in tuple_output[0]
                    ]
                    if len(possible_pwt) > 1:
                        pwt = max(possible_pwt, key=len)
                    else:
                        pwt = possible_pwt[0]
                    pwt = self.rev_rename_pwt[pwt]

                    possible_sizes = [
                        w for w in available_sizes if w in tuple_output[0]
                    ]
                    if len(possible_sizes) > 1:
                        size = max(possible_sizes, key=len)
                    else:
                        size = possible_sizes[0]

                    string += f"Manufacture year: {year}. "
                    for param, formatting in self.rename_parameters.items():
                        if param not in self.vm.array.parameter.values:
                            continue

                        val = (
                            self.vm.array.sel(
                                powertrain=pwt,
                                size=size,
                                year=int(year),
                                parameter=param,
                            )
                            .isel(value=0)
                            .item()
                        )

                        if formatting.get("percentage", False):
                            val *= 100
                            val = "{:0.1f}".format(val)
                        else:
                            if val < 10:
                                val = "{:0.1f}".format(val)
                            else:
                                val = int(val)

                        string += f"{formatting['name']}: {val} {formatting['unit']}. "

            new_act = {
                "production amount": 1,
                "database": self.db_name,
                "name": tuple_output[0],
                "unit": tuple_output[2],
                "location": tuple_output[1],
                "exchanges": list_exc,
                "reference product": tuple_output[3],
                "type": "process",
                "code": str(uuid.uuid1()),
            }

            if source is not None:
                new_act["source"] = source
            if comment is not None:
                new_act["comment"] = comment
            elif string != "":
                new_act["comment"] = string
            else:
                pass

            list_act.append(new_act)

        return list_act

    def _brightpath_inventory(self, data, ecoinvent_version, database_name=None):
        """Prepare a private canonical inventory with an exact background context.

        Carculator owns foreground metadata and its existing 3.10-to-3.9 mapping.
        Brightpath owns normalization, format validation and serialization.
        This does not certify links against an installed background database.
        """
        from copy import deepcopy

        from brightpath import (
            BackgroundContext,
            BiosphereProfile,
            BrightwayInventory,
            FormatProfile,
            InventoryContext,
            InventoryValidationError,
            TechnosphereProfile,
        )

        data = deepcopy(data)
        database_name = database_name or getattr(self, "db_name", "carculator export")
        for activity in data:
            reference = self.references.get(activity["name"], {})
            for field in ("comment", "source"):
                if field not in activity and field in reference:
                    activity[field] = reference[field]
            # Brightpath requires a nonempty activity comment. This identifies
            # generated data without inventing a literature citation.
            if not activity.get("comment"):
                activity["comment"] = "Inventory generated by carculator_utils."
            activity["database"] = database_name

        identities = {
            (a["name"], a["reference product"], a["location"], a["unit"]) for a in data
        }
        for activity in data:
            for exchange in activity["exchanges"]:
                amount = exchange.get("amount")
                if isinstance(amount, Real) and not np.isfinite(amount):
                    raise ValueError(
                        f"Nonfinite exchange amount in {activity['name']!r}: "
                        f"{exchange.get('name')!r}."
                    )
                identity = tuple(
                    exchange.get(k)
                    for k in ("name", "reference product", "location", "unit")
                )
                if exchange["type"] == "production" or identity in identities:
                    exchange["database"] = database_name
                elif exchange["type"] == "technosphere":
                    # External suppliers must be matched to the user's database;
                    # they do not belong to the generated foreground database.
                    exchange.pop("database", None)

        context = InventoryContext(
            format=FormatProfile("brightway_excel", dialect="bw2io"),
            background=BackgroundContext(
                technosphere=TechnosphereProfile(
                    "ecoinvent", ecoinvent_version, "cutoff"
                ),
                biosphere=BiosphereProfile("ecoinvent", ecoinvent_version),
            ),
        )
        inventory = BrightwayInventory.from_data(
            data, context=context, database_name=database_name
        ).normalize()
        report = inventory.validate(check_background_links=False)
        # Brightpath's standard compartment whitelist does not include our
        # custom noise flows. Excel and JSON-LD can preserve them verbatim.
        # Exempt this one diagnostic, keeping amount/identity checks in force.
        noise_paths = {
            f"activity[{i}].exchanges[{j}]"
            for i, activity in enumerate(data)
            for j, exchange in enumerate(activity["exchanges"])
            if _is_noise_exchange(exchange)
        }
        report.issues = [
            issue
            for issue in report.issues
            if not (
                issue.code == "inventory_structure"
                and issue.path in noise_paths
                and "unsupported biosphere category" in issue.message
            )
        ]
        if report.has_errors:
            raise InventoryValidationError(report)
        return inventory

    def _simapro_inventory(self, inventory):
        """Attach carculator's foreground classifications before serialization."""
        from brightpath import SimaProInventory

        data = inventory.data
        omitted_noise = 0
        for activity in data:
            exchanges = activity["exchanges"]
            activity["exchanges"] = [e for e in exchanges if not _is_noise_exchange(e)]
            omitted_noise += len(exchanges) - len(activity["exchanges"])
            # Same physical unit; Brightpath uses ecoinvent's person-kilometre
            # spelling. Apply it to both producers and consumers on this copy.
            for record in [activity, *activity["exchanges"]]:
                if record["unit"] == "passenger kilometer":
                    record["unit"] = "person kilometer"
            name = activity["name"].lower()
            waste = (
                any(
                    word in name
                    for word in (
                        "waste",
                        "emissions",
                        "treatment",
                        "scrap",
                        "used powertrain",
                        "disposal",
                        "sludge",
                        "used li-ion",
                    )
                )
                and "biomethane" not in name
                and not name.startswith(
                    (
                        "supply and refining of waste cooking oil",
                        "carbon fiber production,",
                    )
                )
            )
            if waste:
                category = "waste treatment"
            elif activity["unit"] in (
                "kilometer",
                "person kilometer",
                "ton kilometer",
            ):
                category = "transport"
            elif activity["unit"] in ("kilowatt hour", "megajoule"):
                category = "energy"
            else:
                category = "material"
            for exchange in activity["exchanges"]:
                if exchange["type"] == "production":
                    exchange["simapro category"] = f"{category}/carculator"
        if omitted_noise:
            warnings.warn(
                f"SimaPro export omits {omitted_noise} custom noise exchanges, "
                "which its standard flow sections cannot represent. "
                "Brightway and openLCA exports retain them.",
                UserWarning,
                stacklevel=3,
            )
        return SimaProInventory.from_data(
            data,
            context=inventory.to_simapro().context,
            database_name=inventory.database_name,
        )

    def format_data_for_lci_for_simapro(
        self, data: List[Dict], ei_version: str
    ) -> List[List]:
        """Return Brightpath-rendered SimaPro rows (before file encoding)."""
        from brightpath import SimaProSerializationError

        inventory = self._brightpath_inventory(data, ei_version)
        result = self._simapro_inventory(inventory).render()
        if result.has_errors:
            raise SimaProSerializationError("\n".join(i.message for i in result.issues))
        self._check_simapro_losses(result)
        return result.rows

    @staticmethod
    def _check_simapro_losses(result):
        """Never silently omit exchanges reported by the format renderer."""
        from brightpath import SimaProSerializationError

        unused = [
            i.message for i in result.issues if i.code == "simapro_exchange_unused"
        ]
        if unused:
            raise SimaProSerializationError("\n".join(unused))

    def get_export_filepath(self, filename, directory=None):
        directory = Path(directory or Path.cwd()).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        return str(directory / filename)

    def _write_exports(
        self, ecoinvent_version, directory, filename, export_format, software
    ):
        """Use Brightpath writers; preserve the established per-year return types."""
        from brightpath.formats.openlca_jsonld import write_openlca_jsonld
        from brightpath.formats.simapro_csv import write_simapro_csv
        from brightpath.models import InventoryDocument, InventoryFormat

        if ecoinvent_version not in ("3.9", "3.10"):
            raise ValueError("ecoinvent_version must be either '3.9' or '3.10'")
        if export_format not in ("file", "string", "bw2io") or (
            export_format == "bw2io" and software != "brightway2"
        ):
            raise ValueError("Unsupported inventory export format for this software.")
        if software == "openlca":
            warnings.warn(
                "openLCA export contains foreground processes only. External ecoinvent "
                "suppliers and LCIA elementary flows need linking in the target database "
                "before calculation; generated identifiers do not establish these links.",
                UserWarning,
                stacklevel=3,
            )

        exports = []
        base = filename or safe_filename(f"carculator_export_{datetime.date.today()}")
        suffix = {
            "brightway2": "bw2.xlsx",
            "simapro": "simapro.csv",
            "openlca": "openlca.zip",
        }[software]
        # Brightpath's writers accept paths. Temporary files provide the legacy
        # in-memory API without maintaining another Excel/CSV/JSON-LD writer.
        with TemporaryDirectory(prefix="carculator-export-") as temporary:
            for year in self.vm.array.coords["year"].values:
                data = self.write_lci(ecoinvent_version=ecoinvent_version, year=year)
                inventory = self._brightpath_inventory(
                    data, ecoinvent_version, f"{self.db_name}_{year}"
                )
                if export_format == "bw2io":
                    try:
                        from bw2io.importers.base_lci import LCIImporter
                    except ImportError as exc:
                        raise ImportError(
                            "Brightway export requires carculator_utils[brightway]."
                        ) from exc
                    importer = LCIImporter(inventory.database_name)
                    importer.data = inventory.data
                    exports.append(importer)
                    continue

                destination = self.get_export_filepath(
                    f"{base}_{year}_{suffix}",
                    temporary if export_format == "string" else directory,
                )
                if software == "brightway2":
                    # Structural validation already ran; external backgrounds
                    # are matched by the receiving application.
                    inventory.write_excel(destination, validate=False)
                elif software == "simapro":
                    simapro = self._simapro_inventory(inventory)
                    document = InventoryDocument(
                        data=simapro.data,
                        context=simapro.context,
                        database_name=simapro.database_name,
                    )
                    # Check representation before publishing the file.
                    result = simapro.render()
                    if result.has_errors:
                        from brightpath import SimaProSerializationError

                        raise SimaProSerializationError(
                            "\n".join(i.message for i in result.issues)
                        )
                    self._check_simapro_losses(result)
                    write_simapro_csv(document, destination)
                else:
                    document = InventoryDocument(
                        data=inventory.data,
                        background_profile=inventory.background_profile,
                        biosphere_profile=inventory.biosphere_profile,
                        inventory_format=InventoryFormat.OPENLCA_JSONLD,
                        database_name=inventory.database_name,
                    )
                    write_openlca_jsonld(document, destination)

                if export_format == "string":
                    path = Path(destination)
                    exports.append(
                        path.read_text(encoding="latin-1")
                        if software == "simapro"
                        else path.read_bytes()
                    )
                else:
                    exports.append(destination)
        # Brightway Excel bytes have historically always been returned as a list.
        if software == "brightway2" and export_format == "string":
            return exports
        return exports[0] if len(exports) == 1 else exports

    def write_simapro_lci(
        self, ecoinvent_version, directory=None, filename=None, export_format="file"
    ):
        """Export Latin-1 SimaPro CSV files or their decoded contents."""
        return self._write_exports(
            ecoinvent_version, directory, filename, export_format, "simapro"
        )

    def write_bw2_lci(
        self, ecoinvent_version, directory=None, filename=None, export_format="file"
    ):
        """Export Brightway Excel files/bytes or unlinked bw2io importers."""
        return self._write_exports(
            ecoinvent_version, directory, filename, export_format, "brightway2"
        )

    def write_openlca_lci(
        self, ecoinvent_version, directory=None, filename=None, export_format="file"
    ):
        """Export a foreground-only openLCA JSON-LD ZIP as a file or bytes."""
        return self._write_exports(
            ecoinvent_version, directory, filename, export_format, "openlca"
        )
