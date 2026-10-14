"""Recover original naming/compatibility recipes from a pinned Premise revision.

The source workbooks already live in Premise's Git history. Keeping their
revision and byte hashes avoids depending on a disposable 13 MB audit export.
This is a development-only reader; it never changes either checkout.
"""

import hashlib
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_premise_vehicle_workbooks import read_workbook

REVISION = "a7c19af5251532ccccbc3d36f88504c0bbd2cc46"
WORKBOOKS = {
    "car": (
        "lci-pass_cars.xlsx",
        "80875656287929e09be1d1ebf74a774d345d0fbfdaa11ad22829fe3a1e183520",
    ),
    "truck": (
        "lci-trucks.xlsx",
        "0b39c6311dc71dd13254a62901260e23747205cdd4f8871f952c1e77f4128fba",
    ),
}


def load_baseline(family, premise=None):
    """Return original workbook datasets and verified source SHA-256."""
    premise = (
        Path(premise) if premise else Path(__file__).resolve().parents[2] / "premise"
    )
    filename, expected = WORKBOOKS[family]
    try:
        content = subprocess.check_output(
            [
                "git",
                "-C",
                str(premise),
                "show",
                f"{REVISION}:premise/data/additional_inventories/{filename}",
            ],
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Premise Git revision {REVISION} is required to regenerate vehicle identities; "
            "fetch that history in the sibling checkout."
        ) from exc
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected:
        raise ValueError(f"Original {filename} hash mismatch: {actual} != {expected}")
    with TemporaryDirectory(prefix="premise-vehicle-baseline-") as directory:
        path = Path(directory) / filename
        path.write_bytes(content)
        datasets, _, missing = read_workbook(path)
    if missing:
        raise ValueError(f"Original {filename} has missing formula caches")
    return datasets, actual
