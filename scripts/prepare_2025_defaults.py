"""Stage explicit 2025 input records without modifying source repositories.

The starting point is the existing static 2020/2030 interpolation, not an
empirical calibration. Triangular bounds and modes are interpolated as prior
parameters; this does not claim the distribution of independent endpoint draws.
"""

import argparse
import hashlib
import json
import math
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

from carculator_utils.vehicle_input_parameters import validate_parameters

PACKAGES = (
    "carculator",
    "carculator_bus",
    "carculator_truck",
    "carculator_two_wheeler",
)


def motor_efficiency_record(records):
    """Explicit, unfitted component assumption for regeneration and hybrid reuse."""
    return {
        "name": "electric motor efficiency",
        "year": 2025,
        "sizes": sorted({s for r in records.values() for s in r["sizes"]}),
        "powertrain": sorted({p for r in records.values() for p in r["powertrain"]}),
        "amount": 0.9,
        "loc": 0.9,
        "kind": "distribution",
        "uncertainty_type": 1,
        "unit": "unitless",
        "category": "Efficiency",
        "source": "Engineering assumption; not measurement-fitted",
        "comment": (
            "Cycle-average motor/inverter efficiency used for electric traction, "
            "regenerative storage and subsequent electric propulsion in hybrids. "
            "Excludes battery and transmission losses. Aggregate consumption does not identify "
            "this component uniquely; retained as an explicit, adjustable assumption."
        ),
    }


def build_records(original, package=None):
    """Preserve first-record precedence and missing-cell zero interpolation."""
    endpoints = {}
    for identifier, record in original.items():
        if record["year"] not in (2020, 2030):
            continue
        for size in record["sizes"]:
            for powertrain in record["powertrain"]:
                cell = (record["name"], size, powertrain, record["year"])
                endpoints.setdefault(cell, identifier)

    groups = defaultdict(lambda: defaultdict(list))
    for name, size, powertrain in sorted({cell[:3] for cell in endpoints}):
        pair = tuple(
            endpoints.get((name, size, powertrain, year)) for year in (2020, 2030)
        )
        groups[pair][size].append(powertrain)

    result, provenance = {}, {}
    for pair, sizes in groups.items():
        left, right = (original.get(identifier, {}) for identifier in pair)
        record = deepcopy(left or right)
        record["year"] = 2025
        record["amount"] = (left.get("amount", 0) + right.get("amount", 0)) / 2
        record["loc"] = record["amount"]
        distributions = {r.get("uncertainty_type", 1) for r in (left, right) if r}
        if not distributions.issubset({1, 5}):
            raise ValueError(f"Unsupported uncertainty types {distributions}: {pair}")
        if 5 in distributions:
            record["uncertainty_type"] = 5
            uncertainty_note = ""
            effective = []
            for endpoint, other in ((left, right), (right, left)):
                endpoint = deepcopy(endpoint)
                mode = endpoint.get("amount", 0)
                if (
                    not endpoint.get("minimum", mode)
                    <= mode
                    <= endpoint.get("maximum", mode)
                ):
                    reference = other.get("amount", 0)
                    if reference <= 0 or not other.get(
                        "minimum", reference
                    ) <= reference <= other.get("maximum", reference):
                        raise ValueError(
                            f"No valid relative uncertainty prior for {pair}"
                        )
                    for bound in ("minimum", "maximum"):
                        endpoint[bound] = other.get(bound, reference) * mode / reference
                    uncertainty_note = (
                        "An endpoint mode lies outside its published bounds; for this "
                        "2025 prior only, its bounds are reconstructed using the other "
                        "endpoint's relative bounds before interpolation. "
                    )
                effective.append(endpoint)
            for bound in ("minimum", "maximum"):
                record[bound] = (
                    sum(r.get(bound, r.get("amount", 0)) for r in effective) / 2
                )
        else:
            uncertainty_note = ""
            record["uncertainty_type"] = 1
            record.pop("minimum", None)
            record.pop("maximum", None)
        sources = list(dict.fromkeys(r.get("source", "") for r in (left, right) if r))
        record["source"] = " | ".join(sources)
        record["comment"] = (
            "2025 baseline: linear interpolation of the effective 2020 and 2030 "
            "records, before empirical calibration. Triangular modes and bounds "
            "are interpolated. "
            + uncertainty_note
            + (
                "An absent endpoint is zero, matching the existing array contract. "
                if None in pair
                else ""
            )
            + "Endpoint records: "
            + repr(pair)
            + ". "
            + record.get("comment", "")
        )
        # Different endpoint overlaps need not form a Cartesian rectangle.
        # Merge sizes only when their complete powertrain sets are identical.
        rectangles = defaultdict(list)
        for size, powertrains in sizes.items():
            rectangles[tuple(sorted(powertrains))].append(size)
        for powertrains, selected_sizes in rectangles.items():
            identifier = f"baseline-2025-{len(result):04d}-{record['name']}"
            result[identifier] = dict(
                record, sizes=selected_sizes, powertrain=list(powertrains)
            )
            provenance[identifier] = {
                "endpoint_records": pair,
                "missing_endpoint": None in pair,
            }
    identifier = "assumption-2025-electric-motor-efficiency"
    result[identifier] = motor_efficiency_record(original)
    provenance[identifier] = {
        "method": "explicit engineering assumption",
        "fitted": False,
    }
    hybrids = sorted(
        {
            p
            for r in original.values()
            for p in r["powertrain"]
            if p.startswith(("HEV-", "PHEV-c-"))
        }
    )
    if hybrids:
        identifier = "assumption-2025-electric-motor-power-share"
        result[identifier] = dict(
            motor_efficiency_record(original),
            name="electric motor power share",
            powertrain=hybrids,
            amount=0.65,
            loc=0.65,
            category="Power",
            comment="Unfitted motor peak/system power ratio. Hybrid component peaks need not sum to system power; replace with published vehicle-specific ratios where available.",
        )
        provenance[identifier] = {
            "method": "explicit engineering assumption",
            "fitted": False,
        }
    if package == "carculator_bus":
        for key, record in list(result.items()):
            if (
                record["name"] == "combustion power share"
                and "HEV-d" in record["powertrain"]
            ):
                hybrid = deepcopy(record)
                record["powertrain"].remove("HEV-d")
                hybrid.update(
                    powertrain=["HEV-d"],
                    amount=0.7,
                    loc=0.7,
                    uncertainty_type=1,
                    source="Engineering assumption; hybrid architecture baseline, not consumption-fitted",
                    comment="Combustion engine peak/system rating ratio; electric motor is sized independently. Replaces the old hybrid configuration without an electric motor.",
                )
                hybrid.pop("minimum", None)
                hybrid.pop("maximum", None)
                identifier = key + "-hybrid-architecture"
                result[identifier] = hybrid
                provenance[identifier] = {
                    "method": "hybrid architecture assumption",
                    "fitted": False,
                    "replaces": key,
                }
                if not record["powertrain"]:
                    del result[key]
                    del provenance[key]
    if package == "carculator":
        # Depleted mode keeps the same physical battery as electric mode.
        for key, record in list(result.items()):
            if (
                record["name"] == "battery discharge efficiency"
                and "PHEV-e" in record["powertrain"]
            ):
                clone = deepcopy(record)
                clone["powertrain"] = [
                    p for p in ("PHEV-c-p", "PHEV-c-d") if p in hybrids
                ]
                if not clone["powertrain"]:
                    continue
                clone["comment"] = (
                    "2025 PHEV mode consistency: same battery discharge efficiency as PHEV-e. The depleted mode retains its battery and regenerative capability. "
                    + clone.get("comment", "")
                )
                identifier = key + "-depleted-phev"
                result[identifier] = clone
                provenance[identifier] = {
                    "method": "same battery across PHEV operating modes",
                    "source_2025_record": key,
                    "fitted": False,
                }
    identifier = "assumption-2025-electric-transmission-efficiency"
    result[identifier] = dict(
        motor_efficiency_record(original),
        name="electric transmission efficiency",
        amount=0.97,
        loc=0.97,
        comment="Unfitted electric drivetrain mechanical transmission efficiency; excludes motor/inverter and battery losses.",
    )
    provenance[identifier] = {
        "method": "explicit engineering assumption",
        "fitted": False,
    }
    # Replace historical composite loss factors only for electrified vehicles.
    # Battery charge/discharge are internal storage losses; AC/DC conversion is
    # represented separately by charger efficiency, never in regeneration.
    for key, record in list(result.items()):
        name = record["name"]
        if name not in {
            "battery charge efficiency",
            "battery discharge efficiency",
            "charger efficiency",
        }:
            continue
        applicable = [
            p
            for p in record["powertrain"]
            if p.startswith(("BEV", "HEV", "PHEV")) or p == "FCEV"
        ]
        if not applicable:
            continue
        updated = deepcopy(record)
        updated["powertrain"] = applicable
        remaining = [p for p in record["powertrain"] if p not in applicable]
        new_key = key + "-component" if remaining else key
        if remaining:
            record["powertrain"] = remaining
        value = 0.90 if name == "charger efficiency" else math.sqrt(0.97)
        updated.update(amount=value, loc=value, uncertainty_type=1)
        updated.pop("minimum", None)
        updated.pop("maximum", None)
        updated["source"] = (
            "Engineering assumption; AC input to battery-terminal DC, not fitted"
            if name == "charger efficiency"
            else "https://github.com/NatLabRockies/fastsim/blob/63808be8d09cb191047b536a2b9b7f883dbbd0c3/python/fastsim/resources/vehdb/2022_Tesla_Model_3_RWD.csv"
        )
        updated["comment"] = "2025 component prior, not consumption-fitted. " + (
            "Charger conversion excludes internal battery losses."
            if name == "charger efficiency"
            else "Symmetric one-way storage efficiency sqrt(0.97), following FASTSim's battery round-trip prior. Excludes charger and motor/inverter. Transfer to other vehicles is an engineering assumption, not independent validation."
        )
        result[new_key] = updated
        provenance[new_key] = {
            "method": "component-boundary prior",
            "fitted": False,
            "replaces": key,
            "source": updated["source"],
        }
    validate_parameters(result, check_duplicates=True)
    return result, provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repositories-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    for package in PACKAGES:
        source = (
            args.repositories_root / package / package / "data/default_parameters.json"
        )
        raw = source.read_bytes()
        original = json.loads(raw)
        if any(record["year"] == 2025 for record in original.values()):
            raise ValueError(
                f"{source} already has 2025 records; refusing to overwrite calibration."
            )
        records, provenance = build_records(original, package)
        combined = {**original, **records}
        validate_parameters(combined)
        folder = args.output / package
        folder.mkdir()
        (folder / "default_parameters.json").write_text(
            json.dumps(combined, indent=4) + "\n"
        )
        (folder / "defaults_2025_provenance.json").write_text(
            json.dumps(
                {
                    "method": "2025 interpolated inputs with explicit component-efficiency priors; not universally measurement-calibrated",
                    "source_sha256": hashlib.sha256(raw).hexdigest(),
                    "original_record_count": len(original),
                    "new_record_count": len(records),
                    "records": provenance,
                },
                indent=2,
            )
            + "\n"
        )
        print(f"{package}: staged {len(records)} new 2025 records")


if __name__ == "__main__":
    main()
