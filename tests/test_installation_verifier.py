"""Command limits must stop stalled verification without losing diagnostics."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_installation.py"


def test_command_timeout_preserves_child_output(tmp_path):
    spec = importlib.util.spec_from_file_location("verify_installation", SCRIPT)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
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
