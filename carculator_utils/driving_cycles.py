"""
driving_cycles.py loads a driving_cycles based on
the name specific by the user.
The driving_cycles returned is a numpy
array with speed levels (in km/h) for each
second of driving.
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np
import yaml

from . import DATA_DIR

FILEPATH_DC_SPECS = DATA_DIR / "driving_cycles" / "dc_specs.yaml"


def get_source_cycle_durations(vehicle_type: str, name: str) -> dict:
    """Return verified one-second sample counts by size, excluding padding.

    Missing sizes have no verified source duration and retain the caller's
    legacy duration convention.
    """
    path = DATA_DIR / "driving_cycles" / "vecto_cycle_provenance.json"
    with path.open() as stream:
        records = json.load(stream)["records"]
    return {
        record["size"]: record["duration_seconds"]
        for record in records
        if record["vehicle_type"] == vehicle_type and record["cycle"] == name
    }


def detect_vehicle_type(vehicle_sizes: List[str]) -> str:
    """
    Detect the type of vehicle based on the size of the vehicle.
    """

    dc = get_driving_cycle_specs()

    for vehicle_type in dc["columns"]:
        for dc_name in dc["columns"][vehicle_type]:
            for size in dc["columns"][vehicle_type][dc_name]:
                if size in vehicle_sizes:
                    return vehicle_type

    raise ValueError("The vehicle size is not in the list of available vehicle sizes.")


def get_driving_cycle_specs() -> dict:
    """Get driving_cycles specifications.

    :returns: A dictionary with driving_cycles specifications.
    :rtype: dict

    """

    with open(FILEPATH_DC_SPECS, "r") as f:
        return yaml.safe_load(f)


def get_dc_column_number(
    vehicle_type: str, vehicle_size: List[str], dc_name: str
) -> List[int]:
    """
    Loads YAML file that contains the column number.
    Return the column number given a vehicle type and driving_cycles name.
    """

    dc_specs = get_driving_cycle_specs()

    if isinstance(vehicle_size, str):
        vehicle_size = [vehicle_size]

    if vehicle_type not in dc_specs["columns"]:
        raise KeyError(
            f"Vehicle type {vehicle_type} is not in the list of "
            f"available vehicle types: {list(dc_specs['columns'].keys())}"
        )

    if dc_name not in dc_specs["columns"][vehicle_type]:
        raise KeyError(
            f"Driving cycle {dc_name} is not in the list of "
            f"available driving cycles: {list(dc_specs['columns'][vehicle_type].keys())}"
        )

    if not all(
        vehicle in dc_specs["columns"][vehicle_type][dc_name]
        for vehicle in vehicle_size
    ):
        raise KeyError(
            f"Vehicle size(s) {vehicle_size} is not in the list of "
            f"available vehicle sizes: {list(dc_specs['columns'][vehicle_type][dc_name].keys())}"
        )

    return [dc_specs["columns"][vehicle_type][dc_name][s] for s in vehicle_size]


def get_data(
    filepath: Path, vehicle_type: str, vehicle_sizes: List[str], name: str
) -> np.ndarray:
    try:
        col = get_dc_column_number(vehicle_type, vehicle_sizes, name)
        arr = np.genfromtxt(filepath, delimiter=";")
        # we skip the headers
        dc = arr[1:, col]
        return dc

    except KeyError as err:
        print(err, "The specified driving_cycles could not be found.")
        raise


def get_standard_driving_cycle_and_gradient(
    vehicle_type: str, vehicle_sizes: List[str], name: str
) -> Tuple[np.ndarray, np.ndarray]:
    """Return bundled speed and road grade arrays, with one row per second.

    Speed is in km/h. Road grade is dimensionless rise/run, not degrees or
    radians. The energy model converts grade to angle using ``arctan``.
    Arrays can contain padding; source durations identify verified VECTO traces.

    :param name: The name of the driving_cycles.
    e.g., WLTC (Worldwide harmonized Light vehicles Test Cycles)
    :type name: str

    :returns: Speed and grade arrays with columns in requested size order.
    :rtype: tuple[numpy.ndarray, numpy.ndarray]

    """

    filepath_dc = DATA_DIR / "driving_cycles" / f"{vehicle_type}.csv"
    filepath_gradient = DATA_DIR / "gradient" / f"{vehicle_type}.csv"

    # definition of columns to select in the CSV file
    # each column corresponds to a size class
    # since the driving_cycles is simulated for each size class
    return (
        get_data(filepath_dc, vehicle_type, vehicle_sizes, name),
        get_data(filepath_gradient, vehicle_type, vehicle_sizes, name),
    )
