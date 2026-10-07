"""Verify packaged cycles against the recorded original VECTO simulation files.

Run with matching sibling checkouts containing their ``dev/*.vmod`` sources.
The source SHA-256 checks prevent silently substituting another simulation.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from carculator_utils import DATA_DIR
from carculator_utils.driving_cycles import get_standard_driving_cycle_and_gradient


def audit(source_root):
    metadata = json.loads(
        (DATA_DIR / "driving_cycles/vecto_cycle_provenance.json").read_text()
    )
    results = []
    for record in metadata["records"]:
        path = source_root / record["source_repository"] / record["source_file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["source_sha256"]:
            raise ValueError(f"Source checksum mismatch: {path}")
        frame = pd.read_csv(path, skiprows=1)
        frame.columns = frame.columns.str.strip()
        duration = record["duration_seconds"]
        np.testing.assert_array_equal(frame["dt [s]"], 1)
        np.testing.assert_array_equal(frame["time [s]"], np.arange(1, duration + 1))
        speed, grade = get_standard_driving_cycle_and_gradient(
            record["vehicle_type"], [record["size"]], record["cycle"]
        )
        np.testing.assert_array_equal(speed[:duration, 0], frame["v_act [km/h]"])
        np.testing.assert_allclose(
            grade[:duration, 0], frame["grad [%]"] / 100, rtol=0, atol=1e-12
        )
        np.testing.assert_array_equal(np.nan_to_num(speed[duration:]), 0)
        np.testing.assert_array_equal(np.nan_to_num(grade[duration:]), 0)
        results.append(
            {
                "vehicle_type": record["vehicle_type"],
                "size": record["size"],
                "cycle": record["cycle"],
                "duration_seconds": duration,
                "distance_km": float(np.nansum(speed) / 3600),
                "net_elevation_m": float(
                    np.nansum(speed / 3.6 * grade / np.sqrt(1 + grade**2))
                ),
            }
        )
    return {
        "verified": len(results),
        "cycles": results,
        "unresolved": metadata["unresolved"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.source_root)
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
