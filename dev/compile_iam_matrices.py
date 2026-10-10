"""Compile an aligned candidate A/index/B bundle from certified Brightway builds.

B stores full LCIA scores for background suppliers and characterization factors
for elementary flows. Expanded foreground columns are zero in B. Every source
resolution is exact or attributed; missing/ambiguous matches stop the build.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from iam_matrix_tools import (
    activity_label,
    assemble_matrix,
    flow_label,
    load_labels,
    load_migrations,
    resolve_activity,
    save_labels,
)
from rebuild_iam import PATHWAYS, PREFIX, database_plan
from rebuild_iam_databases import digest, write_json
from scipy import sparse
from scipy.sparse.linalg import splu
from update_iam_b_matrices import (
    MATRIX_GROUPS,
    load_impact_categories,
    mapped_methods,
    validate_method_units,
)

ROOT = Path(__file__).resolve().parents[1]


def activity_index(database):
    result = defaultdict(list)
    for activity in database:
        result[activity_label(activity)].append(activity)
    return dict(result)


def load_policy():
    policy = json.loads((ROOT / "dev/iam_migration_policy.json").read_text())
    overrides = {tuple(row["label"]): row for row in policy["overrides"]}
    retired = {tuple(row["label"]) for row in policy["retired_foreground"]}
    return policy, overrides, retired


def migration_chain():
    # Locate files without importing premise (and initializing unrelated caches).
    import importlib.util

    base = Path(importlib.util.find_spec("premise").origin).parent
    directory = base / "data/utils/import/migrations/cutoff"
    paths = [
        directory / f"ecoinvent-{a}-cutoff-ecoinvent-{b}-cutoff.json"
        for a, b in (("3.10", "3.11"), ("3.11", "3.12"))
    ]
    return load_migrations(paths), {p.name: digest(p) for p in paths}


def compile_foreground(
    source, original_labels, foreground, chain, overrides, retired, background_labels
):
    """Refresh every expanded recipe and append newly required suppliers/flows."""
    labels = [label for label in original_labels if label not in retired]
    index = activity_index(source)
    physical_to_logical = {}
    provenance = []
    suppliers = {}
    for label in foreground:
        targets, sources = resolve_activity(label, index, chain, overrides)
        if len(targets) != 1 or targets[0][1] != 1:
            raise ValueError(
                f"Expanded foreground requires one reference activity: {label}"
            )
        target = targets[0][0]
        if target in physical_to_logical:
            raise ValueError(
                f"Two foreground labels resolve to the same activity: {target}"
            )
        physical_to_logical[target] = label
        suppliers[label] = index[target][0]
        provenance.append(
            {"label": label, "source_label": target, "migration": sources}
        )
    for label in labels:
        if len(label) != 4 or label in suppliers:
            continue
        targets, _ = resolve_activity(label, index, chain, overrides)
        if len(targets) == 1 and targets[0][1] == 1:
            target = targets[0][0]
            # Reuse a stable logical row for an exact one-to-one migration.
            # Adding a second named supplier would make legacy substring
            # selectors purchase both rows (e.g. container-ship transport).
            physical_to_logical.setdefault(
                target, target if target in labels else label
            )
    recipes_by_label = {}
    required = set()
    pending = list(suppliers)
    for label in pending:
        activity = suppliers[label]
        exchanges = []
        for exchange in activity.exchanges():
            kind = exchange["type"]
            supplier = exchange.input
            if kind == "biosphere":
                row = flow_label(supplier)
            elif kind in {"production", "technosphere", "substitution"}:
                physical = activity_label(supplier)
                row = physical_to_logical.get(physical, physical)
                if (
                    kind != "production"
                    and physical not in background_labels
                    and row not in suppliers
                ):
                    # Supplementary premise datasets must be explicit foreground
                    # recipes, so exports can link to a plain ecoinvent database.
                    suppliers[row] = supplier
                    physical_to_logical[physical] = row
                    pending.append(row)
                    provenance.append(
                        {
                            "label": row,
                            "source_label": physical,
                            "migration": [],
                            "added_foreground": True,
                        }
                    )
            else:
                raise ValueError(f"Unsupported exchange type {kind!r} in {label}")
            if row in retired:
                raise ValueError(f"Retired intermediate is still used: {row}")
            exchanges.append((row, kind, float(exchange["amount"])))
            required.add(row)
        recipes_by_label[label] = exchanges
    # Keep the existing order for all retained labels. Sort additions by repr,
    # which is stable across activity iteration order and tuple/list field types.
    labels.extend(sorted(required.difference(labels), key=repr))
    positions = {label: i for i, label in enumerate(labels)}
    recipes = {positions[label]: recipe for label, recipe in recipes_by_label.items()}
    matrix = assemble_matrix(labels, recipes)
    if not np.isfinite(matrix.data).all():
        raise ValueError("Nonfinite A coefficients")
    return labels, matrix, provenance


def load_methods(bd, category_path):
    entries = mapped_methods(load_impact_categories(category_path), set(bd.methods))
    missing = [
        entry
        for entry in entries
        if entry.brightway_method is None
        and entry.category.source != "Cucurachi et al."
    ]
    if missing:
        raise LookupError(f"Missing LCIA methods: {missing}")
    validate_method_units(entries, bd.methods)
    return entries


def load_factors(bd, entries):
    factors = []
    for entry in entries:
        if entry.brightway_method is None:
            factors.append({})
            continue
        result = {}
        for row in bd.Method(entry.brightway_method).load():
            if len(row) != 2:
                raise ValueError(f"Regionalized CF requires explicit handling: {entry}")
            key, amount = row
            flow_id = (
                int(key)
                if isinstance(key, (int, np.integer))
                else bd.get_activity(key).id
            )
            if isinstance(amount, dict):
                amount = amount["amount"]
            amount = float(amount)
            if not np.isfinite(amount):
                raise ValueError(f"Nonfinite characterization factor: {entry}")
            if flow_id in result:
                raise ValueError(f"Duplicate CF for {flow_id}: {entry}")
            result[flow_id] = amount
        factors.append(result)
    return factors


def characterize_background(bd, database, entries, factors):
    """Adjoint LCIA: solve once per category instead of once per supplier.

    The technosphere includes signed, non-unit production. If C is the CF
    matrix and E the biosphere matrix, scores are C E T^-1; solve T.T x = E.T C.T.
    A separate Brightway forward calculation checks selected demand vectors.
    """
    import bw2calc as bc

    first = next(iter(bd.Database(database)))
    lca = bc.LCA({first.id: 1})
    lca.load_lci_data()
    print(
        f"Loaded matrices: T={lca.technosphere_matrix.dtype}, E={lca.biosphere_matrix.dtype}",
        flush=True,
    )
    # Compact exports can store single-precision coefficients. Do arithmetic
    # in double precision, including forward verification and row summation.
    lca.technosphere_matrix = lca.technosphere_matrix.astype(np.float64)
    lca.biosphere_matrix = lca.biosphere_matrix.astype(np.float64)
    lca.lci(factorize=True)
    rows, columns, values = [], [], []
    for row, method_factors in enumerate(factors):
        for flow_id, amount in method_factors.items():
            if flow_id in lca.dicts.biosphere:
                rows.append(row)
                columns.append(lca.dicts.biosphere[flow_id])
                values.append(amount)
    cf = sparse.csr_matrix(
        (values, (rows, columns)), shape=(len(entries), len(lca.dicts.biosphere))
    )
    direct = (cf @ lca.biosphere_matrix).toarray()
    from scikits.umfpack import splu as umfpack_splu

    solver = umfpack_splu(lca.technosphere_matrix.T.tocsc())
    print("Solving LCIA adjoints", flush=True)
    scores = np.vstack([solver.solve(row) for row in direct])
    if not np.isfinite(scores).all():
        raise ValueError(f"Nonfinite LCIA scores for {database}")
    ids = dict(lca.dicts.product)
    return scores, ids, lca, cf


def noise_factors(original_iam, original_labels, labels, entries):
    """Preserve only the explicitly custom Cucurachi noise CFs, by full label."""
    original_positions = {label: i for i, label in enumerate(original_labels)}
    noise = np.zeros((len(entries), len(labels)))
    for row, entry in enumerate(entries):
        if entry.brightway_method is not None:
            continue
        old = sparse.load_npz(
            original_iam / f"B_matrix_{entry.group[0]}_{entry.group[1]}_static.npz"
        ).toarray()[entry.row]
        for i, label in enumerate(labels):
            if len(label) == 3 and label[0].startswith("noise, "):
                if label not in original_positions:
                    raise LookupError(f"No published custom noise factor for {label}")
                noise[row, i] = old[original_positions[label]]
        excluded = [
            i
            for i, label in enumerate(original_labels)
            if not (len(label) == 3 and label[0].startswith("noise, "))
        ]
        if np.any(old[excluded] != 0):
            raise ValueError("Unexpected background contribution in custom noise row")
    return noise


def compile_background(
    bd, database, labels, foreground, entries, factors, chain, overrides, noise
):
    index = activity_index(bd.Database(database))
    biosphere = defaultdict(list)
    for flow in bd.Database("ecoinvent-3.12-biosphere"):
        biosphere[flow_label(flow)].append(flow)
    resolved = {}
    provenance = []
    for column, label in enumerate(labels):
        if len(label) == 4:
            # Resolve foreground too: needed for independent static parity.
            targets, sources = resolve_activity(label, index, chain, overrides)
            resolved[column] = [(index[key][0].id, weight) for key, weight in targets]
            if label not in foreground:
                provenance.append(
                    {"label": label, "targets": targets, "migration": sources}
                )
        elif not label[0].startswith("noise, ") and len(biosphere.get(label, [])) != 1:
            raise LookupError(f"Missing/ambiguous biosphere flow: {label}")
    scores, ids, lca, cf = characterize_background(bd, database, entries, factors)
    result = noise.copy()
    for column, label in enumerate(labels):
        if len(label) == 4:
            if label not in foreground:
                for activity_id, weight in resolved[column]:
                    result[:, column] += scores[:, ids[activity_id]] * weight
        elif not label[0].startswith("noise, "):
            flow_id = biosphere[label][0].id
            result[:, column] = [values.get(flow_id, 0.0) for values in factors]
    # Validate the adjoint against separately solved forward supply arrays.
    checked = []
    candidates = list(resolved)
    for column in sorted(
        set(candidates[:: max(1, len(candidates) // 12)] + candidates[-1:])
    ):
        demand = dict(resolved[column])
        lca.redo_lci(demand)
        observed = np.asarray(
            cf @ np.asarray(lca.inventory.sum(axis=1)).ravel()
        ).ravel()
        expected = sum(scores[:, ids[key]] * amount for key, amount in demand.items())
        np.testing.assert_allclose(
            observed,
            expected,
            rtol=1e-7,
            atol=1e-12,
            err_msg=f"Forward/adjoint mismatch: {labels[column]}",
        )
        checked.append(labels[column])
    if not np.isfinite(result).all():
        raise ValueError("Nonfinite B coefficients")
    return (
        result,
        {"suppliers": provenance, "forward_checks": checked},
        scores,
        ids,
        resolved,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument(
        "--legacy-catalogue",
        type=Path,
        help="Optional JSON list of exact ecoinvent 3.10 cutoff activity labels",
    )
    parser.add_argument("--legacy-39-catalogue", type=Path)
    args = parser.parse_args()
    import bw2data as bd

    if args.project not in bd.projects:
        raise ValueError(f"Missing project {args.project}")
    previous = bd.projects.current
    try:
        bd.projects.set_current(args.project)
        legacy_labels = (
            {tuple(label) for label in json.loads(args.legacy_catalogue.read_text())}
            if args.legacy_catalogue
            else set()
        )
        legacy_39_labels = (
            {tuple(label) for label in json.loads(args.legacy_39_catalogue.read_text())}
            if args.legacy_39_catalogue
            else set()
        )
        import csv

        legacy_mapping = {}
        with (ROOT / "carculator_utils/data/export/ei310_to_ei39.csv").open() as stream:
            rows = csv.reader(stream, delimiter=";")
            next(rows)
            for row in rows:
                if not row[2]:
                    legacy_mapping[tuple(row[i].strip() for i in (0, 1, 3, 4))] = tuple(
                        row[i].strip() for i in (5, 6, 8, 9)
                    )
        workspace = args.workspace.resolve()
        candidate = workspace / "candidate"
        candidate.mkdir(exist_ok=True)
        write_json(candidate / "build_manifest.json", {"complete": False})
        original = ROOT / "carculator_utils/data/IAM"
        original_labels = load_labels(original / "dict_inputs_A_matrix.csv")
        foreground = load_labels(ROOT / "dev/iam_foreground.csv")
        policy, overrides, retired = load_policy()
        chain, migration_hashes = migration_chain()
        renames = {
            tuple(row["old"]): tuple(row["new"])
            for row in policy.get("logical_renames", [])
        }
        renamed_labels = [renames.get(label, label) for label in original_labels]
        labels, matrix, foreground_provenance = compile_foreground(
            bd.Database(PREFIX + "-static"),
            renamed_labels,
            foreground,
            chain,
            overrides,
            retired,
            set(activity_index(bd.Database("ecoinvent-3.12-cutoff"))),
        )
        foreground = [tuple(row["label"]) for row in foreground_provenance]
        sparse.save_npz(candidate / "A_matrix.npz", matrix)
        save_labels(candidate / "dict_inputs_A_matrix.csv", labels)
        entries = load_methods(
            bd, ROOT / "carculator_utils/data/lcia/dict_impact_categories.csv"
        )
        factors = load_factors(bd, entries)
        noise = noise_factors(original, original_labels, labels, entries)
        report = {
            "project": args.project,
            "migration_policy": policy,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ecoinvent_version": "3.12",
            "system_model": "cutoff",
            "packages": {
                name: importlib.metadata.version(name)
                for name in (
                    "premise",
                    "bw2data",
                    "bw2io",
                    "bw2calc",
                    "numpy",
                    "scipy",
                    "pyarrow",
                    "scikit-umfpack",
                )
            },
            "build_requirements_sha256": digest(
                ROOT / "dev/iam-build-requirements.txt"
            ),
            "migration_hashes": migration_hashes,
            "foreground": foreground_provenance,
            "label_count": len(labels),
            "A_nonzero": matrix.nnz,
            "databases": [],
            "complete": False,
        }
        for item in database_plan():
            if args.static_only and not item["static"]:
                continue
            database = item["name"]
            if database not in bd.databases:
                raise ValueError(f"Missing built database: {database}")
            build_report = workspace / "database-reports" / (database + ".json")
            built = json.loads(build_report.read_text())
            if not built.get("written") or built.get("project") != args.project:
                raise ValueError(f"Unverified build: {database}")
            print(f"Characterizing: {database}", flush=True)
            started = time.monotonic()
            result, audit, scores, ids, resolved = compile_background(
                bd,
                database,
                labels,
                set(foreground),
                entries,
                factors,
                chain,
                overrides,
                noise,
            )
            if item["static"]:
                # All expanded foreground unit demands must reproduce the full
                # static Brightway model, including waste/negative production.
                solver = splu(matrix.tocsc())
                errors = []
                scaled_errors = []
                for label in foreground:
                    column = labels.index(label)
                    demand = np.zeros(len(labels))
                    demand[column] = 1
                    observed = result @ solver.solve(demand)
                    expected = sum(
                        scores[:, ids[key]] * amount for key, amount in resolved[column]
                    )
                    np.testing.assert_allclose(
                        observed,
                        expected,
                        rtol=1e-6,
                        atol=1e-11,
                        err_msg=f"Reduced/full inventory mismatch: {label}",
                    )
                    errors.append(float(np.max(np.abs(observed - expected))))
                    scaled_errors.append(
                        float(
                            np.max(
                                np.abs(observed - expected)
                                / (1e-11 + 1e-6 * np.abs(expected))
                            )
                        )
                    )
                audit["foreground_parity_checks"] = len(errors)
                audit["maximum_absolute_foreground_error"] = max(errors)
                audit["maximum_fraction_of_parity_tolerance"] = max(scaled_errors)
                for supplier in audit["suppliers"]:
                    supplier["available_in_3.10"] = (
                        tuple(supplier["label"]) in legacy_labels
                    )
                    label = tuple(supplier["label"])
                    supplier["available_in_3.9"] = (
                        legacy_mapping.get(label, label) in legacy_39_labels
                    )
                write_json(
                    candidate / "background_mapping.json",
                    {
                        "ecoinvent_version": "3.12",
                        "system_model": "cutoff",
                        "activities": audit["suppliers"],
                        "legacy_39_catalogue_sha256": (
                            digest(args.legacy_39_catalogue)
                            if args.legacy_39_catalogue
                            else None
                        ),
                        "legacy_catalogue_sha256": (
                            digest(args.legacy_catalogue)
                            if args.legacy_catalogue
                            else None
                        ),
                        "logical_renames": policy.get("logical_renames", []),
                    },
                )
            outputs = (
                [("static", None)]
                if item["static"]
                else [(item["pathway"], item["year"])]
            )
            if not item["static"] and item["year"] <= 2020:
                outputs = [(pathway, item["year"]) for pathway in PATHWAYS]
            for method, indicator in MATRIX_GROUPS:
                selected = [
                    i
                    for i, entry in enumerate(entries)
                    if entry.group == (method, indicator)
                ]
                for pathway, year in outputs:
                    suffix = "static" if year is None else f"remind_{pathway}_{year}"
                    sparse.save_npz(
                        candidate / f"B_matrix_{method}_{indicator}_{suffix}.npz",
                        sparse.csr_matrix(result[selected]),
                    )
            audit.update(
                {
                    "database": database,
                    "build_manifest_sha256": digest(build_report),
                    "seconds": time.monotonic() - started,
                    "build": {
                        k: v
                        for k, v in built.items()
                        if k not in {"seconds", "python", "project"}
                    },
                }
            )
            write_json(
                workspace / "database-reports" / (database + "-matrix.json"), audit
            )
            report["databases"].append(
                {k: v for k, v in audit.items() if k != "suppliers"}
            )
            write_json(candidate / "build_manifest.json", report)
            print(f"Completed coefficients in {audit['seconds']:.1f}s", flush=True)
        report["complete"] = not args.static_only
        report["resource_hashes"] = {
            p.name: digest(p)
            for p in sorted(candidate.iterdir())
            if p.suffix in {".npz", ".csv"} or p.name == "background_mapping.json"
        }
        write_json(candidate / "build_manifest.json", report)
    finally:
        bd.projects.set_current(previous)


if __name__ == "__main__":
    main()
