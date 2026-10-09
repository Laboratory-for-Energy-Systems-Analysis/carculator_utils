"""Build offline electricity resources from locally downloaded, attributed sources.

Requires the test extra (pandas/openpyxl). This script never downloads data.
Example commands and source URLs are in docs/electricity_scenarios.rst.
"""

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pycountry
import yaml

SOURCE_DIR = (
    Path(__file__).resolve().parents[1] / "carculator_utils" / "data" / "electricity"
)
EMBER_MAP = {
    "Hydro": "Hydro",
    "Nuclear": "Nuclear",
    "Gas": "Gas",
    "Solar": "Solar",
    "Wind": "Wind",
    "Bioenergy": "Biomass",
    "Coal": "Coal",
    "Other fossil": "Oil",
    "Other renewables": "Geothermal",
}
GECO_MAP = {
    "Coal": "Coal",
    "Oil": "Oil",
    "Gas": "Gas",
    "Biomass & Waste": "Biomass",
    "Nuclear": "Nuclear",
    "Hydro": "Hydro",
    "Wind": "Wind",
    "Solar": "Solar",
    "Other": "Geothermal",
}
GECO_SCENARIOS = {
    "Reference": "geco-2025-reference",
    "NDC-LTS": "geco-2025-ndc-lts",
    "15C": "geco-2025-1.5c",
}
NATIVE_REGIONS = {
    "AR": "Argentina",
    "AU": "Australia",
    "BR": "Brazil",
    "CA": "Canada",
    "CH": "Switzerland",
    "CL": "Chile",
    "CN": "China",
    "EG": "Egypt",
    "GB": "United Kingdom",
    "ID": "Indonesia",
    "IN": "India",
    "IR": "Iran",
    "IS": "Iceland",
    "JP": "Japan",
    "KR": "South Korea",
    "MX": "Mexico",
    "MY": "Malaysia",
    "NO": "Norway",
    "NZ": "New Zealand",
    "RU": "Russian Federation",
    "SA": "Saudi Arabia",
    "TH": "Thailand",
    "TR": "Türkiye",
    "UA": "Ukraine",
    "US": "United States",
    "VN": "Vietnam",
    "ZA": "South Africa",
}
# GECO 2025 report, Annex 1, tables 2-3 (pp. 167-168), supplemented by
# explicitly marked proxies for geographies absent from that printed table.
# A member of a model region still uses a regional, not a national, forecast.
REGIONAL_PROXIES = {
    "European Union": "AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE RER",
    "Rest of Balkans": "AL BA MD ME MK RS XK",
    "Rest of CIS": "AM AZ BY GE KZ KG TJ TM UZ",
    "Rest of South Asia": "AF BD BT LK MV NP PK SC",
    "Rest of South-East Asia": "BN KH LA MM MN KP PH SG TW TL",
    "Rest of Persian Gulf": "BH IQ KW OM QA AE YE",
    "Mediterranean Middle-East": "IL JO LB PS SY",
    "Morocco and Tunisia": "MA TN",
    "Algeria and Libya": "DZ LY",
    "Rest of South America": "BO CO EC GY PY PE SR UY VE GF FK",
    "Rest of Central America": "BM ST",
    "China": "HK MO",
}


def technologies():
    with (SOURCE_DIR / "elec_tech_map.yaml").open(encoding="utf-8") as stream:
        return list(yaml.safe_load(stream))


def normalized_generation(values, total, context, absolute_tolerance=0.005):
    """Validate TWh balances, then convert mutually exclusive output to shares."""
    values = np.asarray(values, dtype=float)
    if (
        not np.isfinite(values).all()
        or (values < 0).any()
        or not np.isfinite(total)
        or total <= 0
    ):
        raise ValueError(f"Invalid generation at {context}.")
    if abs(values.sum() - total) > max(absolute_tolerance, total * 1e-5):
        raise ValueError(
            f"Generation balance at {context}: components {values.sum()}, total {total}."
        )
    if values.sum() <= 0:
        raise ValueError(f"No generation components at {context}.")
    return values / values.sum()


def country_code(area, iso3):
    if area in ("Europe", "World"):
        return {"Europe": "RER", "World": "GLO"}[area]
    if iso3 == "XKX":
        return "XK"
    record = pycountry.countries.get(alpha_3=iso3)
    if record is None:
        raise ValueError(f"Unmapped Ember geography {area!r}, {iso3!r}.")
    return record.alpha_2


def read_ember(path, allow_exclusions=False):
    """Extract disjoint generation categories; never use capacity or aggregates."""
    source = pd.read_csv(path)
    required = {
        "Area",
        "ISO 3 code",
        "Year",
        "Area type",
        "Electricity source",
        "Generation (TWh)",
        "Ember region",
    }
    if not required.issubset(source):
        raise ValueError(f"Ember schema is missing {required - set(source)}.")
    source = source.loc[
        (source["Area type"] == "Country or economy")
        | source.Area.isin(["Europe", "World"])
    ]
    keys = ["Area", "Year", "Electricity source"]
    if source.duplicated(keys).any():
        raise ValueError("Duplicate Ember area/year/source records.")
    allowed = set(EMBER_MAP) | {
        "Total generation",
        "Demand",
        "Net imports",
        "Wind and solar",
        "Renewables",
        "Hydro, bioenergy and other renewables",
        "Clean",
        "Fossil",
    }
    if set(source["Electricity source"]) - allowed:
        raise ValueError("Unmapped Ember electricity source; review the source schema.")
    techs = technologies()
    records, audit, areas = [], [], {}
    for (area, year), group in source.groupby(["Area", "Year"], sort=True):
        code = country_code(area, group["ISO 3 code"].iloc[0])
        areas[code] = {
            "source_area": area,
            "ember_region": group["Ember region"].iloc[0],
        }
        series = group.set_index("Electricity source")["Generation (TWh)"]
        total = series.get("Total generation", np.nan)
        # An absent fuel row can mean no output. Accept zero only when the
        # independently reported total confirms the complete component balance.
        components = series.reindex(EMBER_MAP).fillna(0)
        context = {"country": code, "year": int(year)}
        if total == 0 and (components == 0).all():
            audit.append(dict(context, reason="zero domestic generation"))
            continue
        if (components < 0).any():
            if not allow_exclusions:
                raise ValueError(
                    f"Negative Ember generation at {context}; inspect source or explicitly allow exclusions."
                )
            audit.append(
                dict(
                    context,
                    reason="negative source generation; entire country-year excluded",
                    values=components.loc[components < 0].to_dict(),
                )
            )
            continue
        fractions = normalized_generation(components, total, context)
        record = dict(context, **dict.fromkeys(techs, 0.0))
        for source_tech, fraction in zip(EMBER_MAP, fractions):
            record[EMBER_MAP[source_tech]] += fraction
        records.append(record)
    history = pd.DataFrame(records)[["country", "year", *techs]].sort_values(
        ["country", "year"]
    )
    return history, areas, audit


def read_geco_sheet(frame, scenario, region, other_residual=False, audit=None):
    """Read the gross-generation block and subtract nested CCS from its parent."""
    labels = frame.iloc[:, 0].fillna("").astype(str).str.strip()
    starts = np.flatnonzero(labels.str.startswith("Gross Elec. Generation"))
    if len(starts) != 1:
        raise ValueError(f"Expected one GECO generation section: {scenario}, {region}.")
    start = starts[0]
    stops = np.flatnonzero(labels.str.startswith("Share of Renewables"))
    stop = next((i for i in stops if i > start), None)
    if stop is None:
        raise ValueError(f"Missing GECO generation section end: {region}.")
    # Locate year headings, rather than depending on workbook row offsets.
    headings = [
        i
        for i in range(start)
        if list(frame.iloc[i, 1:8]) == [2023, 2030, 2035, 2040, 2050, 2060, 2070]
    ]
    if len(headings) != 1:
        raise ValueError(f"Unexpected GECO year schema: {region}.")
    techs = technologies()
    records = []
    # 2023 is a model calibration year; observed history is supplied by Ember.
    for col, year in enumerate([2030, 2035, 2040, 2050, 2060, 2070], start=2):
        amounts = dict.fromkeys(techs, 0.0)
        parent, seen, seen_ccs = None, set(), set()
        for i in range(start + 1, stop):
            label, amount = labels.iloc[i], float(frame.iloc[i, col])
            if label == "of which CCS":
                if parent not in ("Coal", "Gas", "Biomass") or parent in seen_ccs:
                    raise ValueError(
                        f"Unexpected GECO CCS subgroup at {region}, {year}."
                    )
                amounts[parent] -= amount
                amounts[parent + " CCS"] += amount
                seen_ccs.add(parent)
            elif label in GECO_MAP and label not in seen:
                parent = GECO_MAP[label]
                amounts[parent] += amount
                seen.add(label)
            else:
                raise ValueError(
                    f"Unmapped or duplicate GECO generation category {label!r}."
                )
        if seen != set(GECO_MAP):
            raise ValueError(
                f"Incomplete GECO technology coverage at {region}, {year}."
            )
        total = float(frame.iloc[start, col])
        reported_other = amounts["Geothermal"]
        residual = total - (sum(amounts.values()) - reported_other)
        if other_residual:
            if residual < 0 or residual > reported_other + max(0.005, total * 1e-5):
                raise ValueError(
                    f"GECO Other cannot reconcile at {scenario}, {region}, {year}."
                )
            amounts["Geothermal"] = residual
        if audit is not None:
            audit.append(
                dict(
                    scenario=scenario,
                    region=region,
                    year=year,
                    reported_total_twh=total,
                    reported_other_twh=reported_other,
                    residual_other_twh=residual,
                    other_surplus_twh=reported_other - residual,
                )
            )
        shares = normalized_generation(
            list(amounts.values()), total, (scenario, region, year)
        )
        records.append(
            dict(
                scenario=scenario, region=region, year=year, **dict(zip(techs, shares))
            )
        )
    return records


def read_geco(path, other_residual=False):
    records, audit = [], []
    with ZipFile(path) as archive:
        for suffix, scenario in GECO_SCENARIOS.items():
            names = [
                n for n in archive.namelist() if n.endswith(f"GECO 2025 {suffix}.xlsx")
            ]
            if len(names) != 1:
                raise ValueError(f"Missing or duplicate GECO workbook for {scenario}.")
            book = pd.ExcelFile(BytesIO(archive.read(names[0])))
            for region in book.sheet_names:
                records.extend(
                    read_geco_sheet(
                        pd.read_excel(book, sheet_name=region, header=None),
                        scenario,
                        region,
                        other_residual,
                        audit,
                    )
                )
    return pd.DataFrame(records).sort_values(
        ["scenario", "region", "year"]
    ), pd.DataFrame(audit)


def geography_mapping(history, areas, projection_regions):
    records = []
    for code in sorted(history.country.unique()):
        area = areas[code]
        region, kind = NATIVE_REGIONS.get(code), "country"
        if region is None:
            kind = "regional-proxy"
            region = next(
                (
                    r
                    for r, members in REGIONAL_PROXIES.items()
                    if code in members.split()
                ),
                None,
            )
            if region is None:
                region = {
                    "Africa": "Rest of Sub-Saharan Africa",
                    "Oceania": "Rest of Pacific",
                    "Latin America and Caribbean": "Rest of Central America",
                }.get(area["ember_region"], "World")
            if region == "World":
                kind = "aggregate" if code == "GLO" else "world-proxy"
        if region not in projection_regions:
            raise ValueError(f"Projection geography {region!r} is missing.")
        records.append(
            dict(
                country=code,
                source_area=area["source_area"],
                projection_region=region,
                projection_kind=kind,
            )
        )
    return pd.DataFrame(records)


def audit_tyndp(path):
    """Preserve disaggregated TWh outputs and explicitly flag unresolved LCI links.

    The output is an audit resource, not an accepted runtime electricity scenario.
    Storage, unserved demand and curtailment must not be normalized as generation.
    """
    import openpyxl

    direct = {
        "Wind Onshore": "Wind",
        "Wind Offshore Radial": "Wind, offshore",
        "Wind Offshore Hub": "Wind, offshore",
        "Solar PV": "Solar",
        "Solar CSP": "Solar, thermal",
        "Run of River": "Hydro",
        "Pondage": "Hydro, reservoir",
        "Reservoir": "Hydro, reservoir",
        "Nuclear": "Nuclear",
        "Crude Oil": "Oil",
    }
    exclusions = {
        "PS Turbine": "storage output",
        "ENS": "unserved demand",
        "RES Curtailment": "curtailment",
    }
    unresolved = {
        "SRES Electricity",
        "Biofuel",
        "Other RES",
        "Natural Gas",
        "Coal",
        "Hydrogen GT",
        "Fuel Cell",
        "Other Non RES",
        "Adequacy Units",
    }
    records = []
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet in book.worksheets:
            if sheet.title == "Info":
                continue
            rows = list(sheet.values)
            year, columns = None, []
            for col, value in enumerate(rows[2]):
                if isinstance(value, (int, float)):
                    year = int(value)
                if rows[3][col] == "Weighted WS":
                    columns.append((col, year))
            if [year for _, year in columns] != [2030, 2035, 2040, 2050]:
                raise ValueError(f"Unexpected TYNDP year schema: {sheet.title}.")
            start = next(i for i, r in enumerate(rows) if r[0] == "Generation [TWh]")
            stop = next(
                i
                for i in range(start + 1, len(rows))
                if rows[i][0] == "Electricity - Flexibility"
            )
            for row in rows[start + 1 : stop]:
                label = row[1].strip()
                if label not in set(direct) | set(exclusions) | unresolved:
                    raise ValueError(f"Unknown TYNDP generation label {label!r}.")
                for col, year in columns:
                    value = row[col]
                    records.append(
                        dict(
                            area=sheet.title,
                            year=year,
                            technology=label,
                            generation_twh=value,
                            mapping=direct.get(label, ""),
                            status=(
                                "not reported"
                                if value is None
                                else exclusions.get(
                                    label,
                                    (
                                        "candidate mapping"
                                        if label in direct
                                        else "unresolved LCI mapping"
                                    ),
                                )
                            ),
                        )
                    )
    finally:
        book.close()
    return pd.DataFrame(records)


def build(ember, geco, tyndp, output, allow_exclusions=False, other_residual=False):
    history, areas, exclusions = read_ember(ember, allow_exclusions)
    projections, geco_audit = read_geco(geco, other_residual)
    geography = geography_mapping(history, areas, set(projections.region))
    tyndp_audit = audit_tyndp(tyndp)
    output.mkdir(parents=True, exist_ok=True)
    resources = [
        ("electricity_history.csv", history),
        ("electricity_projections.csv", projections),
        ("electricity_geographies.csv", geography),
        ("tyndp_2026_mapping_audit.csv", tyndp_audit),
        ("geco_2025_balance_audit.csv", geco_audit),
    ]
    for name, frame in resources:
        frame.to_csv(
            output / name,
            sep=";",
            index=False,
            float_format="%.12g",
            lineterminator="\n",
        )
    source_info = [
        (
            "ember",
            ember,
            "Ember yearly electricity, snapshot 2026-10-09",
            "https://files.ember-energy.org/public-downloads/generation/outputs/release_generation_yearly_global.csv",
        ),
        (
            "geco",
            geco,
            "JRC GECO 2025, workbooks published 2026-06-23",
            "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GECOutlook/GECO2025/GECO2025.zip",
        ),
        (
            "tyndp",
            tyndp,
            "TYNDP 2026 draft NT+ KPI dashboard, snapshot 2026-10-09",
            "https://2026-data.entsos-tyndp-scenarios.eu/output/model-results/kpi-dashboards/NT%2B_KPI_Dashboard.xlsx",
        ),
    ]
    metadata = {
        "schema_version": 1,
        "default_scenario": "geco-2025-reference",
        "sources": {
            key: {
                "title": title,
                "url": url,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "license": "CC BY 4.0",
                "attribution": title,
            }
            for key, path, title, url in source_info
        },
        "ember_technology_proxies": EMBER_MAP,
        "geco_technology_proxies": GECO_MAP,
        "geco_other_residual": other_residual,
        "geography_reference": {
            "url": "https://publications.jrc.ec.europa.eu/repository/bitstream/JRC145985/JRC145985_01.pdf",
            "location": "Annex 1, tables 2-3, pp. 167-168",
            "extensions": "PS -> Mediterranean Middle-East; TL -> Rest of South-East Asia; GF/FK -> Rest of South America; remaining African/Oceanian/Latin American territories -> corresponding regional proxy; otherwise World. RER -> EU27.",
        },
        "assumptions": [
            "Generation shares only; electricity imports, storage losses and supplier contracts are not resolved.",
            "Coarse categories use existing LCI proxies: oil for other fossil; geothermal for other renewables/GECO Other; wood CHP for bioenergy/biomass and waste; run-of-river for hydro; onshore wind and rooftop PV for aggregate wind/solar; conventional gas for aggregate gas; hard coal for aggregate coal.",
            "CCS is subtracted from the parent fuel total and mapped separately; biomass/waste CCS uses Biomass CCS.",
            "GECO's reported nine generation categories do not sum to its gross-generation total. With --geco-other-residual, preserve the eight named fuel groups and use total minus those groups for Other. Reported Other, its residual and surplus remain in geco_2025_balance_audit.csv. This explicit reconciliation assumes the reported total and named fuels are authoritative; the surplus is not assigned an invented technology or silently normalized.",
            "Geographic assignments follow GECO 2025 Annex 1 where listed; extensions are identified separately. Regional trajectories are proxies, not national forecasts.",
            "Annual country observations are held to the snapshot's final historical year (2025) when recent observations are unavailable, so historical years do not depend on the future scenario. Linear interpolation then joins that anchor to the first GECO endpoint. Endpoints are held outside the horizon.",
            "2025 Ember values can include estimates. Missing component rows are zero only if reported total generation reconciles within source rounding precision.",
            "Negative-generation country-years are excluded explicitly below; they are not clipped. Other years and subsequent interpolation remain available.",
            "RER history is Ember Europe; its future uses EU27 as a regional proxy. GLO uses World.",
            "TYNDP is an audit-only candidate: unresolved fuels and hydrogen cannot be silently assigned fossil or zero-impact generation.",
            "Existing ecoinvent 3.6 loss multipliers and generic generation inventories are unchanged; missing country losses are disclosed at runtime.",
        ],
        "excluded_history": exclusions,
        "history_records": len(history),
        "geographies": len(geography),
        "projection_scenarios": sorted(projections.scenario.unique()),
        "resources": {
            name: hashlib.sha256((output / name).read_bytes()).hexdigest()
            for name, _ in resources
        },
    }
    (output / "electricity_sources.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ember", type=Path, required=True)
    parser.add_argument("--geco", type=Path, required=True)
    parser.add_argument("--tyndp", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-history-exclusions",
        action="store_true",
        help="Exclude and record whole country-years containing negative source generation",
    )
    parser.add_argument(
        "--geco-other-residual",
        action="store_true",
        help="Explicitly reconcile GECO Other to gross generation; preserve the discrepancy audit",
    )
    args = parser.parse_args()
    metadata = build(
        args.ember,
        args.geco,
        args.tyndp,
        args.output,
        args.allow_history_exclusions,
        args.geco_other_residual,
    )
    print(
        f"Built {metadata['history_records']} observations, {metadata['geographies']} geographies, "
        f"3 scenarios; {len(metadata['excluded_history'])} explicitly excluded records."
    )


if __name__ == "__main__":
    main()
