"""Select bundled IEA PVPS 2026 upstream electricity impact coefficients."""

import json
import warnings

from . import DATA_DIR
from .electricity import ElectricityDataWarning


def select_photovoltaic(country, configuration, inputs):
    """Select a country/aggregate supplier without changing generation shares.

    Coefficients cover one kWh generated at the plant. Delivery infrastructure
    and losses remain the responsibility of the inventory electricity market.
    ``solar photovoltaic country`` can specify the supply location independently
    of vehicle operation, including when a custom electricity mix is provided.
    """
    with (DATA_DIR / "IAM/photovoltaic.json").open(encoding="utf-8") as stream:
        data = json.load(stream)
    version = configuration.get("solar photovoltaic", data["version"])
    if version not in {data["version"], "legacy"}:
        raise ValueError("Solar photovoltaic must be 'iea-pvps-2026' or 'legacy'.")
    if version == "legacy":
        if "solar photovoltaic country" in configuration:
            raise ValueError("Legacy solar photovoltaic uses its fixed CH supplier.")
        key = tuple(data["legacy_label"])
        provenance = {
            "solar_inventory": "legacy Swiss 3 kWp multi-Si rooftop proxy",
            "solar_location": "CH",
            "solar_source": "ecoinvent 3.12 cutoff",
        }
    else:
        selected = configuration.get("solar photovoltaic country", country)
        selected = {"UK": "GB", "NM": "NA", "EU": "EU27"}.get(selected, selected)
        available = set(data["countries"]) | set(data["aggregate_members"])
        if selected not in available:
            if "solar photovoltaic country" in configuration:
                raise ValueError(
                    f"Unsupported solar photovoltaic country: {selected!r}."
                )
            warnings.warn(
                f"Solar photovoltaic supply for {country} uses the generation-weighted GLO proxy.",
                ElectricityDataWarning,
                stacklevel=2,
            )
            selected = "GLO"
        key = (
            data["activity_name"],
            selected,
            "kilowatt hour",
            data["reference_product"],
        )
        provenance = {
            "solar_inventory": data["version"],
            "solar_location": selected,
            "solar_source": data["source"],
            "solar_boundary": data["coefficient_boundary"],
        }
        if selected in data["aggregate_members"]:
            provenance.update(
                solar_weighting_source=data["generation_source"],
                solar_weighting_year=data["generation_year"],
            )
    if key not in inputs:
        raise KeyError(f"Missing photovoltaic coefficient supplier: {key!r}.")
    return key, provenance
