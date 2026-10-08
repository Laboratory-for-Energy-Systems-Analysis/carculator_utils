"""Assemble documented fuel-delivery activities without rewriting IAM matrices."""

import numpy as np
import yaml

from . import DATA_DIR


def load_fuel_supply_recipes():
    """Read foreground supplier recipes and their export provenance."""
    with (DATA_DIR / "fuel" / "supply_chains.yaml").open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def register_fuel_suppliers(inputs, fuel_blend):
    """Append selected suppliers; validate their bundled dependencies first.

    Selection uses the resolved supplier tuple, preserving explicit ``name``
    overrides. Only the inventory's private index is modified. Bundled indices
    remain unchanged so all existing A and B matrices keep their ordering.
    """
    selected = {
        tuple(component["name"])
        for blend in fuel_blend.values()
        for component in blend.values()
    }
    recipes = [
        recipe
        for recipe in load_fuel_supply_recipes()
        if tuple(recipe["name"]) in selected
    ]
    for recipe in recipes:
        dependencies = [recipe["template"]]
        for replacement in recipe["replacements"]:
            dependencies.extend([replacement["original"], replacement["supplier"]])
        for dependency in dependencies:
            if tuple(dependency) not in inputs:
                raise KeyError(
                    f"Fuel supplier {recipe['name'][0]!r} requires missing "
                    f"bundled activity {tuple(dependency)!r}."
                )
    for recipe in recipes:
        name = tuple(recipe["name"])
        if name not in inputs:
            inputs[name] = max(inputs.values()) + 1
    return recipes


def fill_fuel_suppliers(matrix, inputs, recipes):
    """Fill appended columns before fuel-preparation electricity is rewired.

    ``matrix`` has axes sample, product, activity, year. Recipe amounts are
    positive input quantities per unit output; matrix inputs are negative.
    """
    for recipe in recipes:
        column = inputs[tuple(recipe["name"])]
        template = inputs[tuple(recipe["template"])]
        matrix[:, :, column, :] = matrix[:, :, template, :]
        matrix[:, template, column, :] = 0
        matrix[:, column, column, :] = 1
        for replacement in recipe["replacements"]:
            original = inputs[tuple(replacement["original"])]
            supplier = inputs[tuple(replacement["supplier"])]
            original_amount = -matrix[:, original, column, :].copy()
            if not np.all(np.isfinite(original_amount) & (original_amount > 0)):
                raise ValueError(
                    f"Fuel supplier {recipe['name'][0]!r} requires a positive "
                    f"template input from {replacement['original'][0]!r}."
                )
            amount = replacement.get("amount", original_amount)
            matrix[:, original, column, :] = 0
            matrix[:, supplier, column, :] -= amount
