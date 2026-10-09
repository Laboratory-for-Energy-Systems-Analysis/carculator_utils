"""Pure helpers for strict, reproducible foreground/background matrix builds."""

from __future__ import annotations

import ast
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import sparse

UNIT_ALIASES = {
    "kg": "kilogram",
    "m3": "cubic meter",
    "m2": "square meter",
    "metric ton*km": "ton kilometer",
    "person*km": "person kilometer",
    "km": "kilometer",
    "mj": "megajoule",
    "kwh": "kilowatt hour",
    "h": "hour",
    "m": "meter",
    "ha": "hectare",
    "a": "year",
}


def unit(value: str) -> str:
    return UNIT_ALIASES.get(value.lower(), value)


def activity_label(record: dict) -> tuple:
    return (
        record["name"],
        record["location"],
        unit(record["unit"]),
        record.get("reference product", record.get("product")),
    )


def flow_label(record: dict) -> tuple:
    return (record["name"], tuple(record["categories"]), unit(record["unit"]))


def load_labels(path: Path) -> list[tuple]:
    labels = []
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.reader(stream, delimiter=";"):
            if len(row) == 4:
                label = tuple(row)
            elif len(row) == 3:
                label = (row[0], ast.literal_eval(row[1]), row[2])
                if not isinstance(label[1], tuple):
                    raise ValueError(f"Invalid biosphere compartment: {label}")
            else:
                raise ValueError(f"Invalid matrix label: {row}")
            if label in labels:
                raise ValueError(f"Duplicate matrix label: {label}")
            labels.append(label)
    return labels


def save_labels(path: Path, labels: list[tuple]) -> None:
    if len(labels) != len(set(labels)):
        raise ValueError("Matrix labels must be unique")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter=";", lineterminator="\n")
        writer.writerows(labels)


def foreground_columns(matrix: sparse.spmatrix) -> list[int]:
    """Identify legacy expanded activities, retaining non-unit production."""
    off_diagonal = matrix.tocsc(copy=True)
    off_diagonal.setdiag(0)
    off_diagonal.eliminate_zeros()
    return np.flatnonzero(np.diff(off_diagonal.indptr)).tolist()


def load_migrations(paths: list[Path]) -> list[dict]:
    """Load attributed ecoinvent replacement/disaggregation metadata in order."""
    chain = []
    for path in paths:
        source = json.loads(path.read_text())
        rules = {}
        for entries, split in (
            (source.get("replace", []), False),
            (source.get("disaggregate", []), True),
        ):
            for entry in entries:
                key = activity_label(entry["source"])
                targets = entry["targets"] if split else [entry["target"]]
                result = [
                    (activity_label(target), float(target.get("allocation", 1)))
                    for target in targets
                ]
                if not result or any(not np.isfinite(w) or w < 0 for _, w in result):
                    raise ValueError(f"Invalid migration weights for {key}")
                if not np.isclose(sum(w for _, w in result), 1, atol=1e-6, rtol=0):
                    raise ValueError(f"Migration weights do not conserve output: {key}")
                if any(target[2] != key[2] for target, _ in result):
                    raise ValueError(f"Migration needs explicit unit conversion: {key}")
                if key in rules and rules[key] != result:
                    # Some published migration files contain competing targets.
                    # Keep an explicit ambiguity instead of taking the last row.
                    rules[key] = None
                else:
                    rules[key] = result
        chain.append({"source": path.name, "rules": rules})
    return chain


def migrate(label: tuple, chain: list[dict]) -> tuple[list[tuple], list[str]]:
    result = {label: 1.0}
    sources = []
    for step in chain:
        revised = defaultdict(float)
        used = False
        for key, weight in result.items():
            if key in step["rules"]:
                used = True
            if key in step["rules"] and step["rules"][key] is None:
                raise LookupError(
                    f"Conflicting migration rules in {step['source']}: {key}"
                )
            for target, fraction in step["rules"].get(key, [(key, 1.0)]):
                revised[target] += weight * fraction
        if used:
            sources.append(step["source"])
        result = dict(revised)
    return list(result.items()), sources


def resolve_activity(label: tuple, index: dict, chain: list[dict], overrides=None):
    """Return unique exact suppliers or an explicit, complete migration recipe."""
    if label in index:
        targets, sources = [(label, 1.0)], []
    elif overrides and label in overrides:
        override = overrides[label]
        if not override.get("reason") or not override.get("source"):
            raise ValueError(f"An override needs its reason and source: {label}")
        targets = [
            (tuple(item["label"]), float(item["weight"]))
            for item in override["targets"]
        ]
        sources = [override["source"]]
    else:
        targets, sources = migrate(label, chain)
    missing = [key for key, _ in targets if key not in index]
    ambiguous = [key for key, _ in targets if key in index and len(index[key]) != 1]
    if missing or ambiguous:
        raise LookupError({"label": label, "missing": missing, "ambiguous": ambiguous})
    if (
        not targets
        or not np.isclose(sum(w for _, w in targets), 1, atol=1e-6, rtol=0)
        or any(not np.isfinite(w) or w < 0 or key[2] != label[2] for key, w in targets)
    ):
        raise ValueError(f"Invalid supplier recipe for {label}")
    return targets, sources


def assemble_matrix(
    labels: list[tuple], recipes: dict[int, list[tuple]]
) -> sparse.csr_matrix:
    """Assemble A with source production signs and additive duplicate exchanges.

    Recipes contain (row label, exchange type, amount). Biosphere pseudo-products
    and aggregated background suppliers have identity columns. Expanded activity
    columns must explicitly declare nonzero reference production.
    """
    index = {label: i for i, label in enumerate(labels)}
    if len(index) != len(labels):
        raise ValueError("Duplicate matrix labels")
    amounts = defaultdict(float)
    for i in range(len(labels)):
        if i not in recipes:
            amounts[i, i] = 1.0
    for column, exchanges in recipes.items():
        reference = 0.0
        for label, kind, amount in exchanges:
            if label not in index:
                raise LookupError(f"Unresolved exchange in {labels[column]}: {label}")
            if kind not in {"production", "technosphere", "biosphere", "substitution"}:
                raise ValueError(f"Unknown exchange type {kind!r}")
            if not np.isfinite(amount):
                raise ValueError(f"Nonfinite exchange in {labels[column]}: {label}")
            row = index[label]
            sign = 1 if kind in {"production", "substitution"} else -1
            amounts[row, column] += sign * amount
            if kind == "production":
                if row != column:
                    raise ValueError(
                        f"Unallocated secondary production in {labels[column]}"
                    )
                reference += amount
        if reference == 0:
            raise ValueError(f"Missing/zero reference production in {labels[column]}")
    rows, columns, values = zip(*((r, c, v) for (r, c), v in amounts.items() if v != 0))
    return sparse.csr_matrix(
        (values, (rows, columns)), shape=(len(labels), len(labels))
    )
