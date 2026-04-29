"""Compare current IAM B matrices against matrices from a previous git ref.

The default reference is ``HEAD~1``. To compare the current committed IAM
update against the values that preceded it in this branch, use
``--ref f6da67f^``. New scenario filenames are mapped back to the legacy names
so that:

* ``SSP2-PkBudg1000`` is compared with ``SSP2-PkBudg1150``;
* ``SSP2-PkBudg650`` is compared with ``SSP2-PkBudg500``.

Run from the repository root:

    python dev/compare_iam_b_matrices.py --ref HEAD~1
"""

from __future__ import annotations

import argparse
import ast
import csv
import io
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from scipy import sparse


SCENARIO_REPLACEMENTS = {
    "SSP2-PkBudg1000": "SSP2-PkBudg1150",
    "SSP2-PkBudg650": "SSP2-PkBudg500",
}
MATRIX_GROUPS = (("ef", "midpoint"), ("recipe", "midpoint"), ("recipe", "endpoint"))


@dataclass(frozen=True)
class MatrixInfo:
    """Information parsed from a B matrix filename."""

    method: str
    indicator: str
    scenario: str
    year: int | None


def parse_matrix_name(path: Path) -> MatrixInfo:
    parts = path.stem.split("_")
    if len(parts) < 5 or parts[:2] != ["B", "matrix"]:
        raise ValueError(f"Unexpected B matrix filename: {path.name}")

    method, indicator = parts[2], parts[3]
    if parts[4] == "static":
        return MatrixInfo(
            method=method, indicator=indicator, scenario="static", year=None
        )
    if len(parts) != 7 or parts[4] != "remind":
        raise ValueError(f"Unexpected scenario B matrix filename: {path.name}")
    return MatrixInfo(
        method=method,
        indicator=indicator,
        scenario=parts[5],
        year=int(parts[6]),
    )


def previous_matrix_path(current_path: Path) -> Path:
    previous_name = current_path.name
    for current, legacy in SCENARIO_REPLACEMENTS.items():
        previous_name = previous_name.replace(current, legacy)
    return current_path.with_name(previous_name)


def load_current_matrix(path: Path) -> np.ndarray:
    return sparse.load_npz(path).toarray()


def load_git_matrix(repo_root: Path, ref: str, path: Path) -> np.ndarray:
    relative_path = path.relative_to(repo_root).as_posix()
    result = subprocess.run(
        ["git", "show", f"{ref}:{relative_path}"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise FileNotFoundError(
            f"Could not read {relative_path} at {ref}: "
            f"{result.stderr.decode(errors='replace')}"
        )
    return sparse.load_npz(io.BytesIO(result.stdout)).toarray()


def load_activity_labels(path: Path) -> list[str]:
    labels = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter=";"):
            if len(row) == 3:
                categories = ast.literal_eval(row[1])
                labels.append(f"{row[0]} | {categories} | {row[2]}")
            elif len(row) == 4:
                labels.append(f"{row[0]} | {row[1]} | {row[2]} | {row[3]}")
            else:
                raise ValueError(f"Unexpected input label row: {row!r}")
    return labels


def load_category_labels(path: Path) -> dict[tuple[str, str], list[str]]:
    labels: dict[tuple[str, str], list[str]] = {group: [] for group in MATRIX_GROUPS}
    with path.open(encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter=","):
            if len(row) != 7:
                raise ValueError(f"Unexpected LCIA category row: {row!r}")
            group = (row[0], row[1])
            if group in labels:
                labels[group].append(f"{row[2]} | {row[3]} | {row[4]}")
    return labels


def top_indices(values: np.ndarray, count: int) -> np.ndarray:
    flat = values.ravel()
    if count >= flat.size:
        indices = np.arange(flat.size)
    else:
        indices = np.argpartition(flat, -count)[-count:]
    return indices[np.argsort(flat[indices])[::-1]]


def cell_row(
    basis: str,
    rank: int,
    matrix_path: Path,
    previous_path: Path,
    row: int,
    column: int,
    category_labels: list[str],
    activity_labels: list[str],
    old: np.ndarray,
    new: np.ndarray,
    abs_diff: np.ndarray,
    symmetric_relative: np.ndarray,
) -> dict[str, object]:
    return {
        "basis": basis,
        "rank": rank,
        "file": matrix_path.name,
        "previous_file": previous_path.name,
        "row": row,
        "category": category_labels[row],
        "column": column,
        "activity_or_flow": activity_labels[column],
        "old_value": old[row, column],
        "new_value": new[row, column],
        "absolute_difference": abs_diff[row, column],
        "symmetric_relative_difference": symmetric_relative[row, column],
    }


def finite_percentile(values: np.ndarray, percentile: float) -> float:
    if values.size == 0:
        return 0.0
    return float(np.percentile(values[np.isfinite(values)], percentile))


def compare_matrix(
    repo_root: Path,
    current_path: Path,
    ref: str,
    category_labels: dict[tuple[str, str], list[str]],
    activity_labels: list[str],
    args: argparse.Namespace,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    previous_path = previous_matrix_path(current_path)
    info = parse_matrix_name(current_path)
    group = (info.method, info.indicator)
    row_labels = category_labels[group]

    new = load_current_matrix(current_path)
    old = load_git_matrix(repo_root, ref, previous_path)
    if old.shape != new.shape:
        raise ValueError(
            f"Shape mismatch for {current_path.name}: old {old.shape}, new {new.shape}"
        )

    diff = new - old
    abs_diff = np.abs(diff)
    scale = np.maximum(np.abs(old), np.abs(new))
    symmetric_relative = np.zeros_like(abs_diff)
    np.divide(
        abs_diff,
        scale,
        out=symmetric_relative,
        where=scale > args.zero_tolerance,
    )

    changed = abs_diff > (
        args.absolute_tolerance + args.relative_tolerance * np.abs(old)
    )
    changed_relative = symmetric_relative[changed]
    old_nonzero = np.abs(old) > args.zero_tolerance
    new_nonzero = np.abs(new) > args.zero_tolerance

    max_abs_index = int(abs_diff.argmax())
    max_abs_row, max_abs_column = np.unravel_index(max_abs_index, abs_diff.shape)
    max_rel_index = int(symmetric_relative.argmax())
    max_rel_row, max_rel_column = np.unravel_index(
        max_rel_index, symmetric_relative.shape
    )

    summary = {
        "file": current_path.name,
        "previous_file": previous_path.name,
        "scenario": info.scenario,
        "year": info.year or "",
        "rows": new.shape[0],
        "columns": new.shape[1],
        "cells": new.size,
        "changed_cells": int(changed.sum()),
        "changed_percent": float(changed.mean() * 100),
        "zero_to_nonzero": int((~old_nonzero & new_nonzero).sum()),
        "nonzero_to_zero": int((old_nonzero & ~new_nonzero).sum()),
        "max_absolute_difference": float(abs_diff[max_abs_row, max_abs_column]),
        "max_absolute_row": int(max_abs_row),
        "max_absolute_category": row_labels[max_abs_row],
        "max_absolute_column": int(max_abs_column),
        "max_absolute_activity_or_flow": activity_labels[max_abs_column],
        "old_at_max_absolute": float(old[max_abs_row, max_abs_column]),
        "new_at_max_absolute": float(new[max_abs_row, max_abs_column]),
        "max_symmetric_relative_difference": float(
            symmetric_relative[max_rel_row, max_rel_column]
        ),
        "max_relative_row": int(max_rel_row),
        "max_relative_category": row_labels[max_rel_row],
        "max_relative_column": int(max_rel_column),
        "max_relative_activity_or_flow": activity_labels[max_rel_column],
        "old_at_max_relative": float(old[max_rel_row, max_rel_column]),
        "new_at_max_relative": float(new[max_rel_row, max_rel_column]),
        "median_relative_changed": finite_percentile(changed_relative, 50),
        "p95_relative_changed": finite_percentile(changed_relative, 95),
        "relative_gt_1pct": int((symmetric_relative[changed] > 0.01).sum()),
        "relative_gt_10pct": int((symmetric_relative[changed] > 0.10).sum()),
        "relative_gt_50pct": int((symmetric_relative[changed] > 0.50).sum()),
        "relative_gt_100pct": int((symmetric_relative[changed] > 1.00).sum()),
    }

    top_rows = []
    for rank, flat_index in enumerate(top_indices(abs_diff, args.top_n), start=1):
        if abs_diff.ravel()[flat_index] <= args.absolute_tolerance:
            continue
        row, column = np.unravel_index(int(flat_index), abs_diff.shape)
        top_rows.append(
            cell_row(
                "absolute",
                rank,
                current_path,
                previous_path,
                row,
                column,
                row_labels,
                activity_labels,
                old,
                new,
                abs_diff,
                symmetric_relative,
            )
        )

    relative_values = symmetric_relative.copy()
    relative_values[scale <= args.minimum_relative_magnitude] = 0.0
    for rank, flat_index in enumerate(
        top_indices(relative_values, args.top_n), start=1
    ):
        if relative_values.ravel()[flat_index] <= args.relative_tolerance:
            continue
        row, column = np.unravel_index(int(flat_index), relative_values.shape)
        top_rows.append(
            cell_row(
                "relative",
                rank,
                current_path,
                previous_path,
                row,
                column,
                row_labels,
                activity_labels,
                old,
                new,
                abs_diff,
                symmetric_relative,
            )
        )

    return summary, top_rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ref", default="HEAD~1", help="git ref with previous matrices"
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("tmp/iam_b_matrix_diff_summary.csv"),
        help="summary CSV path",
    )
    parser.add_argument(
        "--top-cells",
        type=Path,
        default=Path("tmp/iam_b_matrix_diff_top_cells.csv"),
        help="top changed cells CSV path",
    )
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--absolute-tolerance", type=float, default=1e-12)
    parser.add_argument("--relative-tolerance", type=float, default=1e-12)
    parser.add_argument("--zero-tolerance", type=float, default=1e-30)
    parser.add_argument(
        "--minimum-relative-magnitude",
        type=float,
        default=1e-12,
        help="ignore relative rankings when both old and new values are tiny",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    data_dir = repo_root / "carculator_utils" / "data"
    iam_dir = data_dir / "IAM"

    activity_labels = load_activity_labels(iam_dir / "dict_inputs_A_matrix.csv")
    category_labels = load_category_labels(
        data_dir / "lcia" / "dict_impact_categories.csv"
    )

    summary_rows = []
    top_rows = []
    for matrix_path in sorted(iam_dir.glob("B_matrix_*.npz")):
        summary, top_cells = compare_matrix(
            repo_root,
            matrix_path,
            args.ref,
            category_labels,
            activity_labels,
            args,
        )
        summary_rows.append(summary)
        top_rows.extend(top_cells)

    write_csv(args.summary, summary_rows)
    write_csv(args.top_cells, top_rows)

    changed_cells = sum(int(row["changed_cells"]) for row in summary_rows)
    total_cells = sum(int(row["cells"]) for row in summary_rows)
    high_relative = sum(int(row["relative_gt_50pct"]) for row in summary_rows)
    print(f"Compared {len(summary_rows)} matrices against {args.ref}.")
    print(
        f"Changed cells: {changed_cells}/{total_cells} ({changed_cells / total_cells:.2%})"
    )
    print(f"Changed cells with symmetric relative difference > 50%: {high_relative}")
    print(f"Summary: {args.summary}")
    print(f"Top cells: {args.top_cells}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
