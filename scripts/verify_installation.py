"""Build and execute actual wheel/sdist artifacts in clean environments.

Example (from any directory):
    python scripts/verify_installation.py --repositories ../carculator_utils . \
        ../carculator_bus ../carculator_truck ../carculator_two_wheeler --output /tmp/check

The output directory must not exist. Network access is required for dependency
resolution; calculation smoke tests themselves use only bundled resources.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import venv
import zipfile
from pathlib import Path


def interpreter(environment):
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(args, cwd, log, env):
    with log.open("a", encoding="utf-8") as stream:
        stream.write("\n" + repr([str(a) for a in args]) + "\n")
        stream.flush()
        subprocess.run(
            [str(a) for a in args],
            cwd=cwd,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=900,
        )


SMOKE = r"""
import importlib, importlib.metadata, json, sys
from pathlib import Path
import numpy as np
from unittest.mock import patch
cases = {
    "carculator": ("Car", "Medium", "BEV", {}),
    "carculator_bus": ("Bus", "13m-city", "BEV-depot", {}),
    "carculator_truck": ("Truck", "40t", "BEV", {"cycle":"Long haul"}),
    "carculator_two_wheeler": ("TwoWheeler", "Bicycle <25", "BEV", {}),
}
records = []
for name in sys.argv[1:]:
    with patch("socket.socket.connect", side_effect=AssertionError("Model attempted network access")):
        module = importlib.import_module(name)
        assert Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), module.__file__
        assert ".".join(map(str, module.__version__)) == importlib.metadata.version(name)
        if name not in cases:
            from carculator_utils.background_systems import BackgroundSystemModel
            BackgroundSystemModel()
            continue
        prefix, size, powertrain, kwargs = cases[name]
        ip = getattr(module, prefix+"InputParameters")(); ip.static()
        _, array = module.fill_xarray_from_input_parameters(ip, scope={
            "size":[size], "powertrain":[powertrain], "year":[2020]})
        model = getattr(module,prefix+"Model")(array, **kwargs); model.set_all()
        result = getattr(module,"Inventory"+prefix)(model).calculate_impacts()
        assert np.isfinite(result.values).all()
        assert model["TtW energy"].item() > 0
        records.append({"package":name,"version":importlib.metadata.version(name),
            "ttw_energy":model["TtW energy"].item(),
            "climate_change":result.sel(impact_category="climate change").sum().item()})
Path("model-results.json").write_text(json.dumps(records,indent=2))
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repositories", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run repository suites against installed wheels with test/export extras",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    brightway_data = output / "brightway-data"
    brightway_data.mkdir()
    env["BRIGHTWAY2_DIR"] = str(brightway_data)
    builder = output / "builder"
    venv.EnvBuilder(with_pip=True).create(builder)
    log = output / "installation.log"
    run([interpreter(builder), "-m", "pip", "install", "build"], output, log, env)
    wheelhouse = output / "wheels"
    wheelhouse.mkdir()
    rebuilt = output / "rebuilt"
    rebuilt.mkdir()
    packages = []
    artifacts = []
    for repository in args.repositories:
        repository = repository.resolve()
        import tomllib

        metadata = tomllib.loads((repository / "pyproject.toml").read_text())["project"]
        package = metadata["name"].replace("-", "_")
        packages.append(package)
        run(
            [
                interpreter(builder),
                "-m",
                "build",
                "--sdist",
                "--wheel",
                "--outdir",
                wheelhouse,
                repository,
            ],
            output,
            log,
            env,
        )
        archive = next(wheelhouse.glob(package + "-*.tar.gz"))
        unpacked = output / (package + "-source")
        unpacked.mkdir()
        with tarfile.open(archive) as tar:
            # Only extract archive-relative regular files/directories.
            for member in tar.getmembers():
                destination = (unpacked / member.name).resolve()
                if not destination.is_relative_to(unpacked) or not (
                    member.isfile() or member.isdir()
                ):
                    raise ValueError(f"Unsafe sdist member {member.name}")
            tar.extractall(unpacked, filter="data")
        source = next(unpacked.iterdir())
        run(
            [
                interpreter(builder),
                "-m",
                "build",
                "--wheel",
                "--outdir",
                rebuilt,
                source,
            ],
            output,
            log,
            env,
        )
        expected = {
            str(p.relative_to(repository))
            .replace(os.sep, "/"): hashlib.sha256(p.read_bytes())
            .hexdigest()
            for p in (repository / package / "data").rglob("*")
            if p.is_file()
            and p.suffix in (".json", ".yaml", ".yml", ".csv", ".npz", ".xlsx")
        }
        for directory in (wheelhouse, rebuilt):
            wheel = next(directory.glob(package + "-*.whl"))
            with zipfile.ZipFile(wheel) as zf:
                for name, digest in expected.items():
                    assert hashlib.sha256(zf.read(name)).hexdigest() == digest, (
                        wheel,
                        name,
                    )
            artifacts.append(
                {
                    "name": wheel.name,
                    "source": directory.name,
                    "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                    "resources": len(expected),
                }
            )
    if args.run_tests:
        tests_runtime = output / "tests"
        venv.EnvBuilder(with_pip=True).create(tests_runtime)
        tests_work = output / "tests-run"
        tests_work.mkdir()
        # Install exact candidate artifacts plus their declared optional extras.
        extras = [
            str(wheel.resolve()) + "[test,brightway,excel]"
            for wheel in sorted(wheelhouse.glob("*.whl"))
        ]
        run(
            [interpreter(tests_runtime), "-m", "pip", "install", *extras],
            tests_work,
            log,
            env,
        )
        run([interpreter(tests_runtime), "-m", "pip", "check"], tests_work, log, env)
        run(
            [interpreter(tests_runtime), "-c", "import bw2io, xlsxwriter"],
            tests_work,
            log,
            env,
        )
        with (output / "tests-freeze.txt").open("w") as stream:
            subprocess.run(
                [str(interpreter(tests_runtime)), "-m", "pip", "freeze"],
                env=env,
                stdout=stream,
                check=True,
            )
        for repository in args.repositories:
            package = repository.resolve().name.replace("-", "_")
            run(
                [
                    interpreter(tests_runtime),
                    "-m",
                    "pytest",
                    repository.resolve() / "tests",
                    "--import-mode=importlib",
                    "-q",
                    "--tb=short",
                    "-p",
                    "no:cacheprovider",
                    "--junitxml",
                    output / (package + "-tests.xml"),
                ],
                tests_work,
                log,
                env,
            )
    results = []
    for kind, directory in (("wheel", wheelhouse), ("sdist", rebuilt)):
        runtime = output / kind
        venv.EnvBuilder(with_pip=True).create(runtime)
        work = output / (kind + "-run")
        work.mkdir()
        wheels = sorted(directory.glob("*.whl"))
        run([interpreter(runtime), "-m", "pip", "install", *wheels], work, log, env)
        run([interpreter(runtime), "-m", "pip", "check"], work, log, env)
        # No checkout on sys.path and no optional export dependencies in the core install.
        run(
            [
                interpreter(runtime),
                "-c",
                "import importlib.util; assert importlib.util.find_spec('bw2io') is None",
            ],
            work,
            log,
            env,
        )
        run([interpreter(runtime), "-c", SMOKE, *packages], work, log, env)
        result = json.loads((work / "model-results.json").read_text())
        results.append(result)
        with (output / (kind + "-freeze.txt")).open("w") as stream:
            subprocess.run(
                [str(interpreter(runtime)), "-m", "pip", "freeze"],
                env=env,
                stdout=stream,
                check=True,
            )
    assert [r["package"] for r in results[0]] == [r["package"] for r in results[1]]
    for first, second in zip(*results):
        for field in ("ttw_energy", "climate_change"):
            assert abs(first[field] - second[field]) <= 1e-6 * max(
                1, abs(first[field])
            ), (first, second)
    (output / "report.json").write_text(
        json.dumps(
            {"python": sys.version, "artifacts": artifacts, "results": results[0]},
            indent=2,
        )
    )
    print(
        f"Verified installed wheels and sdist-built wheels. Report: {output/'report.json'}"
    )


if __name__ == "__main__":
    main()
