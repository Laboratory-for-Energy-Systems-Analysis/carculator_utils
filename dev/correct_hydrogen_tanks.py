"""Apply sourced dry-mass and electricity-unit corrections to two tank recipes.

This is a build-time correction, shared by the full compiler and the targeted
bundle update. Source data and the chosen boundary live in the packaged JSON.
Unknown upstream recipes fail instead of being silently overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import sparse

RESOURCE = "hydrogen_tank_corrections.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def corrected_matrix(matrix, labels, specification):
    """Return a private corrected A and provenance; preserve row ordering."""
    if len(set(labels)) != len(labels):
        raise ValueError("Matrix labels must be unique")
    if matrix.shape != (len(labels), len(labels)):
        raise ValueError("A and labels must have matching dimensions")
    positions = {label: index for index, label in enumerate(labels)}

    def position(label):
        key = tuple(label)
        if key not in positions:
            raise LookupError(f"Missing tank correction label: {key}")
        return positions[key]

    suppliers = specification["suppliers"]
    result = matrix.astype(np.float64).tolil(copy=True)
    records = []
    for recipe in specification["recipes"]:
        column = position(recipe["label"])
        materials = {
            key: sum(amounts) for key, amounts in recipe["materials_kg"].items()
        }
        dry_mass = sum(materials.values())
        if not np.isclose(dry_mass, recipe["dry_material_mass_kg"], rtol=0, atol=1e-9):
            raise ValueError(f"Inconsistent dry material mass: {recipe['label']}")
        dry_mass = recipe["dry_material_mass_kg"]
        amounts = {**materials, **recipe["processing_kg"]}
        if materials.keys() & recipe["processing_kg"].keys():
            raise ValueError("Processing services must be separate from materials")
        amounts["electricity"] = recipe["electricity_MJ"]
        denominator = recipe["legacy_denominator_kg"]
        if not all(
            np.isfinite(x) and x > 0 for x in [dry_mass, denominator, *amounts.values()]
        ):
            raise ValueError("Tank recipe amounts must be finite and positive")
        old = np.zeros(len(labels))
        new = np.zeros(len(labels))
        old[column] = new[column] = 1
        used = {column}
        for key, amount in amounts.items():
            row = position(suppliers[key])
            if row in used:
                raise ValueError("Tank suppliers must have distinct labels")
            used.add(row)
            expected_unit = "kilowatt hour" if key == "electricity" else "kilogram"
            if suppliers[key][2] != expected_unit:
                raise ValueError(f"Unexpected supplier unit: {key}")
            old[row] = -amount / denominator
            new[row] = -amount / dry_mass / (3.6 if key == "electricity" else 1)
        observed = matrix[:, column].toarray().ravel()
        # Brightway can serialize either source recipe as float32. Recognize
        # both states, then retain the source-derived float64 coefficients.
        if not (
            np.allclose(observed, old, rtol=1e-7, atol=0)
            or np.allclose(observed, new, rtol=1e-7, atol=0)
        ):
            raise ValueError(f"Unrecognized upstream tank recipe: {recipe['label']}")
        result[:, column] = new.reshape(-1, 1)
        records.append(
            {
                "label": recipe["label"],
                "dry_material_mass_kg": dry_mass,
                "legacy_material_kg_per_kg": dry_mass / denominator,
                "corrected_material_kg_per_kg": 1.0,
                "legacy_electricity_kWh_per_kg": recipe["electricity_MJ"] / denominator,
                "corrected_electricity_kWh_per_kg": recipe["electricity_MJ"]
                / 3.6
                / dry_mass,
            }
        )
    return result.asformat(matrix.format), {
        "id": specification["id"],
        "source_resource": RESOURCE,
        "recipes": records,
    }


def update_bundle(directory):
    """Correct an existing, hash-verified bundle without rebuilding its B files."""
    from iam_matrix_tools import load_labels

    manifest_path = directory / "build_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for name, expected in manifest["resource_hashes"].items():
        if digest(directory / name) != expected:
            raise ValueError(f"Resource hash mismatch before correction: {name}")
    labels = load_labels(directory / "dict_inputs_A_matrix.csv")
    specification = json.loads((directory / RESOURCE).read_text())
    matrix, provenance = corrected_matrix(
        sparse.load_npz(directory / "A_matrix.npz"), labels, specification
    )
    columns = [labels.index(tuple(row["label"])) for row in specification["recipes"]]
    for path in directory.glob("B_matrix_*.npz"):
        if sparse.load_npz(path)[:, columns].nnz:
            raise ValueError(f"Tank foreground must have zero B coefficients: {path}")
    corrections = manifest.setdefault("foreground_corrections", {})
    prior = corrections.get("hydrogen_tanks", {})
    provenance["source_A_sha256"] = prior.get(
        "source_A_sha256", digest(directory / "A_matrix.npz")
    )
    corrections["hydrogen_tanks"] = provenance
    temporary = directory / "A_matrix.corrected.npz"
    sparse.save_npz(temporary, matrix)
    temporary.replace(directory / "A_matrix.npz")
    manifest["A_nonzero"] = matrix.nnz
    for name in ("A_matrix.npz", RESOURCE):
        manifest["resource_hashes"][name] = digest(directory / name)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iam-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(update_bundle(args.iam_dir), indent=2))


if __name__ == "__main__":
    main()
