"""Default records have unambiguous scopes without changing effective values."""

import json
from itertools import product

import numpy as np
import pytest

from carculator_utils.vehicle_input_parameters import (
    VehicleInputParameters,
    validate_parameters,
)


@pytest.mark.family
@pytest.mark.parametrize(
    "package,prefix",
    [
        ("carculator", "Car"),
        ("carculator_bus", "Bus"),
        ("carculator_truck", "Truck"),
        ("carculator_two_wheeler", "TwoWheeler"),
    ],
)
def test_defaults_have_unique_cells_and_preserve_effective_distributions(
    package, prefix
):
    module = pytest.importorskip(package)
    inputs = getattr(module, prefix + "InputParameters")()
    records = json.loads(inputs.DEFAULT.read_text())
    validate_parameters(records, check_duplicates=True)
    provenance = inputs.DEFAULT.with_name("overlap_resolution_provenance.json")
    if not provenance.exists():
        return
    audit = json.loads(provenance.read_text())
    # The full-cell hash in the audit is a historical migration check, not a
    # freeze on future, explicitly sourced inputs (e.g. new Human cost cells).
    # Retained split records must still have their original physical metadata.
    for original_id, identifiers in audit["replacement_record_ids"].items():
        original = audit["original_records"][original_id]
        expected = {
            k: v
            for k, v in original.items()
            if k not in ("sizes", "powertrain", "uncertainty_group")
        }
        for identifier in identifiers:
            record = records[identifier]
            assert {
                k: v
                for k, v in record.items()
                if k not in ("sizes", "powertrain", "uncertainty_group")
            } == expected
            assert set(product(record["sizes"], record["powertrain"])) <= set(
                product(original["sizes"], original["powertrain"])
            )
    inputs.stochastic(16, seed=381)
    for identifiers in audit["replacement_record_ids"].values():
        for identifier in identifiers[1:]:
            np.testing.assert_array_equal(
                inputs.values[identifiers[0]], inputs.values[identifier]
            )


def test_overlapping_bundled_defaults_are_rejected(tmp_path):
    record = dict(
        name="mass", amount=10, sizes=["Small"], powertrain=["BEV"], year=2025
    )
    path = tmp_path / "defaults.json"
    path.write_text(json.dumps({"first": record, "second": record}))

    class Inputs(VehicleInputParameters):
        DEFAULT = path

    with pytest.raises(ValueError, match="duplicate cell.*Small.*BEV.*2025"):
        Inputs(extra=[])
