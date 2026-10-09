"""Electricity supply by vehicle, manufacturing year and retained sample."""

import numpy as np
import xarray as xr


def lifetime_mix(
    array, generation, technologies, custom_mix=None, horizon_policy="hold"
):
    """Return normalized shares with axes value, combined_dim, year, technology.

    Retain the annual-step convention: truncate lifetime to whole years, with
    at least the manufacturing year's mix. Hold endpoints across the complete
    lifetime. ``truncate`` preserves the old horizon convention for legacy data.
    """
    if horizon_policy not in ("hold", "truncate"):
        raise ValueError("Electricity horizon policy must be 'hold' or 'truncate'.")
    dims = ("value", "combined_dim", "year")
    lifetime = (
        array.sel(parameter="lifetime kilometers")
        / array.sel(parameter="kilometers per year")
    ).transpose(*dims)
    coords = {dim: array.coords[dim].values for dim in dims}
    coords["technology"] = technologies
    shape = (*lifetime.shape, len(technologies))
    if custom_mix is not None:
        if isinstance(custom_mix, xr.DataArray):
            if set(custom_mix.dims) != {"year", "technology"}:
                raise ValueError(
                    "Labelled custom electricity mix needs year and technology dimensions."
                )
            for dim, labels in (
                ("year", array.year.values),
                ("technology", technologies),
            ):
                if not custom_mix.get_index(dim).is_unique or set(
                    custom_mix[dim].values
                ) != set(labels):
                    raise ValueError(
                        f"Custom electricity mix {dim} coordinates must match the inventory exactly."
                    )
            custom_mix = custom_mix.sel(
                year=array.year, technology=technologies
            ).transpose("year", "technology")
        mix = np.array(custom_mix, dtype=float, copy=True)
        expected = (array.sizes["year"], len(technologies))
        if mix.shape != expected:
            raise ValueError(
                f"Custom electricity mix must have shape {expected}; got {mix.shape}."
            )
        if not np.isfinite(mix).all() or (mix < 0).any():
            raise ValueError(
                "Custom electricity mix shares must be finite and nonnegative."
            )
        values = np.broadcast_to(mix, shape).copy()
    else:
        active = array.sel(parameter="TtW energy").transpose(*dims) > 0
        invalid = active & (~np.isfinite(lifetime) | (lifetime <= 0))
        if bool(invalid.any()):
            index = tuple(np.argwhere(invalid.values)[0])
            cell = {dim: coords[dim][pos] for dim, pos in zip(dims, index)}
            raise ValueError(
                f"Active vehicles require a finite positive operating lifetime: {cell}."
            )
        generation = generation.sel(variable=technologies)
        horizon = int(generation.year.max())
        values = np.empty(shape)
        cache = {}
        for index in np.ndindex(lifetime.shape):
            year = int(coords["year"][index[-1]])
            duration = (
                max(1, int(lifetime.values[index])) if active.values[index] else 1
            )
            start = min(year, horizon) if horizon_policy == "truncate" else year
            stop = (
                min(year + duration, horizon + 1)
                if horizon_policy == "truncate"
                else year + duration
            )
            key = (start, stop)
            if key not in cache:
                if horizon_policy == "truncate":
                    cache[key] = (
                        generation.interp(
                            year=np.arange(start, stop),
                            kwargs={"fill_value": "extrapolate"},
                        )
                        .mean("year")
                        .values
                    )
                else:
                    first = int(generation.year.min())
                    before = max(0, min(stop, first) - start)
                    after = max(0, stop - max(start, horizon + 1))
                    annual = np.arange(max(start, first), min(stop, horizon + 1))
                    total = (before / duration) * generation.sel(year=first).values + (
                        after / duration
                    ) * generation.sel(year=horizon).values
                    if annual.size:
                        total += (
                            generation.interp(year=annual).sum("year").values / duration
                        )
                    cache[key] = total
            values[index] = cache[key]
    if not np.isfinite(values).all():
        raise ValueError("Electricity mixes must contain finite shares.")
    values = np.clip(values, 0, 1)
    totals = values.sum(axis=-1, keepdims=True)
    if (totals <= 0).any():
        raise ValueError("Each electricity mix must have a positive total share.")
    return xr.DataArray(values / totals, dims=(*dims, "technology"), coords=coords)


def specialize_electricity_supplies(inventory):
    """Give differing vehicle mixes their own electricity-dependent supply chains.

    Called after ordinary foreground assembly, so subclass row lookups still see
    the original supplier names. Only paths between the electricity market and
    a vehicle are copied. Unchanged background activities remain shared.
    """
    inv = inventory
    original = inv.A
    count = original.shape[1]
    prep = inv.inputs[
        (
            "electricity supply for fuel preparation",
            inv.vm.country,
            "kilowatt hour",
            "electricity, low voltage",
        )
    ]
    pairs = []
    for size in inv.scope["size"]:
        for powertrain in inv.scope["powertrain"]:
            names = (
                f"{inv.vm.vehicle_type}, {powertrain}, {size}",
                f"transport, {inv.vm.vehicle_type}, {powertrain}, {size}",
            )
            pairs.append(
                (
                    f"{size} - {powertrain}",
                    [i for i, key in inv.rev_inputs.items() if key[0] in names],
                )
            )
    base = inv.electricity_mix.isel(combined_dim=0).values
    groups = []
    for label, columns in pairs:
        mix = inv.electricity_mix.sel(combined_dim=label).values
        if np.array_equal(mix, base):
            continue
        group = next((g for g in groups if np.array_equal(g["mix"], mix)), None)
        if group is None:
            group = {"label": label, "mix": mix, "columns": []}
            groups.append(group)
        group["columns"].extend(columns)

    # Map each cloned activity back to the original for characterization and
    # export provenance. The mapping also makes the additional rows inspectable.
    inv.electricity_supply_originals = {}
    inv.electricity_supply_indices = {}
    if not groups:
        return
    vehicle_columns = {i for _, columns in pairs for i in columns}
    edges = np.any(original != 0, axis=(0, 3))
    np.fill_diagonal(edges, False)
    dependent = {prep}
    while True:
        consumers = set(np.flatnonzero(edges[list(dependent)].any(axis=0)))
        expanded = dependent | (consumers - vehicle_columns)
        if expanded == dependent:
            break
        dependent = expanded

    next_index = count
    for group in groups:
        needed = set(np.flatnonzero(edges[:, group["columns"]].any(axis=1))) & dependent
        while needed:
            expanded = needed | (
                set(np.flatnonzero(edges[:, list(needed)].any(axis=1))) & dependent
            )
            if expanded == needed:
                break
            needed = expanded
        group["mapping"] = {}
        for old in sorted(needed):
            key = inv.rev_inputs[old]
            scoped_key = (f"{key[0]} [for {group['label']}]", *key[1:])
            inv.inputs[scoped_key] = next_index
            group["mapping"][old] = next_index
            inv.electricity_supply_originals[next_index] = old
            next_index += 1

    if next_index == count:
        return
    expanded = np.zeros((inv.iterations, next_index, next_index, original.shape[-1]))
    expanded[:, :count, :count, :] = original
    for group in groups:
        mapping = group["mapping"]
        if not mapping:
            continue
        old_rows, new_rows = list(mapping), list(mapping.values())
        for old, new in mapping.items():
            expanded[:, :count, new, :] = original[:, :, old, :]
            expanded[:, new_rows, new, :] = original[:, old_rows, old, :]
            expanded[:, old_rows, new, :] = 0
        for column in group["columns"]:
            inv.electricity_supply_indices[column] = mapping.copy()
            expanded[:, new_rows, column, :] = original[:, old_rows, column, :]
            expanded[:, old_rows, column, :] = 0
        generators = [
            mapping.get(inv.inputs[inv.elec_map[t]], inv.inputs[inv.elec_map[t]])
            for t in inv.electricity_technologies
        ]
        expanded[:, generators, mapping[prep], :] = (
            -group["mix"].transpose(0, 2, 1) * inv.electricity_losses
        )
    inv.A = expanded
    inv.rev_inputs = {value: key for key, value in inv.inputs.items()}
    # New rows inherit the original activities' precomputed factors. Electricity
    # markets themselves have zero factors and obtain their impacts via A.
    originals = list(range(count)) + [
        inv.electricity_supply_originals[i] for i in range(count, next_index)
    ]
    labels = np.empty(len(inv.inputs), dtype=object)
    labels[:] = list(inv.inputs)
    inv.B = inv.B.isel(activity=originals).assign_coords(activity=labels)
    inv.list_cat, inv.split_indices = inv.get_split_indices()
