"""Successful sizing or matching a cycle name never establishes validation."""

import runpy
from pathlib import Path

import pytest

MODULE = runpy.run_path(str(Path(__file__).parents[1] / "scripts/energy_evidence.py"))


def matched():
    review = {
        name: {"matched": True, "source": "test report p. 3"}
        for name in MODULE["REQUIRED_MATCHES"]
    }
    review.update(
        cycle_sha256="abc",
        model_energy_field="model_charging",
        energy_boundary_source="meter report p. 4",
        role="held_out",
    )
    return (
        {"unit": "kWh/100 km", "qualification": review},
        {"model_comparison": {"target_driving_mass": 1500}},
        {"cycle_profile_sha256": "abc", "energy_input_driving_mass_kg": 1500},
    )


def test_unreviewed_observation_remains_screening_even_when_model_completes():
    result = MODULE["qualify"](
        {"unit": "L/100 km"}, {}, {"eligible_for_comparison": True}
    )
    assert result["status"] == "screening"
    assert not result["eligible_for_independent_validation"]
    assert result["reasons"]


@pytest.mark.parametrize(
    "fault", ["cycle", "mass", "boundary", "role", *MODULE["REQUIRED_MATCHES"]]
)
def test_each_matching_requirement_is_necessary(fault):
    observation, dataset, run = matched()
    if fault == "cycle":
        run["cycle_profile_sha256"] = "different"
    elif fault == "mass":
        run["energy_input_driving_mass_kg"] = 1600
    elif fault == "boundary":
        observation["qualification"]["model_energy_field"] = "model_fuel"
    elif fault == "role":
        observation["qualification"]["role"] = "unknown"
    else:
        observation["qualification"][fault]["source"] = ""
    assert MODULE["qualify"](observation, dataset, run)["status"] == "screening"


def test_calibration_observation_is_not_independent_validation():
    observation, dataset, run = matched()
    assert MODULE["qualify"](observation, dataset, run)[
        "eligible_for_independent_validation"
    ]
    observation["qualification"]["role"] = "calibration"
    result = MODULE["qualify"](observation, dataset, run)
    assert result["eligible_for_calibration"]
    assert not result["eligible_for_independent_validation"]
    assert (
        MODULE["summarize"]([{"evidence_qualification": result}])["validation_passed"]
        is None
    )
