"""Compare corrected tank LCIA with a saved legacy A and check vehicle exports.

Uses bundled EF midpoint / SSP2-NPi coefficients; no Brightway database needed.
The old A must have the current index and differ only in the two tank columns.
"""

import argparse
import contextlib
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import numpy as np
from carculator import CarInputParameters, CarModel, InventoryCar
from scipy import sparse
from scipy.sparse.linalg import spsolve

from carculator_utils import DATA_DIR
from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.inventory import get_dict_input


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(old_path):
    folder = DATA_DIR / "IAM"
    specification = json.loads((folder / "hydrogen_tank_corrections.json").read_text())
    inputs = get_dict_input()
    old = sparse.load_npz(old_path)
    new = sparse.load_npz(folder / "A_matrix.npz")
    columns = [inputs[tuple(row["label"])] for row in specification["recipes"]]
    assert set((old - new).nonzero()[1]) == set(columns)
    report = {
        "old_A_sha256": digest(old_path),
        "corrected_A_sha256": digest(folder / "A_matrix.npz"),
        "boundary": "2025 Medium FCEV, GLO, WLTC, default inputs; EF midpoint climate change; SSP2-NPi; per vkm",
        "cases": [],
    }
    for tank_type, recipe in zip(["hdpe", "aluminium"], specification["recipes"]):
        parameters = CarInputParameters()
        parameters.static()
        _, array = fill_xarray_from_input_parameters(
            parameters,
            scope={"size": ["Medium"], "powertrain": ["FCEV"], "year": [2025]},
        )
        model = CarModel(
            array,
            country="GLO",
            cycle="WLTC",
            energy_storage={"hydrogen": {"tank type": tank_type}},
        )
        model.set_all()
        inventory = InventoryCar(model, method="ef", scenario="SSP2-NPi")
        before = deepcopy(inventory)
        for column in columns:
            before.A[:, : old.shape[0], column, :] = (
                old[:, column].toarray().ravel()[None, :, None]
            )
        scores = [
            float(inv.calculate_impacts().sel(impact_category="climate change").sum())
            for inv in (before, inventory)
        ]
        demand = np.zeros(inventory.A.shape[1])
        demand[inputs[tuple(recipe["label"])]] = 1
        factors = inventory.B.sel(category="climate change").interp(year=2025).values
        unit_scores = [
            float(
                np.asarray(
                    factors @ spsolve(sparse.csc_matrix(inv.A[0, :, :, 0]), demand)
                ).item()
            )
            for inv in (before, inventory)
        ]
        mass = float(model["fuel tank mass"].item())
        lifetime = float(model["lifetime kilometers"].item())
        np.testing.assert_allclose(
            scores[1] - scores[0],
            mass / lifetime * (unit_scores[1] - unit_scores[0]),
            rtol=2e-5,
            atol=1e-10,
        )
        original = inventory.A.copy()
        export = inventory.export_lci(format="bw2io", ecoinvent_version="3.12")
        (tank,) = [d for d in export.data if d["name"] == recipe["label"][0]]
        assert "excluding stored hydrogen" in tank["comment"]
        suppliers = specification["suppliers"]
        material_names = {suppliers[key][0] for key in recipe["materials_kg"]}
        material_mass = sum(
            e["amount"]
            for e in tank["exchanges"]
            if e["type"] == "technosphere" and e["name"] in material_names
        )
        np.testing.assert_allclose(material_mass, 1, rtol=1e-12)
        np.testing.assert_array_equal(inventory.A, original)
        report["cases"].append(
            {
                "tank_type": tank_type,
                "tank_mass_kg": mass,
                "lifetime_km": lifetime,
                "old_tank_kg_CO2eq_per_kg": unit_scores[0],
                "corrected_tank_kg_CO2eq_per_kg": unit_scores[1],
                "old_vehicle_kg_CO2eq_per_vkm": scores[0],
                "corrected_vehicle_kg_CO2eq_per_vkm": scores[1],
                "change_g_CO2eq_per_vkm": 1000 * (scores[1] - scores[0]),
                "exported_material_kg_per_kg_tank": material_mass,
            }
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-a", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with (
        (args.output / "validation.log").open("w") as log,
        contextlib.redirect_stdout(log),
    ):
        report = validate(args.old_a)
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
