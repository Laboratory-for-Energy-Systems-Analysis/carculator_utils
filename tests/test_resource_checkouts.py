"""Recorded resource fingerprints must survive fresh Git checkouts on every OS."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from carculator_utils import DATA_DIR


@pytest.mark.parametrize("autocrlf", ["false", "true"])
@pytest.mark.parametrize("group", ["emission_factors", "IAM"])
def test_resource_fingerprints_survive_git_checkout(tmp_path, group, autocrlf):
    folder = DATA_DIR / group
    if group == "emission_factors":
        manifest = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
        hashes = {name: record["sha256"] for name, record in manifest["files"].items()}
    else:
        manifest = json.loads(
            (folder / "build_manifest.json").read_text(encoding="utf-8")
        )
        hashes = manifest["resource_hashes"]
    # Binary matrices already have exact-byte checks in test_iam_bundle.
    hashes = {
        name: digest
        for name, digest in hashes.items()
        if Path(name).suffix in {".csv", ".json", ".yaml", ".yml"}
    }
    assert hashes
    repository = tmp_path / "repository"
    repository.mkdir()
    shutil.copyfile(
        Path(__file__).resolve().parents[1] / ".gitattributes",
        repository / ".gitattributes",
    )
    prefix = Path("carculator_utils") / "data" / group
    for name in hashes:
        destination = repository / prefix / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(folder / name, destination)
    (repository / "unprotected.txt").write_bytes(b"first\nsecond\n")
    subprocess.run(["git", "init", "--quiet", str(repository)], check=True)
    subprocess.run(
        ["git", "-c", "core.autocrlf=input", "-c", "core.safecrlf=false", "add", "."],
        cwd=repository,
        check=True,
    )
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    subprocess.run(
        [
            "git",
            "-c",
            f"core.autocrlf={autocrlf}",
            "checkout-index",
            "--all",
            f"--prefix={checkout.as_posix()}/",
        ],
        cwd=repository,
        check=True,
    )
    newline = b"\r\n" if autocrlf == "true" else b"\n"
    assert (checkout / "unprotected.txt").read_bytes() == newline.join(
        [b"first", b"second", b""]
    )
    for name, expected in hashes.items():
        assert (
            hashlib.sha256((checkout / prefix / name).read_bytes()).hexdigest()
            == expected
        ), name
