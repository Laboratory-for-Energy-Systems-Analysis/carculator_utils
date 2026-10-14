"""A stale generic pack must not acquire calibrated Mirai provenance."""

from pathlib import Path

import pytest


def test_adapter_accepts_paired_pack_and_rejects_stale_export(monkeypatch):
    pytest.importorskip("carculator.fuel_cell_battery")
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "dev"))
    from regenerate_premise_cars import validate_fcev_battery

    validate_fcev_battery(
        {
            "battery power": 63,
            "electric energy stored": 2.4864,
            "energy battery mass": 89.2,
        }
    )
    with pytest.raises(AssertionError):
        validate_fcev_battery(
            {
                "battery power": 39.61548,
                "electric energy stored": 4.462805,
                "energy battery mass": 26.564316,
            }
        )
