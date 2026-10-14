"""Provenance for vehicle adapters; model references and component sources differ."""

import ast
import copy
import hashlib
import json
import subprocess
from datetime import date
from pathlib import Path

KEY = "vehicle inventory provenance"
PUBLICATIONS = {
    "car": (
        "Sacchi, R., Bauer, C., Cox, B., Mutel, C. (2022). When, where and how can "
        "the electrification of passenger cars reduce greenhouse gas emissions? "
        "Renewable and Sustainable Energy Reviews 162, 112475. "
        "https://doi.org/10.1016/j.rser.2022.112475"
    ),
    "truck": (
        "Sacchi, R., Bauer, C., Cox, B. L. (2021). Does Size Matter? The Influence "
        "of Size, Load Factor, Range Autonomy, and Application Type on the Life "
        "Cycle Assessment of Current and Future Medium- and Heavy-Duty Vehicles. "
        "Environmental Science & Technology 55(8), 5224-5235. "
        "https://doi.org/10.1021/acs.est.0c07773"
    ),
}
MODELS = {"car": "carculator", "truck": "carculator_truck"}
BASELINE_FIELDS = (
    "power",
    "rated power",
    "electric motor efficiency",
    "auxiliary power demand",
    "fuel cell power",
    "fuel cell power share",
    "fuel cell own consumption",
    "battery power",
    "FCEV continuous charge kW",
    "FCEV continuous discharge kW",
    "FCEV 10s discharge kW",
    "FCEV power minimum capacity kWh",
    "kilometers per year",
    "lifetime kilometers",
    "average passengers",
    "cargo mass",
    "curb mass",
    "driving mass",
    "gross mass",
    "range",
    "target range",
    "electric energy stored",
    "energy battery mass",
    "battery lifetime replacements",
    "starts per day",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(ds):
    return tuple(
        ds.get(k, ds.get("product"))
        for k in ("name", "reference product", "location", "unit")
    )


def generation_manifest(family, root, output, record, generated_on):
    """Identify the recorded model run; a later metadata edit is not regeneration."""
    libraries = {}
    for name in (MODELS[family], "carculator_utils"):
        revision = record["commits"][name]
        source = subprocess.check_output(
            ["git", "show", f"{revision}:{name}/_version.py"],
            cwd=root / name,
            text=True,
        )
        assignment = next(
            n
            for n in ast.parse(source).body
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "VERSION" for t in n.targets)
        )
        libraries[name] = {
            "version": ast.literal_eval(assignment.value),
            "recorded git revision": revision,
        }
    manifest = {
        "schema version": 1,
        "family": family,
        "original model": MODELS[family],
        "model publication": PUBLICATIONS[family],
        "model generation date": generated_on,
        "libraries": libraries,
        "source revision boundary": "Recorded repository HEADs; file hashes identify the actual generation sources, including any uncommitted changes.",
        "source file sha256": {
            str(Path(p).relative_to(root)) if Path(p).is_absolute() else p: h
            for p, h in record["source_sha256"].items()
        },
        "artifacts": {
            name: {"sha256": digest(output / name)}
            for name in (
                "raw.json",
                "model_parameters.json",
                "vehicle_parameters.csv",
                "noise_audit.csv",
            )
        },
        "baseline year": 2020,
        "climate": "CH; Swiss annual-average thermal-demand assumptions",
        "driving cycle": "WLTC" if family == "car" else "Regional delivery",
        "noise boundary": "Direct noise flows omitted from Premise imports; retained in noise_audit.csv identified by SHA-256.",
    }
    if family == "car":
        calibration = root / "carculator/carculator/data/phev_2020_calibration.json"
        if calibration.exists():
            manifest["PHEV battery calibration"] = json.loads(calibration.read_text())
    if record.get("fcev_battery_policy"):
        manifest["FCEV battery profile"] = copy.deepcopy(record["fcev_battery_policy"])
    return manifest


def attach_provenance(datasets, family, generation, parameters):
    """Mutate metadata only. Preserve per-component citations supplied by the export."""
    by_name = {r["name"]: r for r in parameters}
    production_users = {}
    for ds in datasets:
        if ds["name"] not in by_name:
            continue
        for exc in ds["exchanges"]:
            if (
                exc["type"] == "technosphere"
                and exc["unit"] == "unit"
                and exc["name"]
                .lower()
                .startswith(("passenger car,", "lorry production,"))
            ):
                production_users.setdefault(identity(exc), []).append(ds["name"])
    for ds in datasets:
        if KEY in ds:
            raise ValueError(f"Provenance already attached: {ds['name']}")
        service = ds["name"] in by_name
        users = [ds["name"]] if service else production_users.get(identity(ds), [])
        role = (
            "transport service"
            if service
            else "vehicle production" if users else "bundled component"
        )
        spec = copy.deepcopy(generation)
        spec.update(
            {
                "role": role,
                "metadata updated": date.today().isoformat(),
                "baseline identity": dict(
                    zip(("name", "reference product", "location", "unit"), identity(ds))
                ),
            }
        )
        if users:
            # Shared manufacture can serve both a native CNG vehicle and an LPG proxy.
            native = next(
                (
                    by_name[n]
                    for n in users
                    if str(by_name[n]["proxy"]).lower() == "false"
                ),
                by_name[users[0]],
            )
            spec["baseline vehicle parameters"] = {
                k: float(native[k])
                for k in BASELINE_FIELDS
                if native.get(k) not in (None, "")
            }
            spec["model size"] = native["size"]
            spec["model powertrain"] = native["powertrain"]
            spec["service templates"] = users
            spec["parameter units"] = (
                "km/year, lifetime km, persons, masses kg, ranges km, stored energy kWh, motor/stack/battery power kW, auxiliary power demand W, efficiencies/power shares/gross-net multiplier dimensionless, replacements per vehicle, starts/day; all describe the 2020 baseline."
            )
            spec["proxy"] = bool(service and str(native["proxy"]).lower() == "true")
            spec["proxy boundary"] = (
                "Energy-preserving gasoline/LPG conversion; manufacture and non-CO2 combustion factors from the recorded model powertrain. LPG excludes CNG pump-to-tank methane leakage."
                if spec["proxy"]
                else "Native model vehicle; any services using it as a proxy record their own conversion."
            )
            ds["source"] = PUBLICATIONS[family]
            note = (
                "Vehicle specifications in the original-model comment below describe the 2020 baseline. "
                "Scenario-adjusted fuel purchases, efficiency and hardware are recorded separately by Premise. "
                "Original-model fuel volumes use model fuel densities; final purchases use the units of the linked suppliers. "
            )
            if native["powertrain"] == "FCEV":
                note += (
                    "FCEV buffer power is the complement of net fuel-cell power in the electrical supply allocation: motor shaft power divided by motor/inverter efficiency, plus auxiliary DC demand. "
                    "The original fuel-cell/battery percentage split is retained on this electrical boundary; gross fuel-cell stack power includes its own consumption once. "
                    "Complete pack mass equals cell mass divided by cell mass share. This accounting does not independently validate traction-cell charge/discharge limits, fuel-cell dynamics or sustained power delivery. "
                )
                if generation.get("FCEV battery profile"):
                    profile = generation["FCEV battery profile"]
                    spec["FCEV battery profile"] = copy.deepcopy(profile)
                    note += (
                        "Documented FCEV traction-pack proxy: "
                        + profile["source"]
                        + ". "
                        + profile["sizing"]
                        + " "
                        + profile["power_boundary"]
                        + " "
                        + profile["mass_boundary"]
                        + " "
                        + profile["limits"]
                        + " "
                        + profile["lca_proxy"]
                        + " "
                        + profile["future_hardware"]
                        + " "
                        "Battery power records the required DC buffer, not a measured cell capability. "
                    )
                elif family == "truck":
                    note += (
                        "The traction buffer retains the original energy-sizing assumption: 20 kWh plus 6% of hydrogen chemical energy. "
                        "The inherited lead-acid starter cell power-density input is not a validated lithium-ion traction rating and does not determine this final energy-sized pack. "
                        "Traction-cell peak-power capability remains unverified; battery power records the model requirement. "
                    )
            if native["powertrain"].startswith(("HEV-", "PHEV-")):
                note += (
                    "Hybrid hot-exhaust deterioration uses the corresponding petrol/diesel ICEV engine's bundled endpoint factors, as for hot emission factors. "
                    "This is an uncalibrated hybrid ageing proxy: the existing lifetime-average formula uses vehicle lifetime kilometres, without an extra PHEV utility-factor adjustment. "
                    "PHEV combustion emissions are weighted once when combining driving modes; cold-start and evaporative factors are not multiplied by hot-exhaust deterioration. "
                )
            if family == "car" and native["powertrain"].startswith("PHEV-"):
                calibration = generation.get("PHEV battery calibration")
                if calibration:
                    pack = calibration["sizes"][native["size"]]
                    spec["PHEV battery calibration"] = copy.deepcopy(pack)
                    note += (
                        f"2020 PHEV battery calibration: {pack['capacity kWh']:g} kWh nominal, "
                        f"{pack['pack mass kg']:g} kg complete pack. {pack['boundary']} "
                        f"Capacity source: {pack['capacity source']}; mass source: {pack['mass source']}. "
                        "Petrol and diesel variants share the class-specific battery proxy. "
                        "Electric and combustion modes carry the same physical pack. "
                        "The 80% usable-energy window, 70% cell mass fraction and NMC-622 chemistry remain model assumptions. "
                        "Premise retains the MIX capacity market per nominal kWh; its manufacturing mass/chemistry need not equal this calibrated physical pack. "
                        "Future pack mass follows the relative chemistry-density trend from the calibrated baseline. "
                    )
        else:
            spec["component source boundary"] = (
                "Bundled component recipe exported with the model; model year and climate do not date or parameterize this component. Its literature source is recorded separately."
            )
            ds["source"] = (
                ds.get("source")
                or "Bundled carculator_utils inventory; no activity-specific literature reference supplied."
            )
            note = "Bundled component inventory; the model publication describes the generating vehicle model, not the component recipe. "
        model = MODELS[family]
        spec["activity source"] = ds["source"]
        ds["model"] = model
        ds["model version"] = generation["libraries"][model]["version"]
        ds["model publication"] = PUBLICATIONS[family]
        ds[KEY] = spec
        ds["comment"] = (
            f"Original LCA model: {model} {ds['model version']}; shared library carculator_utils "
            f"{generation['libraries']['carculator_utils']['version']}. "
            f"Model publication: {PUBLICATIONS[family]} "
            + note
            + (ds.get("comment") or "")
        )


def attach_legacy_provenance(datasets, original_by_identity, original_workbook_hash):
    """Restore inherited references without attributing old components to a new run."""
    for ds in datasets:
        original = original_by_identity[identity(ds)]
        for field in ("source", "description", "special remark"):
            if original.get(field):
                ds[field] = original[field]
        ds["inventory provenance"] = {
            "schema version": 1,
            "role": "retained legacy component",
            "original workbook": "lci-trucks.xlsx",
            "original workbook sha256": original_workbook_hash,
            "source database version": "3.7",
            "model generation version": "not recorded in original workbook",
            "boundary": "Retained for compatibility with other supplementary inventories; not regenerated by the current carculator_truck model.",
            "metadata updated": date.today().isoformat(),
        }
        ds["comment"] = (
            "Retained legacy truck component, ecoinvent 3.7 import basis; not regenerated by the current vehicle model. "
            + (ds.get("comment") or "")
        )


def enrich_export(datasets, family, root, output, record, parameters, reused):
    """Keep the original run identity when adapting a previously generated raw file."""
    path = output / "generation_provenance.json"
    if reused and path.exists():
        generation = json.loads(path.read_text())
        for name in ("raw.json", "model_parameters.json"):
            if digest(output / name) != generation["artifacts"][name]["sha256"]:
                raise ValueError(f"Reused generation artifact changed: {name}")
    else:
        original = record
        generated_on = date.today().isoformat()
        if reused:
            original = json.loads((output / "provenance.json").read_text())
            generated_on = original.get("model generation date", "not recorded")
            for name, value in original["source_sha256"].items():
                file = Path(name) if Path(name).is_absolute() else root / name
                if "dev" not in file.parts and digest(file) != value:
                    raise ValueError(
                        f"Cannot establish provenance of reused raw data: {name}"
                    )
        generation = generation_manifest(family, root, output, original, generated_on)
    # These two artifacts belong to the adapter, which may have changed metadata.
    for name in ("vehicle_parameters.csv", "noise_audit.csv"):
        generation["artifacts"][name] = {"sha256": digest(output / name)}
    path.write_text(json.dumps(generation, indent=2) + "\n")
    attach_provenance(datasets, family, generation, parameters)
    record["generation provenance"] = generation
