"""Exact foreground reachability and destination-link audits for exported data."""

import math
from copy import deepcopy


def migrate_background(data, mapping, version):
    """Resolve external logical suppliers, preserving foreground identities.

    Disaggregation coefficients multiply the signed demand. Newly introduced
    suppliers without a verified older counterpart fail before serialization.
    Work on a copy so repeated exports cannot change the inventory.
    """
    result = deepcopy(data)
    foreground = {technosphere_key(activity) for activity in result}
    records = {tuple(row["label"]): row for row in mapping["activities"]}
    for activity in result:
        exchanges = []
        for exchange in activity["exchanges"]:
            if (
                exchange["type"] != "technosphere"
                or technosphere_key(exchange) in foreground
            ):
                exchanges.append(exchange)
                continue
            label = tuple(
                exchange[k] for k in ("name", "location", "unit", "reference product")
            )
            record = records.get(label)
            if record is None:
                exchanges.append(exchange)
                continue
            if version != mapping["ecoinvent_version"]:
                if not record.get(f"available_in_{version}", False):
                    raise ValueError(
                        f"No verified ecoinvent {version} cutoff supplier for "
                        f"{label!r}. Use ecoinvent 3.12; no older substitute is assumed."
                    )
                exchanges.append(exchange)
                continue
            targets = record["targets"]
            weights = [float(weight) for _, weight in targets]
            if (
                not weights
                or any(not math.isfinite(w) or w < 0 for w in weights)
                or not math.isclose(sum(weights), 1, abs_tol=1e-9)
            ):
                raise ValueError(f"Invalid supplier migration weights for {label!r}")
            for target, weight in targets:
                if target[2] != exchange["unit"]:
                    raise ValueError(f"Supplier migration changes units for {label!r}")
                migrated = exchange.copy()
                migrated.update(
                    zip(("name", "location", "unit", "reference product"), target)
                )
                migrated["amount"] *= weight
                migrated.pop("input", None)
                exchanges.append(migrated)
        activity["exchanges"] = exchanges
    return result


def map_legacy_exchanges(data, mapping):
    """Apply the reviewed legacy names only to external exchanges, on a copy."""
    result = deepcopy(data)
    foreground = {technosphere_key(activity) for activity in result}
    for activity in result:
        for exchange in activity["exchanges"]:
            if exchange["type"] == "biosphere":
                key = (
                    exchange["name"],
                    "",
                    tuple(exchange["categories"]),
                    exchange["unit"],
                    "",
                )
                if key in mapping:
                    name, _, categories, unit, _ = mapping[key]
                    exchange.update(name=name, categories=categories, unit=unit)
            elif (
                exchange["type"] == "technosphere"
                and technosphere_key(exchange) not in foreground
            ):
                key = (
                    exchange["name"],
                    exchange["location"],
                    "",
                    exchange["unit"],
                    exchange["reference product"],
                )
                if key in mapping:
                    name, location, _, unit, product = mapping[key]
                    exchange.update(name=name, location=location, unit=unit)
                    exchange["reference product"] = product
    return result


def technosphere_key(record):
    return (
        record["name"],
        record.get("reference product", record.get("product")),
        record.get("location"),
        record["unit"],
    )


def reachable_foreground(data, vehicle_type):
    """Retain only suppliers reachable from the exported vehicle transports.

    An unused fuel chain must not introduce background requirements into an
    otherwise unrelated vehicle export. Generic non-vehicle fixtures are kept.
    """
    activities = {technosphere_key(activity): activity for activity in data}
    if len(activities) != len(data):
        raise ValueError("Duplicate foreground identity in export.")
    roots = {
        key for key in activities if key[0].startswith(f"transport, {vehicle_type}, ")
    }
    if not roots:
        return data
    selected, pending = set(), list(roots)
    while pending:
        key = pending.pop()
        if key in selected:
            continue
        selected.add(key)
        for exchange in activities[key]["exchanges"]:
            if exchange["type"] == "technosphere":
                supplier = technosphere_key(exchange)
                if supplier in activities and supplier not in selected:
                    pending.append(supplier)
    return [activity for activity in data if technosphere_key(activity) in selected]


def match_export(data, technosphere, biosphere, *, strict=True):
    """Link on a copy using exact destination identity-to-key catalogs.

    Catalog values are lists of destination (database, code) keys. No name-only
    matches, geographic fallbacks, or synthetic elementary flows are invented.
    Custom noise needs an explicit user database/method. This is link validation,
    not proof of LCIA parity between different database/method versions.
    """
    result = deepcopy(data)
    foreground = {
        technosphere_key(activity): (activity["database"], activity["code"])
        for activity in result
    }
    unresolved = []
    for activity in result:
        for exchange in activity["exchanges"]:
            kind = exchange["type"]
            if kind == "production":
                matches = [foreground[technosphere_key(activity)]]
            elif kind == "technosphere":
                key = technosphere_key(exchange)
                matches = (
                    [foreground[key]]
                    if key in foreground
                    else technosphere.get(key, [])
                )
            elif kind == "biosphere":
                key = (
                    exchange["name"],
                    tuple(exchange.get("categories", ())),
                    exchange["unit"],
                )
                matches = biosphere.get(key, [])
            else:
                raise ValueError(f"Unsupported exchange type: {kind}.")
            if len(matches) == 1:
                exchange["input"] = tuple(matches[0])
            else:
                exchange.pop("input", None)
                unresolved.append(
                    {
                        "activity": activity["name"],
                        "type": kind,
                        "identity": key,
                        "matches": len(matches),
                        "amount": exchange["amount"],
                    }
                )
    if strict and unresolved:
        first = unresolved[0]
        raise ValueError(
            f"Export has {len(unresolved)} unresolved/ambiguous exchanges; first: {first['identity']} ({first['matches']} matches)."
        )
    return result, unresolved


def validate_known_target_gaps(data, version):
    """Reject two 3.10 coal routes absent from the exact 3.9 cutoff database."""
    if version != "3.9":
        return
    missing = {
        ("methanol production, coal gasification", "methanol", "RoW", "kilogram"),
        (
            "hydrogen production, coal gasification",
            "hydrogen, gaseous, low pressure",
            "RoW",
            "kilogram",
        ),
    }
    for activity in data:
        for exchange in activity["exchanges"]:
            if (
                exchange["type"] == "technosphere"
                and technosphere_key(exchange) in missing
                and exchange["amount"] != 0
            ):
                raise ValueError(
                    f"No verified ecoinvent 3.9 cutoff supplier for {exchange['name']!r}. Export this fuel route to 3.10 or supply a reviewed mapping; no substitute is assumed."
                )
