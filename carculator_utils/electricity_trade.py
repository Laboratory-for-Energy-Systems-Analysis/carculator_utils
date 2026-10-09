"""Explicit consumption mixes from generation and bilateral physical imports."""

import numpy as np
import xarray as xr


def consumption_mix(generation, trade, *, source):
    """Trace technology shares through a closed, balanced electricity network.

    ``generation`` has country, year, technology dimensions; ``trade`` has
    exporter, importer, year. Both contain nonnegative absolute energy in the
    same explicitly declared ``attrs['unit']`` (for example TWh). Imports and
    exports refer to the same border boundary; grid losses are applied later.
    Shares assume each country's generation and imports form a perfectly mixed
    pool. The result has country, year, technology axes and a consumption
    coordinate in the source energy unit. No data are downloaded or inferred.
    """
    for array, dims, name in (
        (generation, {"country", "year", "technology"}, "generation"),
        (trade, {"exporter", "importer", "year"}, "trade"),
    ):
        if not isinstance(array, xr.DataArray) or set(array.dims) != dims:
            raise ValueError(
                f"{name} must be a DataArray with dimensions {sorted(dims)}."
            )
        for dim in dims:
            if (
                dim not in array.coords
                or not array.sizes[dim]
                or not array.get_index(dim).is_unique
            ):
                raise ValueError(f"{name} requires nonempty unique {dim} coordinates.")
        if not np.isfinite(array).all() or bool((array < 0).any()):
            raise ValueError(f"{name} must contain finite nonnegative absolute energy.")
    unit = generation.attrs.get("unit")
    if not unit or unit != trade.attrs.get("unit"):
        raise ValueError("Generation and trade must declare the same energy unit.")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Document the generation/trade source and boundary in source.")
    countries = generation.country.values
    years = generation.year.values
    if any(
        set(trade[dim].values) != set(countries) for dim in ("exporter", "importer")
    ) or set(trade.year.values) != set(years):
        raise ValueError(
            "Generation and trade must cover exactly the same countries and years; include external suppliers explicitly."
        )
    g = generation.transpose("year", "country", "technology").values.astype(float)
    t = (
        trade.sel(exporter=countries, importer=countries, year=years)
        .transpose("year", "exporter", "importer")
        .values.astype(float)
    )
    if np.any(np.diagonal(t, axis1=1, axis2=2) != 0):
        raise ValueError(
            "Trade diagonal must be zero; domestic generation is supplied separately."
        )
    supply = g.sum(axis=2) + t.sum(axis=1)
    demand = supply - t.sum(axis=2)
    tolerance = np.maximum(supply, 1) * 1e-10
    if (demand < -tolerance).any() or (supply <= 0).any():
        raise ValueError(
            "Each country-year needs positive supply and exports no greater than supply."
        )
    result = np.empty_like(g)
    for index, year in enumerate(years):
        matrix = np.diag(supply[index]) - t[index].T
        try:
            shares = np.linalg.solve(matrix, g[index])
        except np.linalg.LinAlgError as error:
            raise ValueError(
                f"Unanchored electricity trade cycle in {year}; supply origin cannot be determined."
            ) from error
        if (
            not np.isfinite(shares).all()
            or (shares < -1e-10).any()
            or not np.allclose(shares.sum(axis=1), 1, rtol=0, atol=1e-8)
        ):
            raise ValueError(
                f"Cannot determine a normalized consumption mix in {year}."
            )
        shares = np.maximum(shares, 0)
        if not np.allclose(
            (shares * demand[index, :, None]).sum(axis=0),
            g[index].sum(axis=0),
            rtol=1e-8,
            atol=1e-10,
        ):
            raise ValueError(f"Technology energy balance failed in {year}.")
        result[index] = shares
    return xr.DataArray(
        result.transpose(1, 0, 2),
        dims=("country", "year", "technology"),
        coords={
            "country": countries,
            "year": years,
            "technology": generation.technology.values,
            "consumption": (("country", "year"), np.maximum(demand, 0).T),
        },
        attrs={
            "boundary": "consumption mix including physical imports and re-exports, before grid losses",
            "source": source,
            "trade_method": "proportional sharing",
            "energy_unit": unit,
            "method_reference": "https://doi.org/10.1016/j.ijepes.2017.10.024",
        },
    )
