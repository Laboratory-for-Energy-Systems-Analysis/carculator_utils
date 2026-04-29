"""Update IAM B matrices from Brightway LCIA results.

This script regenerates the characterized emission factors stored in
``carculator_utils/data/IAM/B_matrix_*.npz`` using the Brightway project
``ecoinvent-3.12-cutoff``.

The update is intentionally conservative:

* activity columns are recalculated only when the activity exists in the
  original ``ecoinvent-3.12-cutoff`` database;
* scenario activities that are absent from the selected prospective database
  keep their previous values;
* direct elementary-flow columns are updated only when the flow is found in
  ``ecoinvent-3.12-biosphere``;
* custom noise rows without a Brightway method keep their previous values.

Run from the repository root with the Brightway-enabled environment:

    conda run -n premise python dev/update_iam_b_matrices.py --write
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import time
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

warnings.filterwarnings("ignore", message="pkg_resources is deprecated as an API.*")

import numpy as np
from scipy import sparse


PROJECT = "ecoinvent-3.12-cutoff"
STATIC_DB = "ecoinvent-3.12-cutoff"
BIOSPHERE_DB = "ecoinvent-3.12-biosphere"
DATABASE_PREFIX = "ecoinvent-3.12-cutoff-remind_"
METHOD_PREFIX = "ecoinvent-3.12"
YEARS = (2005, 2010, 2020, 2030, 2040, 2050)
HISTORICAL_YEARS = (2005, 2010, 2020)
OUTPUT_SCENARIOS = ("SSP2-NPi", "SSP2-PkBudg1000", "SSP2-PkBudg650")
LEGACY_INPUT_SCENARIOS = {
    # Used only as a fallback when regenerating from a checkout that still has
    # the pre-2026 scenario filenames.
    "SSP2-NPi": "SSP2-NPi",
    "SSP2-PkBudg1000": "SSP2-PkBudg1150",
    "SSP2-PkBudg650": "SSP2-PkBudg500",
}
MATRIX_GROUPS = (("ef", "midpoint"), ("recipe", "midpoint"), ("recipe", "endpoint"))


@dataclass(frozen=True)
class ImpactCategory:
    """One row from ``dict_impact_categories.csv``."""

    method: str
    indicator: str
    source: str
    category: str
    type: str
    abbreviation: str
    unit: str


@dataclass(frozen=True)
class MappedMethod:
    """A matrix row mapped to a Brightway method tuple."""

    group: tuple[str, str]
    row: int
    category: ImpactCategory
    brightway_method: tuple[str, ...] | None
    reason: str


def clean(value: str) -> str:
    """Normalize labels for exact matching against Brightway methods."""

    return value.strip()


def load_input_labels(path: Path) -> list[tuple]:
    labels = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter=";"):
            if len(row) == 3:
                labels.append((row[0], ast.literal_eval(row[1]), row[2]))
            elif len(row) == 4:
                labels.append(tuple(row))
            else:
                raise ValueError(f"Unexpected input label row: {row!r}")
    return labels


def load_impact_categories(path: Path) -> dict[tuple[str, str], list[ImpactCategory]]:
    categories: dict[tuple[str, str], list[ImpactCategory]] = defaultdict(list)
    with path.open(encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter=","):
            if len(row) != 7:
                raise ValueError(f"Unexpected LCIA category row: {row!r}")
            category = ImpactCategory(*row)
            categories[(category.method, category.indicator)].append(category)
    return categories


def scenario_database(scenario: str, year: int) -> str:
    if scenario == "SSP2-NPi" or year in HISTORICAL_YEARS:
        pathway = "SSP2-NPi"
    else:
        pathway = scenario
    return f"{DATABASE_PREFIX}{pathway}-{year}"


def existing_matrix_path(
    iam_dir: Path, method: str, indicator: str, scenario: str, year: int | None
) -> Path:
    current_path = output_matrix_path(iam_dir, method, indicator, scenario, year)
    if current_path.exists():
        return current_path

    if scenario == "static":
        return current_path

    legacy = LEGACY_INPUT_SCENARIOS[scenario]
    return iam_dir / f"B_matrix_{method}_{indicator}_remind_{legacy}_{year}.npz"


def output_matrix_path(
    iam_dir: Path, method: str, indicator: str, scenario: str, year: int | None
) -> Path:
    if scenario == "static":
        return iam_dir / f"B_matrix_{method}_{indicator}_static.npz"
    return iam_dir / f"B_matrix_{method}_{indicator}_remind_{scenario}_{year}.npz"


def build_activity_index(database_name: str):
    import bw2data as bd

    values: dict[tuple[str, str, str, str], object] = {}
    duplicates: set[tuple[str, str, str, str]] = set()
    for activity in bd.Database(database_name):
        key = (
            activity.get("name"),
            activity.get("location"),
            activity.get("unit"),
            activity.get("reference product"),
        )
        if key in values:
            duplicates.add(key)
        else:
            values[key] = activity

    for key in duplicates:
        values.pop(key, None)

    return values, duplicates


def build_biosphere_index():
    import bw2data as bd

    values: dict[tuple[str, tuple[str, ...], str], object] = {}
    duplicates: set[tuple[str, tuple[str, ...], str]] = set()
    for flow in bd.Database(BIOSPHERE_DB):
        key = (flow.get("name"), tuple(flow.get("categories") or ()), flow.get("unit"))
        if key in values:
            duplicates.add(key)
        else:
            values[key] = flow

    for key in duplicates:
        values.pop(key, None)

    return values, duplicates


def endpoint_method(
    category: ImpactCategory, available_methods: set[tuple[str, ...]]
) -> tuple[str, ...] | None:
    source = clean(category.source)
    category_name = clean(category.category)
    indicator = clean(category.type)
    exact = (METHOD_PREFIX, source, category_name, indicator)
    if exact in available_methods:
        return exact

    matches = [
        method
        for method in available_methods
        if len(method) == 4
        and method[0] == METHOD_PREFIX
        and method[1] == source
        and clean(method[3]) == category_name
    ]
    if len(matches) == 1:
        return matches[0]

    matches = [
        method
        for method in available_methods
        if len(method) == 4
        and method[0] == METHOD_PREFIX
        and method[1] == source
        and clean(method[2]) == category_name
        and clean(method[3]) == indicator
    ]
    if len(matches) == 1:
        return matches[0]

    return None


def map_category(
    category: ImpactCategory, available_methods: set[tuple[str, ...]]
) -> tuple[tuple[str, ...] | None, str]:
    source = clean(category.source)
    category_name = clean(category.category)
    indicator = clean(category.type)

    if source == "Cucurachi et al.":
        return None, "custom noise method not available in Brightway"

    if source == "EF v3.1":
        method = (METHOD_PREFIX, "EF v3.1", category_name, indicator)
    elif source == "IPCC 2021" and category_name == "climate change":
        method = (
            METHOD_PREFIX,
            "IPCC 2021",
            "climate change: total (excl. biogenic CO2)",
            "global warming potential (GWP100)",
        )
    elif source == "IPCC 2021" and category_name == "climate change w bio":
        method = (
            METHOD_PREFIX,
            "IPCC 2021 (incl. biogenic CO2)",
            "climate change: total (incl. biogenic CO2)",
            "global warming potential (GWP100)",
        )
    elif source == "ReCiPe 2016":
        if category_name == "energy resources depletion: non-renewable":
            method = (
                METHOD_PREFIX,
                "ReCiPe 2016 v1.03, midpoint (H)",
                "energy resources: non-renewable, fossil",
                "fossil fuel potential (FFP)",
            )
        else:
            method = (
                METHOD_PREFIX,
                "ReCiPe 2016 v1.03, midpoint (H)",
                category_name,
                indicator,
            )
    elif source == "Cumulative Energy Demand (CED)":
        method = (METHOD_PREFIX, source, category_name, indicator)
    elif source == "ReCiPe 2016 v1.03, endpoint (H)":
        method = endpoint_method(category, available_methods)
        if method is None:
            return None, "no endpoint method match"
    else:
        return None, f"unsupported source {source!r}"

    if method not in available_methods:
        return None, f"method not found: {method!r}"

    return method, "mapped"


def mapped_methods(
    categories: dict[tuple[str, str], list[ImpactCategory]],
    available_methods: set[tuple[str, ...]],
) -> list[MappedMethod]:
    mapped = []
    for group in MATRIX_GROUPS:
        for row, category in enumerate(categories[group]):
            method, reason = map_category(category, available_methods)
            mapped.append(MappedMethod(group, row, category, method, reason))
    return mapped


def load_existing_matrix(
    path: Path, expected_rows: int, expected_columns: int
) -> np.ndarray:
    matrix = sparse.load_npz(path).toarray()
    if matrix.shape[0] != expected_rows:
        raise ValueError(f"{path} has {matrix.shape[0]} rows; expected {expected_rows}")
    if matrix.shape[1] > expected_columns:
        raise ValueError(
            f"{path} has {matrix.shape[1]} columns; expected at most {expected_columns}"
        )
    if matrix.shape[1] == expected_columns:
        return matrix

    expanded = np.zeros((matrix.shape[0], expected_columns), dtype=matrix.dtype)
    expanded[:, : matrix.shape[1]] = matrix
    return expanded


def finite_or_zero(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    values[~np.isfinite(values)] = 0.0
    return values


def inventory_vector(inventory) -> np.ndarray:
    summed = inventory.sum(axis=1)
    try:
        return summed.A1
    except AttributeError:
        return np.asarray(summed).ravel()


def calculate_activity_scores(
    database_name: str,
    db_index: dict[tuple[str, str, str, str], object],
    eligible_activity_columns: list[int],
    labels: list[tuple],
    method_entries: list[MappedMethod],
    max_activities: int | None = None,
) -> tuple[dict[tuple[str, str], np.ndarray], list[int]]:
    import bw2calc as bc

    matched_columns = [
        column for column in eligible_activity_columns if labels[column] in db_index
    ]
    if max_activities is not None:
        matched_columns = matched_columns[:max_activities]

    shape_by_group = {
        group: (
            max(entry.row for entry in method_entries if entry.group == group) + 1,
            len(matched_columns),
        )
        for group in MATRIX_GROUPS
    }
    results = {
        group: np.full(shape, np.nan, dtype=float)
        for group, shape in shape_by_group.items()
    }

    entries = [entry for entry in method_entries if entry.brightway_method is not None]
    if not matched_columns or not entries:
        return results, matched_columns

    first_activity = db_index[labels[matched_columns[0]]]
    first_method = entries[0].brightway_method
    start = time.time()
    lca = bc.LCA({first_activity.id: 1}, first_method)
    lca.lci(factorize=True)
    lca.lcia()

    cf_vectors = np.zeros((len(entries), len(lca.dicts.biosphere)), dtype=float)
    for index, entry in enumerate(entries):
        if index == 0:
            # The first method is already loaded by ``lcia`` above.
            pass
        else:
            lca.switch_method(entry.brightway_method)
        cf_vectors[index, :] = lca.characterization_matrix.diagonal()

    print(
        f"  {database_name}: factorized in {time.time() - start:.1f}s; "
        f"scoring {len(matched_columns)} activities"
    )

    for activity_index, column in enumerate(matched_columns, start=1):
        activity = db_index[labels[column]]
        lca.redo_lci({activity.id: 1})
        scores = finite_or_zero(cf_vectors @ inventory_vector(lca.inventory))
        for method_index, entry in enumerate(entries):
            results[entry.group][entry.row, activity_index - 1] = scores[method_index]

        if activity_index % 100 == 0 or activity_index == len(matched_columns):
            print(f"    {activity_index}/{len(matched_columns)} activities")

    return results, matched_columns


def calculate_direct_factors(
    flow_columns: list[int],
    labels: list[tuple],
    flow_index: dict[tuple[str, tuple[str, ...], str], object],
    method_entries: list[MappedMethod],
) -> tuple[dict[tuple[str, str], np.ndarray], list[int]]:
    import bw2data as bd

    matched_columns = [
        column for column in flow_columns if labels[column] in flow_index
    ]
    shape_by_group = {
        group: (
            max(entry.row for entry in method_entries if entry.group == group) + 1,
            len(matched_columns),
        )
        for group in MATRIX_GROUPS
    }
    results = {
        group: np.full(shape, np.nan, dtype=float)
        for group, shape in shape_by_group.items()
    }

    cf_cache: dict[tuple[str, ...], dict[int, float]] = {}
    for entry in method_entries:
        if entry.brightway_method is None:
            continue
        if entry.brightway_method not in cf_cache:
            cf_cache[entry.brightway_method] = {
                int(flow_id): float(amount)
                for flow_id, amount in bd.Method(entry.brightway_method).load()
            }
        factors = cf_cache[entry.brightway_method]
        for index, column in enumerate(matched_columns):
            flow = flow_index[labels[column]]
            results[entry.group][entry.row, index] = factors.get(int(flow.id), 0.0)

    return results, matched_columns


def summarize_methods(method_entries: list[MappedMethod]) -> dict[str, int]:
    return dict(Counter(entry.reason for entry in method_entries))


def database_plan() -> dict[str, list[tuple[str, int | None]]]:
    plan: dict[str, list[tuple[str, int | None]]] = defaultdict(list)
    plan[STATIC_DB].append(("static", None))
    for scenario in OUTPUT_SCENARIOS:
        for year in YEARS:
            plan[scenario_database(scenario, year)].append((scenario, year))
    return dict(plan)


def write_report(path: Path, report: dict) -> None:
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write updated NPZ files")
    parser.add_argument(
        "--max-activities",
        type=int,
        default=None,
        help="debug limit for the number of matched activities scored per database",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("tmp/iam_b_matrix_update_report.json"),
        help="JSON report path",
    )
    args = parser.parse_args(argv)

    warnings.filterwarnings("ignore", message="pkg_resources is deprecated")
    try:
        from scikits.umfpack import UmfpackWarning

        warnings.filterwarnings("ignore", category=UmfpackWarning)
    except Exception:
        pass

    import bw2data as bd

    repo_root = Path(__file__).resolve().parents[1]
    data_dir = repo_root / "carculator_utils" / "data"
    iam_dir = data_dir / "IAM"
    labels = load_input_labels(iam_dir / "dict_inputs_A_matrix.csv")
    categories = load_impact_categories(
        data_dir / "lcia" / "dict_impact_categories.csv"
    )

    bd.projects.set_current(PROJECT)
    available_databases = set(bd.databases)
    available_methods = {tuple(method) for method in bd.methods}

    missing_databases = sorted(set(database_plan()) - available_databases)
    if missing_databases:
        raise ValueError(f"Missing Brightway databases: {missing_databases}")

    method_entries = mapped_methods(categories, available_methods)

    activity_columns = [index for index, label in enumerate(labels) if len(label) == 4]
    flow_columns = [index for index, label in enumerate(labels) if len(label) == 3]

    static_index, static_duplicates = build_activity_index(STATIC_DB)
    eligible_activity_columns = [
        column for column in activity_columns if labels[column] in static_index
    ]

    flow_index, flow_duplicates = build_biosphere_index()
    direct_scores, matched_flow_columns = calculate_direct_factors(
        flow_columns, labels, flow_index, method_entries
    )

    report = {
        "project": PROJECT,
        "activity_labels": len(activity_columns),
        "flow_labels": len(flow_columns),
        "static_activity_matches": len(eligible_activity_columns),
        "static_activity_missing_or_duplicate": len(activity_columns)
        - len(eligible_activity_columns),
        "static_duplicate_activity_keys": len(static_duplicates),
        "biosphere_flow_matches": len(matched_flow_columns),
        "biosphere_flow_missing_or_duplicate": len(flow_columns)
        - len(matched_flow_columns),
        "biosphere_duplicate_flow_keys": len(flow_duplicates),
        "method_mapping": summarize_methods(method_entries),
        "mapped_methods": [
            {
                "group": list(entry.group),
                "row": entry.row,
                "category": entry.category.category,
                "type": entry.category.type,
                "source": entry.category.source,
                "brightway_method": list(entry.brightway_method)
                if entry.brightway_method
                else None,
                "reason": entry.reason,
            }
            for entry in method_entries
        ],
        "databases": {},
        "files": [],
    }

    print(f"Project: {bd.projects.current}")
    print(
        f"Input labels: {len(activity_columns)} activities, {len(flow_columns)} flows"
    )
    print(
        "Static activity matches eligible for update: "
        f"{len(eligible_activity_columns)}/{len(activity_columns)}"
    )
    print(
        "Direct flow matches eligible for update: "
        f"{len(matched_flow_columns)}/{len(flow_columns)}"
    )
    print(f"Method mapping: {summarize_methods(method_entries)}")

    if not args.write:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        write_report(args.report, report)
        print(f"Dry run only. Report written to {args.report}")
        return 0

    scores_by_database: dict[
        str, tuple[dict[tuple[str, str], np.ndarray], list[int]]
    ] = {}
    for database_name in sorted(database_plan()):
        db_index, duplicates = build_activity_index(database_name)
        scores_by_database[database_name] = calculate_activity_scores(
            database_name,
            db_index,
            eligible_activity_columns,
            labels,
            method_entries,
            args.max_activities,
        )
        matched_columns = scores_by_database[database_name][1]
        report["databases"][database_name] = {
            "matched_activity_columns": len(matched_columns),
            "eligible_activity_columns": len(eligible_activity_columns),
            "missing_eligible_activity_columns": len(eligible_activity_columns)
            - len(matched_columns),
            "duplicate_activity_keys": len(duplicates),
        }

    for method, indicator in MATRIX_GROUPS:
        group = (method, indicator)
        row_count = len(categories[group])
        for scenario, year in [("static", None)] + [
            (scenario, year) for scenario in OUTPUT_SCENARIOS for year in YEARS
        ]:
            source_path = existing_matrix_path(
                iam_dir, method, indicator, scenario, year
            )
            target_path = output_matrix_path(iam_dir, method, indicator, scenario, year)
            matrix = load_existing_matrix(source_path, row_count, len(labels))

            rows_with_direct_scores = ~np.isnan(direct_scores[group]).all(axis=1)
            if matched_flow_columns and np.any(rows_with_direct_scores):
                matrix[
                    np.ix_(
                        np.flatnonzero(rows_with_direct_scores),
                        matched_flow_columns,
                    )
                ] = direct_scores[group][rows_with_direct_scores, :]

            database_name = (
                STATIC_DB if scenario == "static" else scenario_database(scenario, year)
            )
            activity_scores, matched_activity_columns = scores_by_database[
                database_name
            ]
            rows_with_activity_scores = ~np.isnan(activity_scores[group]).all(axis=1)
            if matched_activity_columns and np.any(rows_with_activity_scores):
                matrix[
                    np.ix_(
                        np.flatnonzero(rows_with_activity_scores),
                        matched_activity_columns,
                    )
                ] = activity_scores[group][rows_with_activity_scores, :]

            if not np.isfinite(matrix).all():
                bad = np.argwhere(~np.isfinite(matrix))
                raise ValueError(
                    f"Non-finite values in {target_path}: "
                    f"first bad index {bad[0].tolist()}"
                )

            sparse.save_npz(target_path, sparse.csr_matrix(matrix))
            report["files"].append(
                {
                    "source": str(source_path.relative_to(repo_root)),
                    "target": str(target_path.relative_to(repo_root)),
                    "database": database_name,
                    "rows": int(matrix.shape[0]),
                    "columns": int(matrix.shape[1]),
                    "direct_columns_updated": len(matched_flow_columns),
                    "activity_columns_updated": len(matched_activity_columns),
                }
            )
            print(f"Wrote {target_path.relative_to(repo_root)}")

    args.report.parent.mkdir(parents=True, exist_ok=True)
    write_report(args.report, report)
    print(f"Report written to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
