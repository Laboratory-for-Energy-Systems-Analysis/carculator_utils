"""Fresh 2020 model diagnostics, independent of Premise's inventory adapter.

Run with the matched Python 3.12 carculator environment. This records physical
balances and separates hot exhaust, cold starts and evaporation. It does not
interpret a driving-cycle inventory as an emissions type-approval test.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for package in ("carculator_utils", "carculator", "carculator_truck"):
    sys.path.insert(0, str(ROOT.parent / package))

from carculator import CarInputParameters, CarModel
from carculator_truck import TruckInputParameters, TruckModel
from carculator_utils.array import fill_xarray_from_input_parameters
from carculator_utils.hot_emissions import HotEmissionsModel

from audit_premise_vehicle_workbooks import write_csv

FIELDS = (
    "curb mass",
    "driving mass",
    "gross mass",
    "cargo mass",
    "available payload",
    "capacity utilization",
    "average passengers",
    "lifetime kilometers",
    "kilometers per year",
    "range",
    "target range",
    "TtW energy",
    "electricity consumption",
    "fuel consumption",
    "fuel density per kg",
    "LHV fuel MJ per kg",
    "fuel mass",
    "fuel tank mass",
    "power",
    "electric power",
    "combustion power",
    "combustion power share",
    "engine efficiency",
    "transmission efficiency",
    "fuel cell power",
    "fuel cell power share",
    "fuel cell stack efficiency",
    "fuel cell own consumption",
    "fuel cell system efficiency",
    "fuel cell lifetime replacements",
    "battery power",
    "battery cell power density",
    "electric energy stored",
    "energy battery mass",
    "battery cell mass",
    "battery BoP mass",
    "battery cell mass share",
    "battery cell energy density",
    "battery DoD",
    "battery lifetime replacements",
    "electric utility factor",
    "is_available",
    "is_compliant",
)
COMPONENTS = (
    "Carbon monoxide",
    "Nitrogen oxides",
    "Particulate matters",
    "Hydrocarbons",
    "Non-methane hydrocarbon",
    "Methane",
    "Formaldehyde",
    "PAH, polycyclic aromatic hydrocarbons",
)
ALIASES = {
    "Hydrocarbon": "Hydrocarbons",
    "Particulate matters 2.5": "Particulate matters",
    "PAH polycyclic aromatic hydrocarbons": "PAH, polycyclic aromatic hydrocarbons",
    "PAHs": "PAH, polycyclic aromatic hydrocarbons",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    specs, emissions, snapshots = [], [], {}
    original = HotEmissionsModel.get_hot_emissions
    for family, label, inputs_cls, model_cls in (
        ("car", "pass_cars", CarInputParameters, CarModel),
        ("truck", "trucks", TruckInputParameters, TruckModel),
    ):
        path = (
            ROOT.parent
            / f"premise/premise/data/additional_inventories/lci-{label}.parameters.csv"
        )
        with path.open() as stream:
            installed = list(csv.DictReader(stream))
        native = sorted({(r["size"], r["powertrain"]) for r in installed})
        ip = inputs_cls()
        ip.static()
        _, array = fill_xarray_from_input_parameters(
            ip,
            scope={
                "size": sorted({s for s, _ in native}),
                "powertrain": sorted({p for _, p in native}),
                "year": [2020],
            },
        )
        captured = {}

        def capture(self, **kwargs):
            full = original(self, **kwargs)
            table = self.non_exhaust
            try:
                self.non_exhaust = None
                hot = original(self, **kwargs)
                if table is not None:
                    self.non_exhaust = table.copy(deep=True)
                    for kind in self.non_exhaust.type.values:
                        if kind != "cold start":
                            self.non_exhaust.loc[dict(type=kind)] = 0
                    exhaust = original(self, **kwargs)
                else:
                    exhaust = hot
            finally:
                self.non_exhaust = table
            captured.update(
                full=full,
                hot=hot,
                exhaust=exhaust,
                euro_class=kwargs["euro_class"],
                nmhc_species=list(self.nmhc_species.component.values),
            )
            return full

        HotEmissionsModel.get_hot_emissions = capture
        try:
            kwargs = (
                {"starts_per_day": 1.8}
                if family == "car"
                else {"cycle": "Regional delivery"}
            )
            model = model_cls(array, country="CH", drop_hybrids=False, **kwargs)
            model.set_all()
        finally:
            HotEmissionsModel.get_hot_emissions = original
        snapshots[family] = {}
        for size, power in native:
            cell = model.array.sel(size=size, powertrain=power, year=2020).isel(value=0)
            p = {str(k): float(cell.sel(parameter=k)) for k in cell.parameter.values}
            snapshots[family][f"{size}|{power}"] = p
            row = dict(
                family=family,
                size=size,
                powertrain=power,
                **{k: p[k] for k in FIELDS if k in p},
            )
            row["battery cell share residual kg"] = (
                p["battery cell mass"]
                - p["energy battery mass"] * p["battery cell mass share"]
                if p["energy battery mass"] > 0
                else 0
            )
            if power == "FCEV":
                row["fuel cell net power kW"] = (
                    p["fuel cell power"] / p["fuel cell own consumption"]
                )
                row["fuel cell plus recorded battery power fraction"] = (
                    row["fuel cell net power kW"] + p["battery power"]
                ) / p["power"]
                row["cell specific power implied by complement kW/kg"] = (
                    p["power"] - row["fuel cell net power kW"]
                ) / p["battery cell mass"]
            specs.append(row)
        for stage in ("full", "hot", "exhaust"):
            data = captured[stage]
            for size in data.coords["size"].values:
                for power in data.powertrain.values:
                    if str(power) in {"PHEV-p", "PHEV-d"}:
                        continue  # These placeholder cells are combined later.
                    cell = data.sel(size=size, powertrain=power, year=2020).isel(
                        value=0
                    )
                    sums = {}
                    for name in cell.component.values:
                        substance, _ = str(name).rsplit(", ", 1)
                        substance = ALIASES.get(substance, substance)
                        sums[substance] = sums.get(substance, 0) + float(
                            cell.sel(component=name)
                        )
                    sums["NMHC before speciation"] = sums.get(
                        "Non-methane hydrocarbon", 0
                    ) + sum(sums.get(str(s), 0) for s in captured["nmhc_species"])
                    emissions.append(
                        dict(
                            family=family,
                            size=str(size),
                            powertrain=str(power),
                            stage=stage,
                            euro_class=captured["euro_class"][0],
                            **{k: sums.get(k, 0) for k in COMPONENTS},
                            **{
                                "NMHC before speciation": sums["NMHC before speciation"]
                            },
                        )
                    )
        print(family, "complete", flush=True)
    write_csv(args.output / "model_specifications.csv", specs)
    write_csv(args.output / "model_emissions_kg_per_vkm.csv", emissions)
    (args.output / "model_snapshot.json").write_text(
        json.dumps(snapshots, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
