"""Export checked FCEV scenario builds to the private Brightway project."""

import copy
import json
import os
import pickle
import sys
from pathlib import Path
from types import SimpleNamespace

from premise_vehicle_provenance import digest
from verify_premise_vehicle_provenance import FIELDS, verify_saved

ROOT = Path(__file__).resolve().parents[1]
WORK = Path("/private/tmp/premise-fcev-buffer-20261014")
OUT = ROOT / "results/premise_fcev_buffer_20261014"


def main():
    os.environ["BRIGHTWAY2_DIR"] = str(WORK / "brightway")
    sys.path.insert(0, str(ROOT.parent / "premise"))
    import bw2data as bd
    from premise.brightway25 import write_brightway_database
    from premise.export import prepare_db_for_fast_export
    from premise.geomap import Geomap

    bd.projects.set_current("ecoinvent-3.12-cutoff")
    for year in (2020, 2050):
        record = json.loads((OUT / f"build_{year}.json").read_text())
        path = WORK / str(year) / "database.pickle"
        assert digest(path) == record["private_inventory_sha256"]
        assert record["validation_errors"] == 0
        with path.open("rb") as stream:
            data = pickle.load(stream)
        name = f"premise-remind-SSP2-NPi-{year}-{WORK.name}"
        if name in bd.databases:
            raise ValueError(f"Refusing to overwrite {name}")
        expected = {
            tuple(
                d[k] for k in ("name", "reference product", "location", "unit")
            ): copy.deepcopy({field: d.get(field) for field in FIELDS})
            for d in data
            if "vehicle inventory provenance" in d or "inventory provenance" in d
        }
        scenario = dict(
            record["scenario"],
            database=data,
            **{"iam data": SimpleNamespace(regions=Geomap("remind").iam_regions)},
        )
        prepared = prepare_db_for_fast_export(
            scenario, name=name, version="3.12", biosphere_name=record["biosphere"]
        )
        write_brightway_database(prepared, name, fast=True)
        saved = verify_saved(name, expected, year)
        saved.update(
            database=name,
            brightway_directory=str(bd.projects.dir),
            export_validation=scenario.get("_export_validation_phase"),
            script_sha256=digest(Path(__file__)),
        )
        (OUT / f"saved_{year}.json").write_text(json.dumps(saved, indent=2) + "\n")
        print(year, "saved and verified", flush=True)


if __name__ == "__main__":
    main()
