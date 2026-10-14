"""Check that the corrected baseline FCEV hardware survives 2050 transformation."""

import json
import pickle
from pathlib import Path

from premise_vehicle_provenance import digest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/premise_car_fcev_buffer_20261014"
WORK = Path("/private/tmp/premise-car-fcev-buffer-20261014")


def main():
    rows = []
    for year in (2020, 2050):
        path = WORK / str(year) / "database.pickle"
        build = json.loads((OUT / f"build_{year}.json").read_text())
        assert digest(path) == build["private_inventory_sha256"]
        with path.open("rb") as stream:
            data = pickle.load(stream)
        for dataset in data:
            spec = dataset.get("vehicle inventory provenance", {})
            if isinstance(spec, str):
                spec = json.loads(spec)
            if not (
                spec.get("family") == "car"
                and spec.get("model powertrain") == "FCEV"
                and spec.get("role") == "vehicle production"
            ):
                continue
            p = spec["baseline vehicle parameters"]
            expected = p["power"]
            parts = {}
            for exchange in dataset["exchanges"]:
                name = exchange["name"]
                if exchange["type"] == "technosphere" and any(
                    term in name
                    for term in (
                        "fuel cell",
                        "battery capacity",
                        "electric motor",
                        "inverter",
                    )
                ):
                    assert name not in parts
                    parts[name] = exchange["amount"]
            assert len(parts) == 5
            rows.append(
                dict(
                    year=year,
                    size=spec["model size"],
                    motor_kw=expected,
                    location=dataset["location"],
                    components=parts,
                )
            )
    assert len(rows) == 16
    for size in (
        "Mini",
        "Small",
        "Lower medium",
        "Medium",
        "Large",
        "Medium SUV",
        "Large SUV",
        "Van",
    ):
        before, after = [row for row in rows if row["size"] == size]
        assert before["components"] == after["components"]
    (OUT / "future_fcev_hardware.json").write_text(
        json.dumps(
            dict(
                unchanged_2020_hardware_in_2050=True,
                production_datasets_checked=rows,
                script_sha256=digest(Path(__file__)),
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
