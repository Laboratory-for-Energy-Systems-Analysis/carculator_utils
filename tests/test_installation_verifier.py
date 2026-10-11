"""Command limits must stop stalled verification without losing diagnostics."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_installation.py"


@pytest.fixture
def verifier():
    spec = importlib.util.spec_from_file_location("verify_installation", SCRIPT)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    return verifier


def test_command_timeout_preserves_child_output(tmp_path, verifier):
    log = tmp_path / "installation.log"
    with pytest.raises(subprocess.TimeoutExpired):
        verifier.run(
            [
                sys.executable,
                "-u",
                "-c",
                "import time; print('verification started'); time.sleep(60)",
            ],
            tmp_path,
            log,
            os.environ.copy(),
            timeout=2,
        )
    assert "verification started" in log.read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("seconds", ["0", "-1"])
def test_invalid_test_timeout_fails_before_building(tmp_path, seconds):
    output = tmp_path / "verification"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repositories",
            str(tmp_path),
            "--output",
            str(output),
            "--run-tests",
            "--test-timeout",
            seconds,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 2
    assert "--test-timeout must be greater than zero" in result.stderr
    assert not output.exists()


def test_test_shards_cover_each_module_once(tmp_path, verifier):
    tests = tmp_path / "tests"
    tests.mkdir()
    files = [tests / f"test_case_{index}.py" for index in range(8)]
    for path in files:
        path.write_text("def test_example(): pass\n")
    (tests / "helper.py").write_text("raise AssertionError('not a test module')\n")
    shards = [verifier.test_paths(tmp_path, index, 3) for index in range(3)]
    flattened = [path for shard in shards for path in shard]
    assert sorted(flattened) == files
    assert len(flattened) == len(set(flattened))
    assert max(map(len, shards)) - min(map(len, shards)) == 1
    assert verifier.test_paths(tmp_path, 0, 1) == [tests]


def test_empty_test_shard_fails_explicitly(tmp_path, verifier):
    (tmp_path / "tests").mkdir()
    with pytest.raises(ValueError, match="is empty"):
        verifier.test_paths(tmp_path, 0, 3)


@pytest.mark.parametrize("count,index", [(0, 0), (-1, 0), (3, -1), (3, 3)])
def test_invalid_shards_fail_before_building(tmp_path, count, index):
    output = tmp_path / "verification"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repositories",
            str(tmp_path),
            "--output",
            str(output),
            "--run-tests",
            "--test-shards",
            str(count),
            "--test-shard-index",
            str(index),
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 2
    assert "--test-shard-index" in result.stderr
    assert not output.exists()
