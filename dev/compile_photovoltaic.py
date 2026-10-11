"""Select attributed IEA PVPS 2026 upstream coefficients for an A/B build."""

import json
from pathlib import Path

import numpy as np

RESOURCE = Path("carculator_utils/data/IAM/photovoltaic.json")


def load_config(root):
    return json.loads((root / RESOURCE).read_text())


def label(config, country):
    return (
        config["activity_name"],
        country,
        "kilowatt hour",
        config["reference_product"],
    )


def aggregate_overrides(config):
    """Global/EU output weights are PV generation, never installed capacity."""
    result = {}
    for region, countries in config["aggregate_members"].items():
        volumes = {
            country: config["generation_gwh"].get(country, 0) for country in countries
        }
        total = sum(volumes.values())
        if total <= 0 or any(not np.isfinite(v) or v < 0 for v in volumes.values()):
            raise ValueError(f"Invalid PV generation volumes for {region}")
        key = label(config, region)
        result[key] = {
            "label": list(key),
            "targets": [
                {"label": list(label(config, country)), "weight": value / total}
                for country, value in volumes.items()
                if value > 0
            ],
            "reason": f"PV generation-weighted {region} aggregate, 2023 IRENA volumes",
            "source": config["generation_source"],
        }
    return result
