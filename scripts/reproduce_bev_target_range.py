"""Reproduce BEV chemistry/target-range coupling on completed passenger-car runs.

The diagnostic energy recalculation freezes the final reported vehicle; it is
not an iterative sizing fix or a supported workaround.
"""

import argparse
import hashlib
import inspect
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from carculator import CarInputParameters, CarModel, fill_xarray_from_input_parameters
from carculator_utils.energy_consumption import EnergyConsumptionModel
from carculator_utils.model import VehicleModel


def reproduce(output):
    """Write model outputs and a frozen-vehicle energy consistency check."""
    rows = []
    for year in [2020, 2025]:
        ip = CarInputParameters()
        ip.static()
        _, array = fill_xarray_from_input_parameters(
            ip, scope={"size": ["Medium"], "powertrain": ["BEV"], "year": [year]}
        )
        for chemistry in ["LFP", "NMC-111", "NMC-622", "NMC-811"]:
            for target in [None, 400]:
                key = ("BEV", "Medium", year)
                model = CarModel(
                    array,
                    cycle="WLTC",
                    energy_storage={"electric": {key: chemistry}},
                    target_range={key: target} if target else None,
                )
                masses = []
                original = EnergyConsumptionModel.motive_energy_per_km

                def capture(self, *args, **kwargs):
                    masses.append(float(kwargs["driving_mass"].values.item()))
                    return original(self, *args, **kwargs)

                with patch.object(
                    EnergyConsumptionModel, "motive_energy_per_km", capture
                ):
                    model.set_all()
                row = {
                    "year": year,
                    "chemistry": chemistry,
                    "target_km": target,
                    "energy_calculation_mass_kg": masses[-1],
                }
                for parameter in [
                    "driving mass",
                    "curb mass",
                    "energy battery mass",
                    "battery cell energy density",
                    "electric energy stored",
                    "range",
                    "TtW energy",
                    "electricity consumption",
                ]:
                    row[parameter] = float(model[parameter].values.item())
                diagnostic = deepcopy(model)
                diagnostic.calculate_ttw_energy()
                diagnostic.set_range()
                row["recomputed_TtW_energy_kJ_km"] = float(
                    diagnostic["TtW energy"].values.item()
                )
                row["recomputed_range_km"] = float(diagnostic["range"].values.item())
                rows.append(row)
    sources = [
        Path(inspect.getfile(CarModel)),
        Path(inspect.getfile(VehicleModel)),
        Path(inspect.getfile(CarModel)).parent / "data/default_parameters.json",
    ]
    report = {
        "configuration": "Medium BEV, WLTC, static inputs; four chemistries, 2020/2025; default and 400 km target",
        "source_sha256": {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
        },
        "runs": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    for row in rows:
        if row["target_km"]:
            print(row)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    reproduce(parser.parse_args().output)
