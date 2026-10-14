"""Require the pinned original workbook rather than a disposable audit file."""

import hashlib
from pathlib import Path
from subprocess import CalledProcessError

import pytest


def test_baseline_verifies_bytes_and_removes_temporary_file(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "dev"))
    import premise_vehicle_baseline as baseline

    content = b"workbook fixture"
    monkeypatch.setitem(
        baseline.WORKBOOKS,
        "car",
        ("original.xlsx", hashlib.sha256(content).hexdigest()),
    )
    calls, temporary = [], []

    def show(command, **kwargs):
        calls.append(command)
        return content

    def read(path):
        temporary.append(path)
        assert path.read_bytes() == content
        return [{"name": "original identity"}], [], []

    monkeypatch.setattr(baseline.subprocess, "check_output", show)
    monkeypatch.setattr(baseline, "read_workbook", read)
    data, sha = baseline.load_baseline("car", "/unused/premise")
    assert data == [{"name": "original identity"}]
    assert sha == hashlib.sha256(content).hexdigest()
    assert baseline.REVISION in calls[0][-1]
    assert not temporary[0].exists()
    monkeypatch.setitem(baseline.WORKBOOKS, "car", ("original.xlsx", "incorrect"))
    with pytest.raises(ValueError, match="hash mismatch"):
        baseline.load_baseline("car", "/unused/premise")


def test_missing_history_fails_with_fetch_instructions(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "dev"))
    import premise_vehicle_baseline as baseline

    def missing(*args, **kwargs):
        raise CalledProcessError(128, "git show")

    monkeypatch.setattr(baseline.subprocess, "check_output", missing)
    with pytest.raises(RuntimeError, match="fetch that history"):
        baseline.load_baseline("truck", "/unused/premise")
