"""
inventory.py contains InventoryCalculation which provides all methods to solve inventories.
"""

import ast
import csv
import itertools
import re
import warnings
from collections import defaultdict
from copy import copy
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pyprind
import xarray as xr
import yaml
from numpy import dtype, ndarray
from scipy import sparse

from . import DATA_DIR
from .background_systems import BackgroundSystemModel
from .electricity import (
    DEFAULT_SCENARIO,
    ElectricityDataWarning,
    select_electricity_mix,
)
from .fuel_supply import fill_fuel_suppliers, register_fuel_suppliers
from .inventory_electricity import lifetime_mix, specialize_electricity_supplies

warnings.filterwarnings("ignore", category=np.VisibleDeprecationWarning)

IAM_FILES_DIR = DATA_DIR / "IAM"


RANGE_PARAM = {
    "two-wheeler": "range",
    "car": "range",
    "bus": "daily distance",
    "truck": "target range",
}


def check_func_unit(func_unit):
    """Check if func_unit is a valid functional unit."""
    if func_unit not in ["vkm", "pkm", "tkm"]:
        raise ValueError(
            f"Functional unit must be one of "
            f"'vkm', 'pkm', 'tkm', "
            f"not {func_unit}"
        )
    return func_unit


def check_scenario(scenario):
    """Check if scenario is a valid scenario."""
    valid_scenarios = ["SSP2-NPi", "SSP2-PkBudg1000", "SSP2-PkBudg650", "static"]
    if scenario not in valid_scenarios:
        raise ValueError(
            f"Scenario must be one of " f"{valid_scenarios}, " f"not {scenario}"
        )
    return scenario


def get_noise_emission_flows() -> dict:
    """Get noise emission flows from the noise emission file."""

    return {
        (
            f"noise, octave {i}, day time, {comp}",
            (f"octave {i}", "day time", comp),
            "joule",
        ): f"noise, octave {i}, day time, {comp}"
        for i in range(1, 9)
        for comp in ["urban", "suburban", "rural"]
    }


def get_exhaust_emission_flows() -> dict:
    with open(
        DATA_DIR / "emission_factors" / "exhaust_and_noise_flows.yaml",
        "r",
        encoding="utf-8",
    ) as stream:
        flows = yaml.safe_load(stream)["exhaust"]

    d_comp = {
        "urban": "urban air close to ground",
        "suburban": "non-urban air or from high stacks",
        "rural": "low population density, long-term",
    }

    grouped = defaultdict(list)
    for pollutant, flow in flows.items():
        for compartment, biosphere_compartment in d_comp.items():
            grouped[(flow, ("air", biosphere_compartment), "kilogram")].append(
                f"{pollutant} direct emissions, {compartment}"
            )
    # Retain the scalar mapping for one-to-one flows. Many-to-one mappings
    # must preserve every contributing parameter instead of overwriting it.
    return {
        flow: names[0] if len(names) == 1 else tuple(names)
        for flow, names in grouped.items()
    }


def get_dict_impact_categories(method, indicator) -> dict:
    """
    Load a dictionary with available impact assessment
    methods as keys, and assessment level and categories as values.

    :return: dictionary
    :rtype: dict
    """
    filename = "dict_impact_categories.csv"
    filepath = DATA_DIR / "lcia" / filename
    if not filepath.is_file():
        raise FileNotFoundError(
            "The dictionary of impact categories could not be found."
        )

    csv_dict = {}

    with open(filepath, encoding="utf-8") as f:
        input_dict = csv.reader(f, delimiter=",")
        for row in input_dict:
            if row[0] == method and row[1] == indicator:
                csv_dict[row[3]] = {
                    "method": row[1],
                    "category": row[2],
                    "type": row[3],
                    "abbreviation": row[4],
                    "unit": row[5],
                    "source": row[6],
                }

    return csv_dict


def get_dict_input() -> dict:
    """
    Load a dictionary with tuple ("name of activity", "location", "unit",
    "reference product") as key, row/column
    indices as values.

    :return: dictionary with `label:index` pairs.
    :rtype: dict

    """
    filename = f"dict_inputs_A_matrix.csv"
    filepath = DATA_DIR / "IAM" / filename
    if not filepath.is_file():
        raise FileNotFoundError("The dictionary of activity labels could not be found.")

    with open(filepath, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        raw = list(reader)
        for _r, r in enumerate(raw):
            if len(r) == 3:
                r[1] = ast.literal_eval(r[1])
            raw[_r] = tuple(r)

        return {j: i for i, j in enumerate(list(raw))}


def format_array(array):
    # Transpose the array as needed
    transposed_array = array.transpose(
        "value",
        "parameter",
        "size",
        "powertrain",
        "year",
    )

    # Determine the new shape for the reshaping operation
    new_shape = (
        array.sizes["value"],
        array.sizes["parameter"],
        -1,
        array.sizes["year"],
    )

    # Reshape the array while keeping it as an xarray DataArray
    reshaped_array = transposed_array.data.reshape(new_shape)

    combined_coords = [
        " - ".join(list(x))
        for x in list(
            itertools.product(
                array.coords["size"].values, array.coords["powertrain"].values
            )
        )
    ]

    # Convert the reshaped numpy array back to xarray DataArray
    reshaped_dataarray = xr.DataArray(
        reshaped_array,
        dims=["value", "parameter", "combined_dim", "year"],
        coords=[
            array.coords["value"].values,
            array.coords["parameter"].values,
            combined_coords,
            array.coords["year"].values,
        ],
    )

    return reshaped_dataarray


def validate_fuel_mappings(fuel_blend, inputs):
    """Reject unresolved fuel suppliers before allocating inventory matrices.

    :param fuel_blend: Completed model fuel specifications.
    :param inputs: Activity labels mapped to inventory indices.
    :raises KeyError: A selected fuel supplier is absent from the inventory.
    """
    for fuel, components in fuel_blend.items():
        for role in ("primary", "secondary"):
            component = components[role]
            supplier = tuple(component["name"])
            if supplier not in inputs:
                raise KeyError(
                    f"Fuel blend {fuel!r}, {role} fuel {component['type']!r}: "
                    f"supplier {supplier!r} is absent from the inventory index."
                )


class Inventory:
    """
    Build and solve the inventory for results characterization and inventory export

    :ivar vm: object from the VehicleModel class
    :ivar background_configuration: dictionary that contains choices for background system
    :ivar scenario: IAM energy scenario to use (
        "SSP2-NPi": Nationally implemented policies, limits temperature increase by 2100 to 3.3 degrees Celsius,
        "SSP2-PkBudg1000": limits temperature increase by 2100 to 2 degrees Celsius,
        "SSP2-PkBudg650": limits temperature increase by 2100 to 1.5 degrees Celsius,
        "static": no forward-looking modification of the background inventories).
        "SSP2-NPi" selected by default.)
    :ivar method: impact assessment method to use ("recipe" or "ef" for Environmental Footprint 3.1)
    :ivar indicator: impact assessment indicator to use ("midpoint" or "endpoint")
    :ivar functional_unit: functional unit to use ("vkm", "pkm", "tkm")

    """

    def __init__(
        self,
        vm,
        background_configuration: dict = None,
        scenario: str = "SSP2-NPi",
        method: str = "recipe",
        indicator: str = "midpoint",
        functional_unit: str = "vkm",
    ) -> None:
        if method not in ("recipe", "ef"):
            raise ValueError("method must be 'recipe' or 'ef'.")
        if indicator not in ("midpoint", "endpoint"):
            raise ValueError("indicator must be 'midpoint' or 'endpoint'.")
        self.vm = vm

        self.scope = {
            "size": vm.array.coords["size"].values.tolist(),
            "powertrain": vm.array.coords["powertrain"].values.tolist(),
            "year": vm.array.coords["year"].values.tolist(),
        }
        self.scenario = check_scenario(scenario)
        self.func_unit = check_func_unit(functional_unit)

        self.method = method
        self.indicator = indicator if method == "recipe" else "midpoint"

        self.array = format_array(vm.array)
        self.iterations = len(vm.array.value.values)

        self.number_of_vehicles = (self.vm["TtW energy"] > 0).sum().values

        self.background_configuration = {}
        self.background_configuration.update(background_configuration or {})

        self.inputs = get_dict_input()
        fuel_supply_recipes = register_fuel_suppliers(self.inputs, self.vm.fuel_blend)
        validate_fuel_mappings(self.vm.fuel_blend, self.inputs)

        self.bs = BackgroundSystemModel(
            electricity_scenario=self.background_configuration.get(
                "electricity scenario", DEFAULT_SCENARIO
            )
        )
        self.add_additional_activities()
        self.rev_inputs = {v: k for k, v in self.inputs.items()}

        with open(
            DATA_DIR / "electricity" / "elec_tech_map.yaml", "r", encoding="utf-8"
        ) as stream:
            self.elec_map = yaml.safe_load(stream)
            self.elec_map = {k: tuple(v) for k, v in self.elec_map.items()}

        self.electricity_technologies = list(self.elec_map.keys())

        self.A = self.get_A_matrix()
        fill_fuel_suppliers(self.A, self.inputs, fuel_supply_recipes)
        # Create electricity and fuel market datasets
        self.mix = self.define_electricity_mix_for_fuel_prep()
        self.create_electricity_mix_for_fuel_prep()
        self.rev_inputs = {v: k for k, v in self.inputs.items()}
        self.create_fuel_markets()

        self.exhaust_emissions = get_exhaust_emission_flows()
        self.noise_emissions = get_noise_emission_flows()

        self.list_cat, self.split_indices = self.get_split_indices()

        self.impact_categories = get_dict_impact_categories(
            method=self.method, indicator=self.indicator
        )

        # Create the B matrix
        self.B = self.get_B_matrix()
        self.rev_inputs = {v: k for k, v in self.inputs.items()}

        self.fill_in_A_matrix()
        self.remove_non_compliant_vehicles()
        specialize_electricity_supplies(self)

    def get_results_table(self, sensitivity: bool = False) -> xr.DataArray:
        """
        Format a xarray.DataArray array to receive the results.

        :param sensitivity: if True, the results table will
        be formatted to receive sensitivity analysis results
        :return: xarrray.DataArray
        """

        response = xr.DataArray(
            np.zeros(
                (
                    len(self.impact_categories),
                    len(self.scope["size"]),
                    len(self.scope["powertrain"]),
                    len(self.scope["year"]),
                    len(self.list_cat),
                    self.iterations,
                )
            ),
            coords=[
                list(self.impact_categories.keys()),
                self.scope["size"],
                self.scope["powertrain"],
                self.scope["year"],
                self.list_cat,
                self.array.coords["value"].values.copy(),
            ],
            dims=[
                "impact_category",
                "size",
                "powertrain",
                "year",
                "impact",
                "value",
            ],
        )

        if sensitivity:
            # remove the `impact` dimension
            response = response.sum(dim="impact")

        return response

    def get_split_indices(self):
        """
        Return list of indices to split the results into categories.

        :return: list of indices
        :rtype: list
        """
        # read `impact_source_categories.yaml` file
        with open(
            DATA_DIR / "lcia" / "impact_source_categories.yaml", "r", encoding="utf-8"
        ) as stream:
            source_cats = yaml.safe_load(stream)

        idx_cats = defaultdict(list)

        for cat, name in source_cats.items():
            for n in name:
                idx = self.find_input_indices((n,))
                if idx and idx not in idx_cats[cat]:
                    idx_cats[cat].extend(idx)
            # remove duplicates
            idx_cats[cat] = list(set(idx_cats[cat]))

        # add flows corresponding to `exhaust - direct`
        idx_cats["direct - exhaust"] = [
            self.inputs[("Carbon dioxide, fossil", ("air",), "kilogram")],
            self.inputs[("Carbon dioxide, non-fossil", ("air",), "kilogram")],
        ]
        idx_cats["direct - exhaust"].append(
            self.inputs[("Sulfur dioxide", ("air",), "kilogram")]
        )
        idx_cats["direct - exhaust"].extend(
            [self.inputs[i] for i in self.exhaust_emissions]
        )
        idx_cats["direct - exhaust"].extend(
            [self.inputs[i] for i in self.noise_emissions]
        )

        idx_cats["direct - non-exhaust"].extend(
            self.inputs[(f"Methane, {origin}", ("air",), "kilogram")]
            for origin in ("fossil", "non-fossil")
        )

        # idx for an input that has no burden
        # oxygen in this case
        extra_idx = [j for i, j in self.inputs.items() if i[0].lower() == "oxygen"][0]

        list_ind = [val for val in idx_cats.values()]
        maxLen = max(map(len, list_ind))
        for row in list_ind:
            while len(row) < maxLen:
                row.append(extra_idx)

        return list(idx_cats.keys()), list_ind

    def get_load_factor(self):
        """Return loads aligned with result size/powertrain/year/sample axes."""
        if self.func_unit == "vkm":
            return 1
        parameter = "average passengers" if self.func_unit == "pkm" else "cargo mass"
        load = self.vm.array.sel(parameter=parameter).transpose(
            "size", "powertrain", "year", "value"
        )
        if self.func_unit == "tkm":
            load = load / 1000
        active = self.vm.array.sel(parameter="TtW energy").transpose(*load.dims) > 0
        invalid = (~np.isfinite(load) | (load <= 0)) & active
        if bool(invalid.any()):
            raise ValueError(
                f"{self.func_unit} requires finite, positive {parameter} for active vehicles."
            )
        # Unavailable vehicles contribute zero; avoid dividing that zero by zero.
        values = load.where(active, 1).values
        return values[None, :, :, :, None, :]

    def calculate_impacts(self, sensitivity=False):
        if self.scenario != "static":
            list_b_arrays = []
            for year in self.scope["year"]:
                if year < min(self.B.year.values):
                    arr = self.B.sel(
                        year=min(self.B.year.values),
                    ).values
                elif year > max(self.B.year.values):
                    arr = self.B.sel(
                        year=max(self.B.year.values),
                    ).values
                else:
                    arr = self.B.interp(
                        year=year, method="linear", kwargs={"fill_value": "extrapolate"}
                    ).values
                list_b_arrays.append(arr)
            B = np.array(list_b_arrays)
        else:
            # if static scenario, use the B matrix
            # but we duplicate it for each year
            B = np.repeat(self.B.values, len(self.scope["year"]), axis=0)

        # Prepare an array to store the results
        results = self.get_results_table(sensitivity=sensitivity)

        idx_car_trspt = [
            i
            for i, key in self.rev_inputs.items()
            if key[0].startswith(f"transport, {self.vm.vehicle_type}, ")
        ]
        idx_cars = [
            i
            for i, key in self.rev_inputs.items()
            if key[0].startswith(f"{self.vm.vehicle_type}, ")
        ]
        vehicle_rows = idx_cars + idx_car_trspt
        contributing = np.any(self.A[:, :, vehicle_rows, :] != 0, axis=(0, 2))
        contributing[vehicle_rows, :] = False
        nonzero_idx = np.argwhere(contributing)
        # Electricity and fuel supply matrices may differ between samples.
        # Factor each sample/year once and solve all required suppliers together.
        new_arr = np.zeros(
            (B.shape[1], self.iterations, self.A.shape[1], self.A.shape[-1])
        )
        bar = pyprind.ProgBar(
            self.iterations * self.A.shape[-1], stream=1, title="Calculating impacts"
        )
        for year in range(self.A.shape[-1]):
            used = np.flatnonzero(contributing[:, year])
            biosphere = [i for i in used if isinstance(self.rev_inputs[i][1], tuple)]
            technosphere = [i for i in used if i not in biosphere]
            demands = np.zeros((self.A.shape[1], len(technosphere)))
            demands[technosphere, np.arange(len(technosphere))] = 1
            for sample in range(self.iterations):
                factors = new_arr[:, sample, :, year]
                factors[:, biosphere] = B[year][:, biosphere]
                if technosphere:
                    solver = sparse.linalg.splu(
                        sparse.csc_matrix(self.A[sample, :, :, year])
                    )
                    factors[:, technosphere] = B[year] @ solver.solve(demands)
                bar.update()

        arr = (
            self.A[:, :, idx_car_trspt].reshape(
                self.iterations,
                -1,
                len(self.scope["size"]),
                len(self.scope["powertrain"]),
                len(self.scope["year"]),
            )
            * new_arr[:, :, :, None, None, :]
            * -1
        )

        arr += (
            self.A[:, :, idx_cars].reshape(
                self.iterations,
                -1,
                len(self.scope["size"]),
                len(self.scope["powertrain"]),
                len(self.scope["year"]),
            )
            * new_arr[:, :, :, None, None, :]
            * self.A[:, idx_cars, idx_car_trspt].reshape(
                self.iterations,
                -1,
                len(self.scope["size"]),
                len(self.scope["powertrain"]),
                len(self.scope["year"]),
            )
        )

        arr = arr[:, :, self.split_indices].sum(axis=3)

        # fetch indices not contained in self.split_indices
        # to see if there are other flows unaccounted for
        idx = [
            i
            for i in range(self.B.shape[-1])
            if i not in list(itertools.chain.from_iterable(self.split_indices))
        ]
        # check if any of the first items of nonzero_idx
        # are in idx
        for i in nonzero_idx:
            if i[0] in idx:
                print(f"The flow {self.rev_inputs[i[0]][0]} is not accounted for.")

        # reshape the array to match the dimensions of the results table
        arr = arr.transpose(0, 3, 4, 5, 2, 1)

        load_factor = self.get_load_factor()
        if sensitivity:
            results[...] = arr.sum(axis=-2)
            if isinstance(load_factor, np.ndarray):
                load_factor = np.squeeze(load_factor, axis=4)
            results = results / load_factor
            reference = results.sel(value="reference")
            return results / reference.where(reference != 0)
        results[...] = arr
        return results / load_factor

    def add_additional_activities(self):
        # Add as many rows and columns as cars to consider
        # Also add additional columns and rows for electricity markets
        # for fuel preparation and energy battery production

        maximum = max(self.inputs.values())

        for fuel in ["petrol", "diesel", "hydrogen", "methane"]:
            maximum += 1
            self.inputs[
                (
                    f"fuel supply for {fuel} vehicles",
                    self.vm.country,
                    "kilogram",
                    "fuel",
                )
            ] = maximum

        for electricity_source in [
            (f"electricity supply for electric vehicles", self.vm.country),
            (f"electricity supply for fuel preparation", self.vm.country),
        ]:
            maximum += 1
            self.inputs[
                (
                    electricity_source[0],
                    electricity_source[1],
                    "kilowatt hour",
                    "electricity, low voltage",
                )
            ] = maximum

        with open(DATA_DIR / "emission_factors" / "euro_classes.yaml", "r") as stream:
            euro_classes = yaml.safe_load(stream)[self.vm.vehicle_type]

        list_years = np.clip(
            self.scope["year"],
            min(euro_classes.keys()),
            max(euro_classes.keys()),
        )

        list_euro_classes = [euro_classes[y] for y in list(list_years)]

        for size in self.scope["size"]:
            for powertrain in self.scope["powertrain"]:
                for euro_class, year in zip(list_euro_classes, self.scope["year"]):
                    if self.func_unit == "vkm":
                        unit = "kilometer"
                    elif self.func_unit == "pkm":
                        unit = "passenger kilometer"
                    else:
                        unit = "ton kilometer"

                    name = f"transport, {self.vm.vehicle_type}, {powertrain}, {size}"
                    ref = f"transport, {self.vm.vehicle_type}"

                    # add transport activity
                    key = (name, self.vm.country, unit, ref)
                    if key not in self.inputs:
                        maximum += 1
                        self.inputs[(name, self.vm.country, unit, ref)] = maximum

                    # add vehicle
                    key = (
                        name.replace(
                            f"transport, {self.vm.vehicle_type}",
                            self.vm.vehicle_type,
                        ),
                        self.vm.country,
                        "unit",
                        ref.replace(
                            f"transport, {self.vm.vehicle_type}",
                            self.vm.vehicle_type,
                        ),
                    )

                    if key not in self.inputs:
                        maximum += 1
                        self.inputs[key] = maximum

    def get_A_matrix(self):
        """
        Load the A matrix. The matrix contains exchanges of products (rows)
        between activities (columns).

        :return: A matrix with three dimensions of shape (number of values,
        number of products, number of activities).
        :rtype: numpy.ndarray

        """

        filename = "A_matrix.npz"
        filepath = DATA_DIR / "IAM" / filename
        if not filepath.is_file():
            raise FileNotFoundError("The IAM files could not be found.")

        # load matrix A
        initial_A = sparse.load_npz(filepath).toarray()

        new_A = np.identity(len(self.inputs))
        new_A[0 : np.shape(initial_A)[0], 0 : np.shape(initial_A)[0]] = initial_A

        # Resize the matrix to fit the number of `value` in `self.array`
        new_A = np.resize(
            new_A,
            (
                self.iterations,
                len(self.inputs),
                len(self.inputs),
            ),
        )

        # add a `year`dimension, with length equal to the number of years
        # in the scope
        new_A = np.repeat(new_A[:, :, :, None], len(self.scope["year"]), axis=-1)

        return new_A

    def get_B_matrix(self) -> xr.DataArray:
        """
        Load the B matrix. The B matrix contains impact assessment
        figures for a give impact assessment method,
        per unit of activity. Its length column-wise equals
        the length of the A matrix row-wise.
        Its length row-wise equals the number of
        impact assessment methods.

        :return: an array with impact values per unit
        of activity for each method.
        :rtype: numpy.ndarray

        """

        filepaths = [
            str(fp)
            for fp in list(Path(IAM_FILES_DIR).glob("*.npz"))
            if all(x in str(fp) for x in [self.method, self.indicator, self.scenario])
        ]

        if self.scenario != "static":
            filepaths = sorted(filepaths, key=lambda x: int(x[-8:-4]))

        n_files = max(1, len(filepaths))  # guarantees the first dimension
        B = np.zeros((n_files, len(self.impact_categories), len(self.inputs)))

        for f, filepath in enumerate(filepaths):
            initial_B = sparse.load_npz(filepath).toarray()
            new_B = np.zeros((initial_B.shape[0], len(self.inputs)))
            new_B[: initial_B.shape[0], : initial_B.shape[1]] = initial_B
            B[f, :, :] = new_B

        years = (
            [
                2020,
            ]
            if self.scenario == "static"
            else [2005, 2010, 2020, 2030, 2040, 2050]
        )

        return xr.DataArray(
            B,
            coords=[
                np.asarray(years, dtype=int),
                np.asarray(list(self.impact_categories.keys()), dtype="object"),
                np.asarray(list(self.inputs.keys()), dtype="object"),
            ],
            dims=["year", "category", "activity"],
        )

    def get_index_of_flows(self, items_to_look_for, search_by="name"):
        """
        Return list of row/column indices of self.A of labels that contain the string defined in `items_to_look_for`.

        :param items_to_look_for: string
        :param search_by: "name" or "compartment" (for elementary flows)
        :return: list of row/column indices
        :rtype: list
        """
        if search_by == "name":
            return [
                int(self.inputs[c])
                for c in self.inputs
                if all(ele in c[0].lower() for ele in items_to_look_for)
            ]
        if search_by == "compartment":
            return [
                int(self.inputs[c])
                for c in self.inputs
                if all(ele in c[1] for ele in items_to_look_for)
            ]

    def define_electricity_mix_for_fuel_prep(self) -> np.ndarray:
        """Build per-vehicle/sample mixes and return their legacy summary by year.

        ``electricity_mix`` is the labelled array used in the inventories.
        ``mix`` remains a year/technology summary for existing reporting code.
        """
        custom = self.background_configuration.get("custom electricity mix")
        if custom is not None:
            # An explicit custom mix does not require national background data.
            generation = self.bs.electricity_mix.isel(country=0)
            self.electricity_provenance = {
                "electricity_scenario": "custom",
                "country": self.vm.country,
                "requested_country": self.vm.country,
                "boundary": "user-supplied electricity mix",
                "horizon_policy": "custom",
            }
        else:
            generation, self.electricity_provenance = select_electricity_mix(
                self.bs.electricity_mix,
                self.vm.country,
                self.background_configuration.get("electricity fallback country"),
            )
        self.electricity_mix = lifetime_mix(
            self.array,
            generation,
            self.electricity_technologies,
            custom,
            horizon_policy=generation.attrs.get("horizon_policy", "hold"),
        )
        self.electricity_mix.attrs.update(self.electricity_provenance)
        return self.electricity_mix.mean(("value", "combined_dim")).values

    def define_renewable_rate_in_mix(self) -> ndarray[Any, dtype[Any]]:
        """
        This function returns the renewable rate in the electricity mix
        for each year.
        """

        sum_non_hydro_renew = [
            np.sum([mix[i] for i in [3, 4, 5, 8, 9, 10, 11, 14, 18, 19]])
            for mix in self.mix
        ]

        sum_hydro = [np.sum([mix[i] for i in [0, 15]]) for mix in self.mix]

        sum_nuclear = [
            np.sum(
                [
                    mix[i]
                    for i in [
                        1,
                    ]
                ]
            )
            for mix in self.mix
        ]

        rates = np.vstack(
            (
                sum_non_hydro_renew,
                sum_hydro,
                sum_nuclear,
            )
        )

        return rates

    def find_input_indices(
        self, contains: [tuple, str], excludes: tuple = (), excludes_in: int = 0
    ) -> list:
        """
        This function finds the indices of the inputs in the A matrix
        that contain the strings in the contains list, and do not
        contain the strings in the excludes list.
        :param contains: list of strings
        :param excludes: list of strings
        :param excludes_in: integer of item position to apply excludes filter
        :return: list of indices
        """
        indices = []

        if not isinstance(contains, tuple):
            contains = tuple(contains)

        if not isinstance(excludes, tuple):
            excludes = tuple(excludes)

        for i, input in enumerate(self.inputs):
            if all([c in input[0] for c in contains]) and not any(
                [e in input[excludes_in] for e in excludes]
            ):
                indices.append(i)

        if len(indices) == 0:
            print(
                f"No input found for {contains} and exclude {excludes} in the A matrix."
            )

        return indices

    def add_electricity_infrastructure(self, dataset, losses):
        # Add transmission network for high and medium voltage
        for input in [
            (
                ("transmission network construction, electricity, high voltage",),
                dataset,
                6.58e-9 * -1 * losses,
            ),
            (
                ("transmission network construction, electricity, medium voltage",),
                dataset,
                1.86e-8 * -1 * losses,
            ),
            (
                ("distribution network construction, electricity, low voltage",),
                dataset,
                8.74e-8 * -1 * losses,
            ),
            (
                ("market for sulfur hexafluoride, liquid",),
                dataset,
                (5.4e-8 + 2.99e-9) * -1 * losses,
            ),
            (("Sulfur hexafluoride",), dataset, (5.4e-8 + 2.99e-9) * -1 * losses),
        ]:
            self.A[
                np.ix_(
                    np.arange(self.iterations),
                    self.find_input_indices(
                        input[0],
                    )[:1],
                    self.find_input_indices((input[1],)),
                )
            ] = input[2]

    def create_electricity_mix_for_fuel_prep(self):
        """
        This function fills the electricity market that
        supplies battery charging operations
        and hydrogen production through electrolysis.
        """

        loss_country = {"UK": "GB", "NM": "NA"}.get(self.vm.country, self.vm.country)
        if self.electricity_provenance["electricity_scenario"] == "legacy":
            loss_country = self.vm.country
        if loss_country not in self.bs.losses:
            warnings.warn(
                f"Electricity losses for {self.vm.country} use the legacy RER low-voltage multiplier.",
                ElectricityDataWarning,
                stacklevel=2,
            )
            loss_country = "RER"
        losses_to_low = float(self.bs.losses[loss_country]["LV"])
        self.electricity_provenance.update(
            loss_country=loss_country, loss_multiplier=losses_to_low
        )
        self.electricity_mix.attrs.update(self.electricity_provenance)

        self.electricity_losses = losses_to_low
        # Fill the electricity markets for battery charging and hydrogen production
        # Add electricity technology shares
        self.A[
            np.ix_(
                np.arange(self.iterations),
                [self.inputs[self.elec_map[t]] for t in self.electricity_technologies],
                self.find_input_indices(("electricity supply for fuel preparation",)),
            )
        ] = (
            -self.electricity_mix.isel(combined_dim=0)
            .transpose("value", "technology", "year")
            .values[:, :, None, :]
            * losses_to_low
        )

        self.add_electricity_infrastructure(
            "electricity supply for fuel preparation", losses_to_low
        )

    def get_sulfur_content(self, location, fuel):
        """
        Return the sulfur content in the fuel.
        If a region is passed, the average sulfur content over
        the countries the region contains is returned.

        :param year:
        :param location: str. A country or region ISO code
        :param fuel: str. "diesel" or "petrol"
        :return: float. Sulfur content in ppm.
        """

        if fuel not in self.bs.sulfur.fuel.values:
            return 0

        if location in self.bs.sulfur.country.values:
            sulfur_concentration = (
                self.bs.sulfur.sel(country=location, year=self.scope["year"], fuel=fuel)
                .sum()
                .values
            )
        else:
            # If the geography is not found,
            # we use the European average

            print(
                f"The sulfur content for {fuel} fuel in {location} "
                f"could not be found."
                "European average sulfur content is used instead."
            )

            sulfur_concentration = (
                self.bs.sulfur.sel(country="RER", year=self.scope["year"], fuel=fuel)
                .sum()
                .values
            )

        return sulfur_concentration

    def create_fuel_markets(self):
        """
        This function creates markets for fuel, considering a given blend,
        a given fuel type and a given year.
        It also adds separate electricity input in case hydrogen
        from electrolysis is needed somewhere in the fuel supply chain.
        :return:
        """

        d_dataset_name = {
            "petrol": "fuel supply for petrol vehicles",
            "diesel": "fuel supply for diesel vehicles",
            "methane": "fuel supply for methane vehicles",
            "hydrogen": "fuel supply for hydrogen vehicles",
        }

        # electricity dataset
        # for y, year in enumerate(self.scope["year"]):
        self.A[
            :,
            self.find_input_indices(("electricity supply for fuel preparation",)),
            self.find_input_indices((f"electricity supply for electric vehicles",)),
        ] = -1

        # fuel datasets
        for fuel_type in self.vm.fuel_blend:
            self.find_input_requirement(
                value_in="kilowatt hour",
                find_input_by="unit",
                value_out=self.vm.fuel_blend[fuel_type]["primary"]["name"][0],
                replace_by=self.find_input_indices(
                    ("electricity supply for fuel preparation",)
                ),
            )
            self.find_input_requirement(
                value_in="kilowatt hour",
                find_input_by="unit",
                value_out=self.vm.fuel_blend[fuel_type]["secondary"]["name"][0],
                replace_by=self.find_input_indices(
                    ("electricity supply for fuel preparation",)
                ),
            )

            for y, year in enumerate(self.scope["year"]):
                primary_share = self.vm.fuel_blend[fuel_type]["primary"]["share"][y]
                secondary_share = self.vm.fuel_blend[fuel_type]["secondary"]["share"][y]
                fuel_market_index = self.find_input_indices(
                    (d_dataset_name[fuel_type],)
                )

                try:
                    primary_fuel_activity_index = self.inputs[
                        self.vm.fuel_blend[fuel_type]["primary"]["name"]
                    ]
                    secondary_fuel_activity_index = self.inputs[
                        self.vm.fuel_blend[fuel_type]["secondary"]["name"]
                    ]
                except KeyError:
                    raise KeyError(
                        "One of the primary or secondary fuels specified in "
                        "the fuel blend for {} is not valid.".format(fuel_type)
                    )

                # Two fuel labels can resolve to the same supplier. Accumulate
                # their mass shares instead of overwriting the first exchange.
                suppliers = {primary_fuel_activity_index: primary_share}
                suppliers[secondary_fuel_activity_index] = (
                    suppliers.get(secondary_fuel_activity_index, 0) + secondary_share
                )
                for supplier, share in suppliers.items():
                    self.A[:, supplier, fuel_market_index, y] = -share

    def find_input_requirement(
        self,
        value_in,
        value_out,
        find_input_by="name",
        zero_out_input=False,
        filter_activities=None,
        replace_by=None,
    ):
        """
        Finds the exchange inputs to a specified functional unit
        :param zero_out_input:
        :param find_input_by: can be 'name' or 'unit'
        :param value_in: value to look for
        :param value_out: functional unit output
        :return: indices of all inputs to FU, indices of inputs of interest
        :rtype: tuple
        """

        if isinstance(value_out, str):
            value_out = (value_out,)

        index_output = self.find_input_indices(value_out)

        f_vector = np.zeros((np.shape(self.A)[1]))
        f_vector[index_output] = 1

        X = sparse.linalg.spsolve(sparse.csr_matrix(self.A[0, ..., 0]), f_vector.T)

        ind_inputs = np.nonzero(X)[0]

        if find_input_by == "name":
            ins = [
                i
                for i in ind_inputs
                if value_in.lower() in self.rev_inputs[i][0].lower()
            ]

        elif find_input_by == "unit":
            ins = [
                i
                for i in ind_inputs
                if value_in.lower() in self.rev_inputs[i][2].lower()
            ]
        else:
            raise ValueError("find_input_by must be 'name' or 'unit'")

        outs = [i for i in ind_inputs if i not in ins]

        if filter_activities:
            outs = [
                i
                for e in filter_activities
                for i in outs
                if e.lower() in self.rev_inputs[i][0].lower()
            ]

        ins = [
            i
            for i in ins
            if self.A[np.ix_(np.arange(0, self.A.shape[0]), [i], outs)].sum() != 0
        ]

        # if replace_by, replace the input by the new one
        if replace_by:
            for i in ins:
                if i != replace_by:
                    amount = self.A[np.ix_(np.arange(0, self.A.shape[0]), [i], outs)]
                    self.A[np.ix_(np.arange(0, self.A.shape[0]), [i], outs)] = 0
                    self.A[
                        np.ix_(np.arange(0, self.A.shape[0]), replace_by, outs)
                    ] += amount

        return

    def get_fuel_blend_carbon_intensity(
        self, fuel_type: str
    ) -> [np.ndarray, np.ndarray]:
        """
        Returns the carbon intensity of a fuel blend.
        :param fuel_type: fuel type
        :return: carbon intensity of fuel blend fossil, and biogenic
        """
        primary_share = self.vm.fuel_blend[fuel_type]["primary"]["share"]
        secondary_share = self.vm.fuel_blend[fuel_type]["secondary"]["share"]

        primary_CO2 = self.vm.fuel_blend[fuel_type]["primary"]["CO2"]
        secondary_CO2 = self.vm.fuel_blend[fuel_type]["secondary"]["CO2"]

        primary_biogenic_share = self.vm.fuel_blend[fuel_type]["primary"][
            "biogenic share"
        ]
        secondary_biogenic_share = self.vm.fuel_blend[fuel_type]["secondary"][
            "biogenic share"
        ]

        return (
            primary_share * primary_CO2 * (1 - primary_biogenic_share)
            + secondary_share * secondary_CO2 * (1 - secondary_biogenic_share),
            primary_share * primary_CO2 * primary_biogenic_share
            + secondary_share * secondary_CO2 * secondary_biogenic_share,
        )

    def fill_in_A_matrix(self):
        """
        Fill-in the A matrix. Does not return anything. Modifies in place.
        Shape of the A matrix (values, products, activities).

        :param array: :attr:`array` from :class:`CarModel` class
        """

        pass

    def add_fuel_cell_stack(self):
        self.A[
            :,
            self.find_input_indices(
                (
                    "fuel cell Balance of Plant production, 1 kWe, proton exchange membrane (PEM)",
                )
            ),
            [
                x
                for x, y in self.rev_inputs.items()
                if y[0].startswith(f"{self.vm.vehicle_type}, ")
            ],
        ] = (
            self.array.sel(
                parameter=[
                    "fuel cell ancillary BoP mass",
                    "fuel cell essential BoP mass",
                ]
            ).sum(dim="parameter")
            / 6.6  # 6.6 kg BoP per kWe
            * (1 + self.array.sel(parameter="fuel cell lifetime replacements"))
            * -1
        )

        # note: `Stack`refers to the power of the stack, not mass
        self.A[
            :,
            self.find_input_indices(
                contains=(
                    "fuel cell stack production, 1 kWe, proton exchange membrane (PEM)",
                ),
            ),
            [
                x
                for x, y in self.rev_inputs.items()
                if y[0].startswith(f"{self.vm.vehicle_type}, ")
            ],
        ] = (
            self.array.sel(parameter="fuel cell power")
            * (1 + self.array.sel(parameter="fuel cell lifetime replacements"))
            * -1
        )

    def add_hydrogen_tank(self):
        hydro_tank_type = self.vm.energy_storage.get("hydrogen", {"tank type": "hdpe"})[
            "tank type"
        ]

        dict_tank_map = {
            "carbon fiber": "fuel tank assembly, compressed hydrogen gas, 700bar",
            "hdpe": "fuel tank, compressed hydrogen gas, 700bar, with HDPE liner",
            "aluminium": "fuel tank, compressed hydrogen gas, 700bar, with aluminium liner",
        }

        self.A[
            :,
            self.find_input_indices((dict_tank_map[hydro_tank_type],)),
            [
                x
                for x, y in self.rev_inputs.items()
                if y[0].startswith(f"{self.vm.vehicle_type}, ")
            ],
        ] = (
            self.array.sel(parameter="fuel tank mass")
            * (self.array.sel(parameter="fuel cell power") > 0)
            * -1
        )

    def add_battery(self):
        # Start of printout
        print(
            "****************** IMPORTANT BACKGROUND PARAMETERS ******************",
            end="\n * ",
        )

        # Energy storage
        print(f"The functional unit is: {self.func_unit}.", end="\n * ")
        print(f"The background prospective scenario is: {self.scenario}.", end="\n * ")
        print(f"The country of use is: {self.vm.country}.", end="\n * ")

        battery_tech = list(set(list(self.vm.energy_storage["electric"].values())))
        if len(battery_tech) == 0:
            battery_tech = ["NMC-622"]

        battery_origin = self.vm.energy_storage.get("origin", "CN")

        print(
            "Power and energy batteries produced "
            f"in {battery_origin} using {battery_tech} chemistry/ies",
            end="\n",
        )

        battery_acts = {
            "NMC-111": "market for battery, Li-ion, NMC111, rechargeable, prismatic",
            "NMC-523": "market for battery, Li-ion, NMC523",
            "NMC-622": "market for battery, Li-ion, NMC622",
            "NMC-811": "market for battery, Li-ion, NMC811, rechargeable, prismatic",
            "NMC-955": "market for battery, Li-ion, NMC955",
            "LFP": "market for battery, Li-ion, LFP, rechargeable, prismatic",
            "NCA": "market for battery, Li-ion, NCA, rechargeable, prismatic",
            "LTO": "market for battery, Li-ion, LTO",
            "Li-O2": "market for battery, Li-oxygen, Li-O2",
            "Li-S": "market for battery, Li-sulfur, Li-S",
            "SiB": "market for battery, Sodium-ion, SiB",
        }

        for key, val in self.vm.energy_storage["electric"].items():
            pwt, size, year = key
            if pwt.startswith("HEV"):
                pwt = " " + pwt
            self.A[
                :,
                self.find_input_indices((battery_acts[val],)),
                [
                    x
                    for x, y in self.rev_inputs.items()
                    if y[0].startswith(f"{self.vm.vehicle_type}, ")
                    and all(z in y[0] for z in (pwt, size))
                ],
                self.scope["year"].index(year),
            ] = (
                self.array.sel(
                    parameter="energy battery mass",
                    combined_dim=[
                        d
                        for d in self.array.coords["combined_dim"].values
                        if all(x in d for x in [pwt, size])
                    ],
                    year=year,
                )
                * (
                    1
                    + self.array.sel(
                        parameter="battery lifetime replacements",
                        combined_dim=[
                            d
                            for d in self.array.coords["combined_dim"].values
                            if all(x in d for x in [pwt, size])
                        ],
                        year=year,
                    )
                )
                * -1
            )

        # Battery EoL
        self.A[
            :,
            self.find_input_indices(("market for used Li-ion battery",)),
            [
                x
                for x, y in self.rev_inputs.items()
                if y[0].startswith(f"{self.vm.vehicle_type}, ")
            ],
        ] = self.array.sel(parameter="energy battery mass") * (
            1 + self.array.sel(parameter="battery lifetime replacements")
        )

    def add_cng_tank(self):
        self.A[
            :,
            self.find_input_indices(
                contains=("fuel tank assembly, compressed natural gas, 200 bar",)
            ),
            [
                x
                for x, y in self.rev_inputs.items()
                if y[0].startswith(f"{self.vm.vehicle_type}, ") and "ICEV-g" in y[0]
            ],
        ] = (
            self.array.sel(
                parameter="fuel tank mass",
                combined_dim=[
                    d for d in self.array.coords["combined_dim"].values if "ICEV-g" in d
                ],
            )
            * -1
        )

    def add_vehicle_to_transport_dataset(self):
        self.A[
            :,
            [
                x
                for x, y in self.rev_inputs.items()
                if y[0].startswith(f"{self.vm.vehicle_type}, ")
            ],
            [
                x
                for x, y in self.rev_inputs.items()
                if y[0].startswith(f"transport, {self.vm.vehicle_type}, ")
            ],
        ] = -1 / self.array.sel(parameter="lifetime kilometers")

    def display_renewable_rate_in_mix(self):
        for label in self.electricity_mix.combined_dim.values:
            for year in self.scope["year"]:
                mix = self.electricity_mix.sel(combined_dim=label, year=year).values
                renewable = (
                    mix[:, [3, 4, 5, 8, 9, 10, 11, 14, 18, 19]].sum(axis=1) * 100
                )
                hydro = mix[:, [0, 15]].sum(axis=1) * 100
                nuclear = mix[:, 1] * 100
                print(
                    f"\t * {label}, {year}, lifetime electricity shares across samples (%): "
                    f"non-hydro renew. {renewable.min():.0f}-{renewable.max():.0f}, "
                    f"hydro {hydro.min():.0f}-{hydro.max():.0f}, "
                    f"nuclear {nuclear.min():.0f}-{nuclear.max():.0f}."
                )

    def get_vehicle_supply_indices(self, name, columns):
        """Resolve the original or vehicle-specific supplier for each column."""
        (original,) = self.find_input_indices((name,), excludes=(" [for ",))
        mappings = getattr(self, "electricity_supply_indices", {})
        return [mappings.get(column, {}).get(original, original) for column in columns]

    def add_electricity_to_electric_vehicles(self) -> None:
        electric_powertrains = [
            "BEV",
            "BEV-opp",
            "BEV-motion",
            "BEV-depot",
            "PHEV-p",
            "PHEV-d",
        ]

        if any(True for x in electric_powertrains if x in self.scope["powertrain"]):
            columns = self.find_input_indices((f"transport, {self.vm.vehicle_type}, ",))
            rows = self.get_vehicle_supply_indices(
                "electricity supply for electric vehicles", columns
            )
            self.A[:, rows, columns, :] = -self.array.sel(
                parameter="electricity consumption"
            ).values

    def add_hydrogen_to_fuel_cell_vehicles(self) -> None:
        if "FCEV" in self.scope["powertrain"]:
            print(
                "{} is completed by {}.".format(
                    self.vm.fuel_blend["hydrogen"]["primary"]["type"],
                    self.vm.fuel_blend["hydrogen"]["secondary"]["type"],
                ),
                end="\n \t * ",
            )

            for y, year in enumerate(self.scope["year"]):
                if y + 1 == len(self.scope["year"]):
                    end_str = "\n * "
                else:
                    end_str = "\n \t * "

                print(
                    f"in {year} _________________________________________ "
                    f"{np.round(self.vm.fuel_blend['hydrogen']['secondary']['share'][y]* 100)}%",
                    end=end_str,
                )

            # Fuel supply
            columns = self.find_input_indices((f"transport, {self.vm.vehicle_type}, ",))
            rows = self.get_vehicle_supply_indices(
                "fuel supply for hydrogen vehicles", columns
            )
            self.A[:, rows, columns, :] = (
                self.array.sel(parameter="fuel consumption")
                * self.array.sel(parameter="fuel density per kg")
                * (self.array.sel(parameter="fuel cell power") > 0)
                * -1
            )

    def display_fuel_blend(self, fuel) -> None:
        print(
            "{} is completed by {}.".format(
                self.vm.fuel_blend[fuel]["primary"]["type"],
                self.vm.fuel_blend[fuel]["secondary"]["type"],
            ),
            end="\n \t * ",
        )

        for y, year in enumerate(self.scope["year"]):
            if y + 1 == len(self.scope["year"]):
                end_str = "\n * "
            else:
                end_str = "\n \t * "

            print(
                f"in {year} _________________________________________ {np.round(self.vm.fuel_blend[fuel]['secondary']['share'][y] * 100)}%",
                end=end_str,
            )

    def add_carbon_dioxide_emissions(
        self, powertrain_short, fossil_co2, biogenic_co2
    ) -> None:
        idx = [f"transport, {self.vm.vehicle_type}, ", powertrain_short]

        array_idx = [
            d for d in self.array.coords["combined_dim"].values if powertrain_short in d
        ]

        # Use the same burned fuel quantity as the fuel-supply exchange.
        # In a PHEV, fuel consumption is utility-factor weighted, whereas
        # fuel mass / combined range is not the fuel burned per driven km.
        burned_fuel = self.array.sel(
            parameter="fuel consumption", combined_dim=array_idx
        ) * self.array.sel(parameter="fuel density per kg", combined_dim=array_idx)
        columns = self.find_input_indices(contains=tuple(idx))
        for label, intensity in (
            ("fossil", fossil_co2),
            ("non-fossil", biogenic_co2),
        ):
            row = self.inputs[(f"Carbon dioxide, {label}", ("air",), "kilogram")]
            self.A[:, row, columns] = -burned_fuel * intensity

    def add_sulphur_emissions(self, fuel, powertrain_short, powertrains) -> None:
        # Fuel-based SO2 emissions
        # Sulfur concentration value for a given country, a given year, as concentration ratio

        sulfur_concentration = self.get_sulfur_content(self.vm.country, fuel)
        idx = [f"transport, {self.vm.vehicle_type}, ", powertrain_short]
        _ = lambda x: np.where(x == 0, 1, x)

        if sulfur_concentration:
            self.A[
                :,
                self.inputs[("Sulfur dioxide", ("air",), "kilogram")],
                self.find_input_indices(
                    contains=tuple(idx),
                    excludes=("BEV",),
                ),
            ] = (
                self.array.sel(
                    parameter="fuel mass",
                    combined_dim=[
                        d
                        for d in self.array.coords["combined_dim"].values
                        if any(x in d for x in powertrains)
                    ],
                )
                / _(
                    self.array.sel(
                        parameter=RANGE_PARAM[self.vm.vehicle_type],
                        combined_dim=[
                            d
                            for d in self.array.coords["combined_dim"].values
                            if any(x in d for x in powertrains)
                        ],
                    )
                )
                * -1
                * sulfur_concentration
                * (64 / 32)  # molar mass of SO2/molar mass of O2
            )

    def add_fuel_to_vehicles(self, fuel, powertrains, powertrains_short) -> None:
        if [i for i in self.scope["powertrain"] if i in powertrains]:
            (
                fuel_blend_fossil_CO2,
                fuel_blend_biogenic_CO2,
            ) = self.get_fuel_blend_carbon_intensity(fuel)

            self.display_fuel_blend(fuel)

            # Fuel supply
            columns = self.find_input_indices(
                contains=(f"transport, {self.vm.vehicle_type}, ", powertrains_short),
                excludes=("BEV",),
            )
            rows = self.get_vehicle_supply_indices(
                f"fuel supply for {fuel} vehicles", columns
            )
            self.A[:, rows, columns, :] = (
                (
                    self.array.sel(
                        parameter="fuel consumption",
                        combined_dim=[
                            d
                            for d in self.array.coords["combined_dim"].values
                            if any(x in d for x in powertrains)
                        ],
                    )
                    * self.array.sel(
                        parameter="fuel density per kg",
                        combined_dim=[
                            d
                            for d in self.array.coords["combined_dim"].values
                            if any(x in d for x in powertrains)
                        ],
                    )
                )
            ) * -1

            self.add_carbon_dioxide_emissions(
                powertrains_short,
                fuel_blend_fossil_CO2,
                fuel_blend_biogenic_CO2,
            )

            self.add_sulphur_emissions(fuel, powertrains_short, powertrains)

    def add_methane_leakage(self) -> None:
        """Account for additional non-exhaust methane loss in gas vehicles.

        The existing parameter is kg lost per kg of engine fuel, so purchased
        fuel = engine fuel * (1 + loss ratio). It covers losses additional to
        the selected fuel supplier; do not use a whole-chain loss estimate here
        if the same stages are already included upstream. See docs/methane_leakage.

        Generic air methane rows in gas transport columns hold this contribution.
        HBEFA exhaust flows have separate compartments and are left unchanged.
        Recomputing from engine fuel makes this method safe to call repeatedly.
        """
        if "ICEV-g" not in self.scope["powertrain"]:
            return

        labels = [f"{size} - ICEV-g" for size in self.scope["size"]]
        columns = self.find_input_indices(
            (f"transport, {self.vm.vehicle_type}, ICEV-g, ",)
        )
        markets = self.get_vehicle_supply_indices(
            "fuel supply for methane vehicles", columns
        )
        selected = self.array.sel(combined_dim=labels)
        rates = selected.sel(parameter="CNG pump-to-tank leakage").transpose(
            "value", "combined_dim", "year"
        )
        active = (
            selected.sel(parameter="TtW energy")
            .transpose("value", "combined_dim", "year")
            .values
            > 0
        )
        invalid = active & (~np.isfinite(rates.values) | (rates.values < 0))
        if invalid.any():
            first = np.argwhere(invalid)[0]
            coordinates = {
                dim: rates.coords[dim].values[index]
                for dim, index in zip(rates.dims, first)
            }
            raise ValueError(
                "CNG pump-to-tank leakage must be finite and nonnegative "
                f"(kg lost/kg engine fuel); invalid value at {coordinates}."
            )

        non_fossil_share = np.zeros(len(self.scope["year"]))
        for role, component in self.vm.fuel_blend["methane"].items():
            try:
                fraction = np.broadcast_to(
                    np.asarray(component["biogenic share"], dtype=float),
                    non_fossil_share.shape,
                )
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Methane {role} biogenic share must be numeric and scalar "
                    "or have one entry per year."
                ) from error
            if not np.all(np.isfinite(fraction) & (fraction >= 0) & (fraction <= 1)):
                raise ValueError(
                    f"Methane {role} biogenic share must be finite and within [0, 1]."
                )
            non_fossil_share += component["share"] * fraction

        engine_fuel = (
            (
                selected.sel(parameter="fuel consumption")
                * selected.sel(parameter="fuel density per kg")
            )
            .transpose("value", "combined_dim", "year")
            .values.astype(float)
        )
        engine_fuel = np.where(active, engine_fuel, 0)
        lost = engine_fuel * np.where(active, rates.values, 0)
        self.A[:, markets, columns, :] = -(engine_fuel + lost)
        for origin, share in (
            ("fossil", 1 - non_fossil_share),
            ("non-fossil", non_fossil_share),
        ):
            row = self.inputs[(f"Methane, {origin}", ("air",), "kilogram")]
            self.A[:, row, columns, :] = -lost * share

    def add_road_maintenance(self) -> None:
        # Infrastructure maintenance
        self.A[
            :,
            self.find_input_indices(("market for road maintenance",)),
            self.find_input_indices((f"transport, {self.vm.vehicle_type}, ",)),
        ] = (
            1.29e-3 * -1
        )

    def add_road_construction(self) -> None:
        # Infrastructure
        self.A[
            :,
            self.find_input_indices(
                contains=("market for road",), excludes=("maintenance", "wear")
            ),
            self.find_input_indices((f"transport, {self.vm.vehicle_type}, ",)),
        ] = (
            5.37e-7 * self.array.sel(parameter="driving mass") * -1
        )

    def add_exhaust_emissions(self) -> None:
        columns = self.find_input_indices((f"transport, {self.vm.vehicle_type}, ",))
        for flow, parameters in self.exhaust_emissions.items():
            names = [parameters] if isinstance(parameters, str) else list(parameters)
            emissions = self.array.sel(parameter=names).sum("parameter")
            self.A[:, self.inputs[flow], columns, :] = -emissions.transpose(
                "value", "combined_dim", "year"
            ).values

    def add_noise_emissions(self) -> None:
        # Noise emissions
        self.A[
            np.ix_(
                np.arange(self.iterations),
                [self.inputs[i] for i in self.noise_emissions],
                self.find_input_indices((f"transport, {self.vm.vehicle_type}, ",)),
            )
        ] = (
            self.array.sel(parameter=list(self.noise_emissions.values())) * -1
        ).transpose(
            "value", "parameter", "combined_dim", "year"
        )

    def add_refrigerant_emissions(self) -> None:
        # Emissions of air conditioner refrigerant r134a
        # Leakage assumed to amount to 53g according to
        # https://treeze.ch/fileadmin/user_upload/downloads/Publications/Case_Studies/Mobility/544-LCI-Road-NonRoad-Transport-Services-v2.0.pdf
        # but only to cars with an AC system (meaning, with a cooling energy consumption)
        # and only for vehicles before 2022

        loss_rate = {
            "car": 0.75,
            "bus": 16,
            "truck": 0.94,
        }

        refill_rate = {
            "car": 0.55,
            "bus": 7.5,
            "truck": 1.1,
        }

        self.A[
            :,
            self.inputs[("1,1,1,2-Tetrafluoroethane", ("air",), "kilogram")],
            self.find_input_indices((f"transport, {self.vm.vehicle_type}, ",)),
        ] = (
            loss_rate[self.vm.vehicle_type]
            / self.array.sel(parameter="lifetime kilometers")
            * (self.array.sel(parameter="cooling energy consumption") > 0)
            * (np.array(self.scope["year"]) < 2022)
            * -1
        )

        self.A[
            :,
            self.find_input_indices(("market for refrigerant R134a",)),
            self.find_input_indices((f"transport, {self.vm.vehicle_type}, ",)),
        ] = (
            (
                (loss_rate[self.vm.vehicle_type] + refill_rate[self.vm.vehicle_type])
                / self.array.sel(parameter="lifetime kilometers")
                * -1
            )
            * (self.array.sel(parameter="cooling energy consumption") > 0)
            * (np.array(self.scope["year"]) < 2022)
        )

    def add_abrasion_emissions(self) -> None:
        # Non-exhaust emissions

        abrasion_datasets = {
            (
                "road wear",
                "two-wheeler",
            ): "treatment of road wear emissions, passenger car",
            (
                "brake wear",
                "two-wheeler",
            ): "treatment of brake wear emissions, passenger car",
            (
                "tire wear",
                "two-wheeler",
            ): "treatment of tyre wear emissions, passenger car",
            ("road wear", "car"): "treatment of road wear emissions, passenger car",
            ("brake wear", "car"): "treatment of brake wear emissions, passenger car",
            ("tire wear", "car"): "treatment of tyre wear emissions, passenger car",
            ("road wear", "truck"): "treatment of road wear emissions, lorry",
            ("brake wear", "truck"): "treatment of brake wear emissions, lorry",
            ("tire wear", "truck"): "treatment of tyre wear emissions, lorry",
            ("road wear", "bus"): "treatment of road wear emissions, lorry",
            ("brake wear", "bus"): "treatment of brake wear emissions, lorry",
            ("tire wear", "bus"): "treatment of tyre wear emissions, lorry",
        }
        # Road wear emissions + 33.3% of re-suspended road dust
        self.A[
            :,
            self.find_input_indices(
                (abrasion_datasets[("road wear", self.vm.vehicle_type)],)
            ),
            self.find_input_indices((f"transport, {self.vm.vehicle_type}, ",)),
        ] = self.array.sel(parameter="road wear emissions") + (
            0.333 * self.array.sel(parameter="road dust emissions")
        )

        self.A[
            :,
            self.find_input_indices(
                (abrasion_datasets[("tire wear", self.vm.vehicle_type)],)
            ),
            self.find_input_indices((f"transport, {self.vm.vehicle_type}, ",)),
        ] = self.array.sel(parameter="tire wear emissions") + (
            0.333 * self.array.sel(parameter="road dust emissions")
        )

        # Brake wear emissions
        # BEVs only emit 20% of what a combustion engine vehicle emit according to
        # https://link.springer.com/article/10.1007/s11367-014-0792-4

        self.A[
            :,
            self.find_input_indices(
                (abrasion_datasets[("brake wear", self.vm.vehicle_type)],)
            ),
            self.find_input_indices((f"transport, {self.vm.vehicle_type}, ",)),
        ] = self.array.sel(parameter="brake wear emissions") + (
            0.333 * self.array.sel(parameter="road dust emissions")
        )

    def remove_non_compliant_vehicles(self):
        """
        Remove vehicles from self.A that do not have a TtW energy superior to 0.
        """
        # Get the indices of the vehicles that are not compliant
        self.A = np.nan_to_num(self.A)
        idx = [
            x
            for x, y in self.rev_inputs.items()
            if y[0].startswith(f"{self.vm.vehicle_type}, ")
        ]

        self.A[
            :,
            :,
            idx,
        ] *= (self.array.sel(parameter=["TtW energy"]) > 0).values
        self.A[:, idx, idx] = 1

        idx = self.find_input_indices((f"transport, {self.vm.vehicle_type}, ",))

        self.A[
            :,
            :,
            idx,
        ] *= (self.array.sel(parameter=["TtW energy"]) > 0).values
        self.A[:, idx, idx] = 1

    def change_functional_unit(self) -> None:
        """Convert this inventory once. Exports call this on a private copy."""
        if (
            self.func_unit == "vkm"
            or getattr(self, "_converted_func_unit", None) == self.func_unit
        ):
            return
        if getattr(self, "_converted_func_unit", None) is not None:
            raise ValueError(
                "Use a fresh inventory when changing an already converted functional unit."
            )
        factor = self.get_load_factor()[0, :, :, :, 0, :]
        factor = factor.transpose(3, 0, 1, 2).reshape(
            self.iterations, -1, len(self.scope["year"])
        )
        indices = self.find_input_indices((f"transport, {self.vm.vehicle_type}, ",))
        others = [i for i in range(self.A.shape[1]) if i not in indices]
        self.A[np.ix_(np.arange(self.iterations), others, indices)] /= factor[
            :, None, :, :
        ]
        new_inputs = {}
        for key, value in self.inputs.items():
            if key[0].startswith(f"transport, {self.vm.vehicle_type}, "):
                unit = {"pkm": "passenger kilometer", "tkm": "ton kilometer"}[
                    self.func_unit
                ]
                key = (*key[:2], unit, *key[3:])
            new_inputs[key] = value
        self.inputs = new_inputs
        self.rev_inputs = {value: key for key, value in new_inputs.items()}
        self._converted_func_unit = self.func_unit

    def export_lci(
        self,
        ecoinvent_version="3.10",
        filename=f"carculator_lci",
        directory=None,
        software="brightway2",
        format="bw2io",
    ):
        """
        Export the inventory. Can export to Simapro (as csv), or brightway2 (as bw2io object, file or string).
        :param db_name:
        :param ecoinvent_version: str. "3.9" or "3.10"
        :param filename: str. Name of the file to be exported
        :param directory: str. Directory where the file is saved
        :param software: str. "brightway2" or "simapro"
        :param format: str. "bw2io" or "file" or "string"
        ::return: inventory, or the filepath where the file is saved.
        :rtype: list
        """

        if ecoinvent_version not in ["3.9", "3.10"]:
            raise ValueError("ecoinvent_version must be either '3.9' or '3.10'")

        if software not in ("brightway2", "simapro"):
            raise ValueError("software must be 'brightway2' or 'simapro'.")
        if format not in ("file", "string", "bw2io") or (
            software == "simapro" and format == "bw2io"
        ):
            raise ValueError("Unsupported inventory export format for this software.")
        export = copy(self)
        export.A = self.A.copy()
        export.inputs = self.inputs.copy()
        export.rev_inputs = self.rev_inputs.copy()
        export.change_functional_unit()

        from .export import ExportInventory

        lci = ExportInventory(
            array=export.A,
            vehicle_model=self.vm,
            indices=export.rev_inputs,
            db_name=f"{filename}_{self.vm.vehicle_type}_{datetime.now().strftime('%Y%m%d')}",
        )

        provenance = getattr(self, "electricity_provenance", {})
        if provenance:
            comment = "; ".join(f"{key}: {value}" for key, value in provenance.items())
            for key in export.inputs:
                if key[0].startswith("electricity supply for"):
                    lci.references[key[0]] = {
                        "source": provenance.get(
                            "history_source", provenance["electricity_scenario"]
                        ),
                        "comment": comment,
                    }

        for scoped, original in getattr(
            self, "electricity_supply_originals", {}
        ).items():
            source_name = export.rev_inputs[original][0]
            if source_name in lci.references:
                lci.references[export.rev_inputs[scoped][0]] = lci.references[
                    source_name
                ]

        if software == "brightway2":
            return lci.write_bw2_lci(
                ecoinvent_version=ecoinvent_version,
                directory=directory,
                filename=f"{filename}_{self.vm.vehicle_type}_{datetime.now().strftime('%Y%m%d')}",
                export_format=format,
            )

        else:
            return lci.write_simapro_lci(
                ecoinvent_version=ecoinvent_version,
                directory=directory,
                filename=f"{filename}_{self.vm.vehicle_type}_{datetime.now().strftime('%Y%m%d')}",
                export_format=format,
            )
