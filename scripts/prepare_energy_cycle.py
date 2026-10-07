"""Convert a DriveCAT seconds/mph CSV to the audit's one-second km/h format.

No speed or energy fitting is performed. The adjacent provenance JSON records
the sampling effects; agreement of summary metrics is not model validation.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-url", required=True)
    args = parser.parse_args()
    with args.input.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["Time (seconds)", "Speed (mph)"]:
            raise ValueError("Expected explicitly labeled seconds and mph columns")
        profile = np.array([[float(r[k]) for k in reader.fieldnames] for r in reader])
    if profile.ndim != 2 or len(profile) < 2 or not np.isfinite(profile).all():
        raise ValueError("Cycle needs at least two finite samples")
    time, speed = profile.T
    intervals = np.diff(time)
    dt = float(np.median(intervals))
    if time[0] != 0 or dt <= 0 or not np.allclose(intervals, dt):
        raise ValueError("Expected uniform increasing timestamps beginning at zero")
    if np.any(speed < 0) or speed[0] != 0 or speed[-1] != 0:
        raise ValueError("Expected nonnegative speeds and stopped endpoints")
    seconds = np.arange(int(np.floor(time[-1])) + 1)
    # A fractional final interval may be omitted only while fully stopped.
    if np.any(speed[time >= seconds[-1]] != 0):
        raise ValueError("Cannot discard motion in a fractional final interval")
    sampled = np.interp(seconds, time, speed)
    raw_distance = (
        float(np.trapezoid(speed, time) / 3600)
        if hasattr(np, "trapezoid")
        else float(np.trapz(speed, time) / 3600)
    )
    distance = float(sampled.sum() / 3600)
    raw_kinetic = float(np.maximum(np.diff(speed**2), 0).sum())
    kinetic = float(np.maximum(np.diff(sampled**2), 0).sum())
    if raw_distance <= 0 or raw_kinetic <= 0:
        raise ValueError("Cycle must contain motion")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["second", "speed_km_h"])
        writer.writerows(
            (int(t), f"{v * 1.609344:.9f}") for t, v in zip(seconds, sampled)
        )
    metadata = {
        "source_url": args.source_url,
        "source_page": "https://nrel.sitefinity.cloud/transportation/drive-cycle-tool",
        "raw_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "converted_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "conversion": "Linear interpolation at integer seconds, then mph * 1.609344; trailing fractional stopped interval omitted",
        "raw_sample_period_s": dt,
        "raw_sample_count": len(speed),
        "sample_count": len(sampled),
        "raw_elapsed_seconds": float(time[-1]),
        "elapsed_seconds": int(seconds[-1]),
        "raw_distance_miles": raw_distance,
        "distance_miles": distance,
        "distance_change_pct": 100 * (distance / raw_distance - 1),
        "raw_max_speed_mph": float(speed.max()),
        "max_speed_mph": float(sampled.max()),
        "positive_squared_speed_change_raw": raw_kinetic,
        "positive_squared_speed_change_resampled": kinetic,
        "positive_squared_speed_change_pct": 100 * (kinetic / raw_kinetic - 1),
        "maximum_reconstruction_error_mph": float(
            abs(np.interp(time, seconds, sampled) - speed).max()
        ),
        "note": "Reference trace, not actual dynamometer tracking. Sampling alters acceleration; summary checks do not prove dynamic equivalence.",
    }
    args.output.with_name(args.output.stem + "_provenance.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
