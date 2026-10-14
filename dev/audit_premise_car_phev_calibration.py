"""Audit 2020 PHEV battery calibration without changing model defaults.

Manufacturer examples are plausibility benchmarks, not fleet averages. The
Prius-density column is an arithmetic sensitivity, not a regenerated vehicle.
Run with Python 3.12 and matching sibling sources; no Brightway project is used.
"""

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent / "carculator")]

import numpy as np

from carculator import CarInputParameters, CarModel, fill_xarray_from_input_parameters

SIZES = (
    "Mini",
    "Small",
    "Lower medium",
    "Medium",
    "Large",
    "Medium SUV",
    "Large SUV",
    "Van",
)
BENCHMARKS = (
    {
        "vehicle": "Toyota Prius Plug-in",
        "publication date": "2017-02-06",
        "capacity kWh": 8.8,
        "pack mass kg": 120,
        "capacity basis": "manufacturer battery capacity; not a usable-energy claim",
        "scope": "Contemporary battery reference; not a Mini/Small segment match",
        "url": "https://newsroom.toyota.eu/toyota-prius-plug-in-hybrid/",
    },
    {
        "vehicle": "Volkswagen Golf eHybrid/GTE Mk8",
        "publication date": "2020-08",
        "capacity kWh": 13,
        "scope": "Lower medium example; excludes earlier Golf generations",
        "capacity basis": "manufacturer battery energy content",
        "url": "https://www.volkswagen-newsroom.com/en/golf-etsi-golf-ehybrid-and-golf-gte-international-media-drive-6336/the-new-golf-hybrid-models-6337",
    },
    {
        "vehicle": "BMW 330e",
        "publication date": "2019-08-14",
        "capacity kWh": 12,
        "scope": "Medium example",
        "capacity basis": "gross",
        "url": "https://www.press.bmwgroup.com/global/article/detail/T0298940EN/sportier-and-more-efficient-than-ever-thanks-to-the-latest-bmw-edrive-technology%3A-the-new-bmw-330e-sedan-celebrates-its-market-launch?language=en",
    },
    {
        "vehicle": "BMW 530e",
        "publication date": "2019-08",
        "capacity kWh": 12,
        "scope": "Large example",
        "capacity basis": "gross",
        "url": "https://www.press.bmwgroup.com/global/article/detail/T0299399EN/more-variety-more-electric-range-less-co2%3A-bmw-530e-sedan-with-the-latest-battery-cell-technology-and-also-with-optional-intelligent-all-wheel-drive",
    },
    {
        "vehicle": "Toyota RAV4 Plug-in",
        "publication date": "2020-09-14",
        "capacity kWh": 18.1,
        "scope": "Medium SUV example; late-2020 introduction",
        "capacity basis": "manufacturer battery capacity",
        "url": "https://newsroom.toyota.eu/the-new-toyota-rav4-plug-in-hybrid/",
    },
    {
        "vehicle": "BMW X5 xDrive45e",
        "publication date": "2020-02-27",
        "capacity kWh": 24,
        "scope": "Large SUV example",
        "capacity basis": "gross",
        "url": "https://www.press.bmwgroup.com/slovenia/article/detail/T0300315EN/electrifying-power-for-supreme-driving-pleasure-market-launch-of-the-new-bmw-x5-xdrive45e",
    },
    {
        "vehicle": "Ford Tourneo Custom Plug-in Hybrid",
        "publication date": "2019-09-23",
        "capacity kWh": 13.6,
        "scope": "Passenger van example; series-hybrid architecture",
        "capacity basis": "manufacturer battery capacity",
        "url": "https://media.ford.com/content/fordmedia/feu/gb/en/news/2019/09/23/New-Ford-Transit-and-Tourneo-Custom-Plug-In-Hybrids-Deliver-Zero-Emission-Driving.html",
    },
)


def dump_csv(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    inputs = CarInputParameters()
    inputs.static()
    _, array = fill_xarray_from_input_parameters(
        inputs,
        scope={"size": list(SIZES), "powertrain": ["PHEV-p", "PHEV-d"], "year": [2020]},
    )
    model = CarModel(array, country="CH", starts_per_day=1.8, drop_hybrids=False)
    model.set_all()

    installed_path = (
        ROOT.parent
        / "premise/premise/data/additional_inventories/lci-pass_cars.parameters.csv"
    )
    with installed_path.open() as stream:
        installed_rows = list(csv.DictReader(stream))

    rows = []
    for size in SIZES:
        for powertrain in ("PHEV-p", "PHEV-d"):

            def value(parameter, mode=powertrain):
                return float(
                    model.array.sel(
                        size=size,
                        powertrain=mode,
                        year=2020,
                        value=0,
                        parameter=parameter,
                    )
                )

            capacity = value("electric energy stored")
            mass = value("energy battery mass")
            density = value("battery cell energy density")
            cells = value("battery cell mass share")
            share = value("electric utility factor")
            demand = value("TtW energy", "PHEV-e") / 3600
            combustion_mode = powertrain.replace("PHEV-", "PHEV-c-")
            np.testing.assert_allclose(capacity, mass * cells * density, rtol=2e-6)
            np.testing.assert_allclose(
                capacity, value("electric energy stored", "PHEV-e"), rtol=2e-6
            )
            np.testing.assert_allclose(
                mass,
                value("battery cell mass") + value("battery BoP mass"),
                rtol=2e-6,
            )
            # The source records below are read independently of the calculation.
            original_mass = float(
                array.sel(
                    size=size,
                    powertrain="PHEV-e",
                    year=2020,
                    value=0,
                    parameter="energy battery mass",
                )
            )
            np.testing.assert_allclose(mass, original_mass)
            battery_in_weighted_modes = share * mass + (1 - share) * value(
                "energy battery mass", combustion_mode
            )
            rows.append(
                {
                    "size": size,
                    "powertrain": powertrain,
                    "capacity kWh": capacity,
                    "pack mass kg": mass,
                    "cell density kWh/kg": density,
                    "cell mass share": cells,
                    "pack density Wh/kg": 1000 * capacity / mass,
                    "usable capacity kWh": capacity * value("battery DoD"),
                    "electric range km": capacity * value("battery DoD") / demand,
                    "electric utility factor": share,
                    "electric-mode stored kWh/km": demand,
                    "combustion-mode pack mass kg": value(
                        "energy battery mass", combustion_mode
                    ),
                    "combustion-mode capacity kWh": value(
                        "electric energy stored", combustion_mode
                    ),
                    "battery mass in weighted modes kg": battery_in_weighted_modes,
                    "full pack minus weighted pack kg": mass
                    - battery_in_weighted_modes,
                    "Prius density sensitivity capacity kWh": mass * 8.8 / 120,
                    "Prius density sensitivity range km at unchanged mode demand": (
                        mass * 8.8 / 120 * value("battery DoD") / demand
                    ),
                }
            )
            matching = [
                row
                for row in installed_rows
                if row["size"] == size and row["powertrain"] == powertrain
            ]
            assert matching, (size, powertrain)
            for row in matching:
                for parameter in (
                    "electric energy stored",
                    "energy battery mass",
                    "electric utility factor",
                ):
                    np.testing.assert_allclose(
                        value(parameter), float(row[parameter]), rtol=2e-6
                    )

    data_path = ROOT.parent / "carculator/carculator/data/default_parameters.json"
    records = json.loads(data_path.read_text())
    selected = {
        key: record
        for key, record in records.items()
        if record["year"] == 2020
        and "PHEV-e" in record["powertrain"]
        and record["name"]
        in (
            "energy battery mass",
            "battery cell energy density",
            "battery cell mass share",
            "battery cell energy density, NMC-622",
            "battery cell mass share, NMC-622",
            "battery DoD",
        )
    }
    history = []
    for revision in ("bf2abf2", "463c8be", "1a773dd", "HEAD"):
        source = json.loads(
            subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(ROOT.parent / "carculator"),
                    "show",
                    f"{revision}:carculator/data/default_parameters.json",
                ],
                text=True,
            )
        )
        values = [
            {"sizes": record["sizes"], "mass kg": record["amount"]}
            for record in source.values()
            if record["name"] == "energy battery mass"
            and record["year"] == 2020
            and "PHEV-e" in record["powertrain"]
        ]
        commit = subprocess.check_output(
            ["git", "-C", str(ROOT.parent / "carculator"), "rev-parse", revision],
            text=True,
        ).strip()
        history.append({"revision": revision, "commit": commit, "mass inputs": values})

    dump_csv(args.output / "current_specs.csv", rows)
    dump_csv(args.output / "manufacturer_benchmarks.csv", BENCHMARKS)
    for name, payload in (
        ("input_records.json", selected),
        ("input_history.json", history),
        (
            "checks.json",
            {
                "vehicles checked": len(rows),
                "mass-capacity arithmetic": "passed",
                "full physical capacity retained in combined PHEV": "passed",
                "installed parameter comparison": "passed",
                "source calibration": "unresolved; manufacturer examples are not fleet averages",
                "driving-mode battery consistency": "unresolved; mode packs differ",
                "python": sys.version,
                "numpy": np.__version__,
                "defaults sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
                "installed parameters sha256": hashlib.sha256(
                    installed_path.read_bytes()
                ).hexdigest(),
                "audit script sha256": hashlib.sha256(
                    Path(__file__).read_bytes()
                ).hexdigest(),
            },
        ),
    ):
        (args.output / name).write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "vehicles checked": len(rows)}))


if __name__ == "__main__":
    main()
