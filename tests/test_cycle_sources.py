"""Source-trace integrity and physical grade/duration conventions."""

import hashlib
import json

import numpy as np
import pytest

from carculator_utils import DATA_DIR
from carculator_utils.driving_cycles import get_standard_driving_cycle_and_gradient
from carculator_utils.energy_consumption import EnergyConsumptionModel

RECORDS = json.loads(
    (DATA_DIR / "driving_cycles/vecto_cycle_provenance.json").read_text()
)["records"]


@pytest.mark.parametrize("record", RECORDS, ids=lambda r: f"{r['size']}-{r['cycle']}")
def test_packaged_cycle_matches_recorded_primary_source(record):
    speed, grade = get_standard_driving_cycle_and_gradient(
        record["vehicle_type"], [record["size"]], record["cycle"]
    )
    duration = record["duration_seconds"]
    for values, key in [(speed, "speed"), (grade, "grade_fraction")]:
        digest = hashlib.sha256(
            np.asarray(values[:duration, 0], dtype="<f8").tobytes()
        ).hexdigest()
        assert digest == record[key + "_sha256"]
        assert not np.nan_to_num(values[duration:]).any()
    assert speed[:duration].sum() / 3600 == pytest.approx(record["distance_km"])
    model = EnergyConsumptionModel(
        record["vehicle_type"], [record["size"]], ["ICEV-d"], record["cycle"], None
    )
    assert model.driving_time.sum() == duration
    assert model.driving_time[duration - 1].all()
    assert not model.driving_time[duration:].any()
    # Road-normal and vertical projections follow rise/run geometry.
    np.testing.assert_allclose(
        np.sin(model.gradient[:duration, 0]),
        grade[:duration, 0] / np.sqrt(1 + grade[:duration, 0] ** 2),
        atol=1e-15,
    )


def test_duration_mask_is_independent_for_bus_sizes():
    model = EnergyConsumptionModel("bus", ["9m", "13m-coach"], ["ICEV-d"], "bus", None)
    np.testing.assert_array_equal(model.driving_time.sum(axis=0).ravel(), [8072, 17837])
    assert not model.driving_time[8072, 0, 0, 0, 0]
    assert model.driving_time[8072, 0, 0, 0, 1]
