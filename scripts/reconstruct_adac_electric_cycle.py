"""Reconstruct the published ADAC BEV ending; preserve the numerical WLTC prefix.

Requires NumPy, Pillow and Poppler's pdfimages. This is NOT an official trace.
The PDF is downloaded separately from SOURCE_URL and supplied with --pdf.
"""

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

SOURCE_URL = "https://assets.adac.de/image/upload/v1721027897/ADAC-eV/KOR/Text/PDF/ecotest-methodik-ab-04-2021_pg5juw.pdf"
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (
        hashlib.sha256(args.pdf.read_bytes()).hexdigest()
        != "dc745309546ab8a9f70194750947b09fdd8d36d593084528c3b5adef3aaada58"
    ):
        raise ValueError("Source PDF changed; inspect the figure and axes before reuse")
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        prefix = Path(directory) / "figure"
        subprocess.run(
            ["pdfimages", "-f", "3", "-l", "3", "-png", str(args.pdf), str(prefix)],
            check=True,
        )
        path = Path(str(prefix) + "-002.png")
        pixels = np.asarray(Image.open(path).convert("RGB"))
        assert pixels.shape == (
            649,
            1008,
            3,
        ), "Unexpected source figure; inspect axes before reuse"
        image_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    # Pixel coordinates read from the original embedded figure, not a screenshot.
    # x=61.5 at 0 s, x=957 at 1900 s; y=600 at 0 km/h, y=50 at 140 km/h.
    x0, x_per_second, y0, y_per_kph = 61.5, (957 - 61.5) / 1900, 600.0, 550 / 140
    dark = pixels.max(axis=2) < 100
    xs, ys = [], []
    for x in range(64, 985):
        found = np.flatnonzero(dark[55:600, x]) + 55
        if len(found):
            xs.append(x)
            ys.append(float(np.median(found)))
    times = (np.array(xs) - x0) / x_per_second
    speeds = np.maximum((y0 - np.array(ys)) / y_per_kph, 0)
    source = ROOT / "carculator_utils/data/driving_cycles/car.csv"
    wltc = np.genfromtxt(source, delimiter=";", skip_header=1)[:, 1]
    wltc = wltc[np.isfinite(wltc)]
    # Last numerical WLTC point before the plotted profile holds at 80 km/h.
    join = 1767
    assert 79 < wltc[join] < 81
    tail_times = np.arange(join + 1, 1961)
    tail = np.interp(tail_times, times, speeds)
    for plateau in (80, 110, 130):
        tail[np.abs(tail - plateau) < 1] = plateau
    tail[-1] = 0
    nominal = np.r_[wltc[: join + 1], tail]
    variants = {"wltc_reference": wltc, "adac_graph_nominal": nominal}
    # Deliberately wider than pixel-level timing: sensitivity, NOT confidence bounds.
    for name, stretch in [("adac_tail_short", 0.95), ("adac_tail_long", 1.05)]:
        source_times = np.arange(join, len(nominal)) - join
        length = round(source_times[-1] * stretch)
        ending = np.interp(
            np.arange(length + 1) / stretch, source_times, nominal[join:]
        )
        ending[-1] = 0
        variants[name] = np.r_[nominal[:join], ending]
    # Preserve the ending's speed waypoints and dwell, extending acceleration
    # ramps. This changes time AND distance; it is a separate feasibility probe.
    ending = [nominal[join]]
    for target in nominal[join + 1 :]:
        start = ending[-1]
        steps = max(1, int(np.ceil((target - start) / (0.25 * 3.6))))
        ending.extend(np.linspace(start, target, steps + 1)[1:])
    variants["adac_tail_gentle_acceleration"] = np.r_[nominal[:join], ending]
    summary = {}
    for name, speed in variants.items():
        path = args.output / (name + ".csv")
        np.savetxt(
            path,
            np.c_[np.arange(len(speed)), speed],
            delimiter=",",
            header="time_s,speed_kmh",
            comments="",
            fmt=["%d", "%.6f"],
        )
        summary[name] = dict(
            samples=len(speed),
            distance_km=float(speed.sum() / 3600),
            max_speed_kmh=float(speed.max()),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
    sample = np.arange(30, 1740)
    visible = np.interp(sample, times, speeds)
    moving = wltc[sample] > 10
    check = np.abs(visible[moving] - wltc[sample][moving])
    metadata = dict(
        source_url=SOURCE_URL,
        pdf_sha256=hashlib.sha256(args.pdf.read_bytes()).hexdigest(),
        source_page=3,
        source_figure=3,
        image_sha256=image_hash,
        numerical_wltc_source="carculator_utils/data/driving_cycles/car.csv",
        numerical_wltc_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        join_second=join,
        x0=x0,
        x_pixels_per_second=x_per_second,
        y0=y0,
        y_pixels_per_kmh=y_per_kph,
        moving_prefix_median_absolute_error_kmh=float(np.median(check)),
        moving_prefix_p95_absolute_error_kmh=float(np.quantile(check, 0.95)),
        variants=summary,
        status="Graph reconstruction, not original ADAC or measured vehicle speed data",
        limitations=[
            "Manual axis calibration; raster resolves roughly 2.1 seconds per pixel",
            "Numerical WLTC prefix preserved; agreement with graph checked, not proof of exact ADAC trace",
            "Sharp motorway accelerations may exceed vehicle power; inspect run diagnostics",
            "Tail +/-5% timing is an illustrative sensitivity, not a statistical confidence interval",
            "Gentle-acceleration probe retimes the ending to at most 0.25 m/s2 positive acceleration; preserves waypoints, changes time/distance, is not an ADAC test trace",
            "No temperature, HVAC, road-load or SOC matching is implied",
        ],
    )
    (args.output / "reconstruction.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
