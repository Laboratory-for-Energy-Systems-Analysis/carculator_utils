"""Separate screening, calibration and independent energy-validation evidence."""

import math

REQUIRED_MATCHES = (
    "vehicle_and_model_year",
    "road_load",
    "ambient_and_conditioning",
    "auxiliaries",
    "fuel_or_battery_properties",
)
ENERGY_FIELDS = {
    "L/100 km": {"model_fuel"},
    "kg/100 km": {"model_fuel"},
    "kWh/100 km": {"model_onboard", "model_charging", "model_stored_energy"},
}


def qualify(observation, dataset, run):
    """Require reviewed matching evidence before using a residual for calibration.

    A matching cycle name alone is insufficient. Review metadata are explicit
    declarations with source references, not automatically verified observations.
    """
    review = observation.get("qualification", dataset.get("qualification", {}))
    reasons = []
    expected = review.get("cycle_sha256")
    actual = run.get("cycle_profile_sha256")
    if not expected or expected != actual:
        reasons.append(
            "Measured test speed/grade trace is not independently matched by hash."
        )
    for field in REQUIRED_MATCHES:
        evidence = review.get(field, {})
        if evidence.get("matched") is not True or not evidence.get("source"):
            reasons.append(f"Missing reviewed match and source: {field}.")
    target = dataset.get("model_comparison", {}).get("target_driving_mass")
    mass = run.get("energy_input_driving_mass_kg")
    if (
        target is None
        or mass is None
        or not math.isfinite(mass)
        or abs(mass - target) >= 0.1
    ):
        reasons.append("Driving mass has not been matched within 0.1 kg.")
    boundary = review.get("model_energy_field")
    if boundary not in ENERGY_FIELDS.get(
        observation.get("unit"), set()
    ) or not review.get("energy_boundary_source"):
        reasons.append(
            "Measured energy boundary lacks a reviewed matching model field."
        )
    role = review.get("role")
    if role not in ("calibration", "held_out"):
        reasons.append("Observation has no declared calibration/held-out role.")
    return {
        "status": "screening" if reasons else role,
        "eligible_for_calibration": not reasons and role == "calibration",
        "eligible_for_independent_validation": not reasons and role == "held_out",
        "model_energy_field": boundary if not reasons else None,
        "reasons": reasons,
    }


def summarize(comparisons):
    """Keep unmatched observations out of quantitative validation claims."""
    counts = {
        key: sum(row["evidence_qualification"]["status"] == key for row in comparisons)
        for key in ("screening", "calibration", "held_out")
    }
    return {
        "counts": counts,
        "validation_passed": None,
        "note": "Eligibility is not validation success. No fixed error threshold or automatic parameter fitting is applied.",
    }
