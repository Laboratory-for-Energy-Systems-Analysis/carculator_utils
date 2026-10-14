"""Screen the current model emissions without equating model duty with approval.

The truck screen reports g/kWh of fuel as a strict lower bound on g/kWh of
engine work. It cannot establish type-approval compliance on a different cycle.
Uncharacterized proxy combustion factors are labelled explicitly.
"""

import argparse
import csv
import json
from pathlib import Path

from audit_premise_vehicle_carbon import write_csv

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.generation / "probe/model_emissions_kg_per_vkm.csv").open() as stream:
        emissions = {
            (r["family"], r["size"], r["powertrain"], r["stage"]): r
            for r in csv.DictReader(stream)
        }
    cars, trucks = [], []
    for family, folder in (("car", "cars"), ("truck", "trucks")):
        with (args.generation / folder / "vehicle_parameters.csv").open() as stream:
            parameters = list(csv.DictReader(stream))
        for par in parameters:
            power, size = par["powertrain"], par["size"]
            if power in {"BEV", "FCEV"}:
                continue
            mode = (
                power.replace("PHEV-", "PHEV-c-")
                if power.startswith("PHEV-")
                else power
            )
            weight = (
                1 - float(par["electric utility factor"])
                if power.startswith("PHEV-")
                else 1
            )
            sources = {
                stage: emissions[family, size, mode, stage]
                for stage in ("hot", "exhaust", "full")
            }
            diesel = mode.endswith("-d")
            for pollutant, column in (
                ("CO", "Carbon monoxide"),
                ("NOx", "Nitrogen oxides"),
                ("PM", "Particulate matters"),
                ("THC", "Hydrocarbons"),
                ("NMHC", "NMHC before speciation"),
                ("CH4", "Methane"),
                ("THC+NOx", None),
            ):
                if column:
                    quantities = {
                        s: float(r[column]) * 1e6 * weight for s, r in sources.items()
                    }
                else:
                    quantities = {
                        s: (float(r["Hydrocarbons"]) + float(r["Nitrogen oxides"]))
                        * 1e6
                        * weight
                        for s, r in sources.items()
                    }
                row = dict(
                    name=par["name"],
                    size=size,
                    powertrain=power,
                    proxy=par["proxy"],
                    pollutant=pollutant,
                    hot_mg_per_vkm=quantities["hot"],
                    cold_start_mg_per_vkm=quantities["exhaust"] - quantities["hot"],
                    exhaust_mg_per_vkm=quantities["exhaust"],
                    phev_combustion_share=weight,
                )
                if family == "car":
                    limits = {
                        "CO": 500 if diesel else 1000,
                        "NOx": 80 if diesel else 60,
                        "PM": 4.5,
                    }
                    limits.update(
                        {"THC+NOx": 170} if diesel else {"THC": 100, "NMHC": 68}
                    )
                    if pollutant not in limits:
                        continue
                    limit = limits[pollutant]
                    row.update(
                        benchmark_mg_per_km=limit,
                        ratio_to_benchmark=quantities["exhaust"] / limit,
                        boundary="M-category Euro 6 screening benchmark; Van classification unconfirmed; PI PM conditional on direct injection; no type-approval claim",
                    )
                    cars.append(row)
                else:
                    limits = {"CO": 4000, "NOx": 460, "PM": 10}
                    limits.update({"THC": 160} if diesel else {"NMHC": 160, "CH4": 500})
                    if pollutant not in limits:
                        continue
                    fuel_MJ_per_km = (
                        float(par["fuel_energy_MJ_per_tkm"])
                        * float(par["cargo mass"])
                        / 1000
                    )
                    lower_bound = quantities["exhaust"] * 3.6 / fuel_MJ_per_km
                    row.update(
                        benchmark_mg_per_engine_kWh=limits[pollutant],
                        mg_per_fuel_kWh=lower_bound,
                        minimum_engine_efficiency_to_equal_benchmark=lower_bound
                        / limits[pollutant],
                        boundary="Regional delivery, not WHTC; engine work unavailable; 3.5t homologation category unconfirmed; gasoline proxies retain CI factors",
                    )
                    trucks.append(row)
    write_csv(args.output / "car_euro6_screen.csv", cars)
    write_csv(args.output / "truck_euroVI_screen.csv", trucks)
    summary = dict(
        car_vehicles=len({r["name"] for r in cars}),
        car_benchmark_exceedances=[r for r in cars if r["ratio_to_benchmark"] > 1],
        truck_vehicles=len({r["name"] for r in trucks}),
        truck_lower_bound_exceedances=sum(
            r["minimum_engine_efficiency_to_equal_benchmark"] > 1 for r in trucks
        ),
        interpretation="Screening flags, not a certification test; no inventory was clipped.",
    )
    (args.output / "emission_screen_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
