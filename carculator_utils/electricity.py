"""Versioned, offline national generation scenarios and their provenance."""

import json
import warnings
from functools import lru_cache

import numpy as np
import pandas as pd
import xarray as xr
import yaml

from . import DATA_DIR

ELECTRICITY_DIR = DATA_DIR / "electricity"
DEFAULT_SCENARIO = "geco-2025-reference"
SCENARIOS = (DEFAULT_SCENARIO, "geco-2025-ndc-lts", "geco-2025-1.5c", "legacy")


class ElectricityDataWarning(UserWarning):
    """An electricity result uses a documented geographic or temporal proxy."""


def validate_shares(frame, keys, technologies, tolerance=1e-7):
    """Validate complete, unique fraction records before any interpolation.

    Only rounding differences within ``tolerance`` are normalized. Missing,
    negative and unbalanced records raise with their geographic/year keys.
    Return a private copy, preserving caller-owned data.
    """
    required = set(keys) | set(technologies)
    if set(frame.columns) != required:
        raise ValueError(
            f"Electricity columns differ: missing {required - set(frame.columns)}, "
            f"unexpected {set(frame.columns) - required}."
        )
    if frame.empty or frame[keys].isna().any().any():
        raise ValueError("Electricity records require nonempty geographic/year keys.")
    years = pd.to_numeric(frame["year"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(years).all() or (years != np.floor(years)).any():
        raise ValueError("Electricity years must be finite integers.")
    duplicate = frame.duplicated(keys, keep=False)
    if duplicate.any():
        raise ValueError(
            f"Duplicate electricity record: {frame.loc[duplicate, keys].iloc[0].to_dict()}"
        )
    values = frame[technologies].to_numpy(dtype=float)
    invalid = (~np.isfinite(values)).any(axis=1) | (values < 0).any(axis=1)
    totals = values.sum(axis=1)
    invalid |= (totals <= 0) | (abs(totals - 1) > tolerance)
    if invalid.any():
        i = np.flatnonzero(invalid)[0]
        raise ValueError(
            f"Invalid electricity shares at {frame.iloc[i][keys].to_dict()}: "
            f"total={totals[i]:.12g}; require finite nonnegative fractions summing to one."
        )
    result = frame.copy(deep=True)
    result[technologies] = values / totals[:, None]
    return result


def _legacy_mix():
    """Retain the previous interpolation/normalization exactly for reproduction."""
    frame = pd.read_csv(ELECTRICITY_DIR / "electricity_mixes.csv", sep=";")
    array = (
        frame.melt(id_vars=["country", "year"], value_name="value")
        .groupby(["country", "year", "variable"])["value"]
        .mean()
        .to_xarray()
    )
    array = array.interpolate_na(
        dim="year", method="linear", fill_value="extrapolate"
    ).clip(0, 1)
    array /= array.sum("variable")
    array.attrs.update(electricity_scenario="legacy", horizon_policy="truncate")
    return array


@lru_cache(maxsize=4)
def _load_mix(scenario):
    if scenario == "legacy":
        return _legacy_mix()
    with (ELECTRICITY_DIR / "elec_tech_map.yaml").open(encoding="utf-8") as stream:
        technologies = list(yaml.safe_load(stream))
    history = validate_shares(
        pd.read_csv(
            ELECTRICITY_DIR / "electricity_history.csv", sep=";", keep_default_na=False
        ),
        ["country", "year"],
        technologies,
    )
    projections = validate_shares(
        pd.read_csv(
            ELECTRICITY_DIR / "electricity_projections.csv",
            sep=";",
            keep_default_na=False,
        ),
        ["scenario", "region", "year"],
        technologies,
    )
    projections = projections.loc[projections.scenario == scenario]
    if projections.empty:
        raise ValueError(f"No bundled electricity projections for {scenario}.")
    geographies = pd.read_csv(
        ELECTRICITY_DIR / "electricity_geographies.csv", sep=";", keep_default_na=False
    )
    if geographies.country.duplicated().any() or set(geographies.country) != set(
        history.country
    ):
        raise ValueError("Electricity geography mapping must match history uniquely.")
    years = np.arange(int(history.year.min()), int(projections.year.max()) + 1)
    history_cutoff = int(history.year.max())
    countries, mixes, last_years, regions, kinds = [], [], [], [], []
    for row in geographies.sort_values("country").itertuples(index=False):
        past = history.loc[history.country == row.country].sort_values("year")
        future = projections.loc[
            projections.region == row.projection_region
        ].sort_values("year")
        if future.empty:
            raise ValueError(
                f"Missing electricity projection region {row.projection_region}."
            )
        last = int(past.year.max())
        # Use national observations up to their final available year. Regional
        # proxies are explicit endpoints, never labelled as national forecasts.
        future = future.loc[future.year > history_cutoff]
        # A scenario must not rewrite missing recent historical observations.
        # Hold the last observation to the snapshot boundary before forecasting.
        anchors = past[["year", *technologies]]
        if last < history_cutoff:
            anchors = pd.concat([anchors, anchors.tail(1).assign(year=history_cutoff)])
        knots = pd.concat([anchors, future[["year", *technologies]]])
        mixes.append(
            np.stack(
                [np.interp(years, knots.year, knots[t]) for t in technologies], axis=1
            )
        )
        countries.append(row.country)
        last_years.append(last)
        regions.append(row.projection_region)
        kinds.append(row.projection_kind)
    return xr.DataArray(
        np.stack(mixes),
        dims=("country", "year", "variable"),
        coords={
            "country": countries,
            "year": years,
            "variable": technologies,
            "history_last_year": ("country", last_years),
            "projection_region": ("country", regions),
            "projection_kind": ("country", kinds),
        },
        attrs={
            "electricity_scenario": scenario,
            "horizon_policy": "hold",
            "boundary": "domestic generation; imports excluded",
            "history_source": "Ember yearly electricity, snapshot 2026-10-09",
            "history_snapshot_year": history_cutoff,
            "projection_source": "JRC GECO 2025, published 2026-06-23",
            "technology_mapping": "electricity_sources.json; coarse LCI proxies",
        },
    )


def get_electricity_mix(scenario=DEFAULT_SCENARIO):
    """Return a private country/year/technology array for a bundled scenario.

    Electricity scenarios are independent of the inventory's IAM impact-factor
    scenario. No network, Excel reader or Brightway installation is required.
    ``legacy`` reproduces the previous, unvalidated source table.
    """
    if scenario not in SCENARIOS:
        raise ValueError(
            f"Electricity scenario must be one of {SCENARIOS}; got {scenario!r}."
        )
    return _load_mix(scenario).copy(deep=True)


def select_electricity_mix(generation, country, fallback=None):
    """Select a country, exposing regional proxies and explicit fallbacks."""
    requested = country
    country = {"UK": "GB", "NM": "NA"}.get(country, country)
    if generation.attrs.get("electricity_scenario") == "legacy":
        country = requested
        if country not in generation.country.values:
            country = "RER"
    elif country not in generation.country.values:
        if fallback is None:
            raise ValueError(
                f"No electricity history for {requested!r}. Supply a custom electricity "
                "mix or an explicit 'electricity fallback country' (e.g. 'GLO')."
            )
        country = fallback
    if country not in generation.country.values:
        raise ValueError(f"Electricity fallback country {country!r} is unavailable.")
    selected = generation.sel(country=country)
    provenance = dict(generation.attrs, requested_country=requested, country=country)
    for name in ("projection_region", "projection_kind", "history_last_year"):
        if name in selected.coords:
            provenance[name] = selected.coords[name].item()
    if country != requested:
        warnings.warn(
            f"Electricity for {requested} uses {country}.",
            ElectricityDataWarning,
            stacklevel=2,
        )
    if provenance.get("projection_kind") in ("regional-proxy", "world-proxy"):
        warnings.warn(
            f"Electricity projections for {country} use the {provenance['projection_region']} "
            f"regional proxy after {provenance['history_snapshot_year']}; this is not a national forecast.",
            ElectricityDataWarning,
            stacklevel=2,
        )
    return selected, provenance


def electricity_source_metadata():
    """Return the bundled attribution, checksums and explicit mapping assumptions."""
    with (ELECTRICITY_DIR / "electricity_sources.json").open(
        encoding="utf-8"
    ) as stream:
        return json.load(stream)
