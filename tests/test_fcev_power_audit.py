"""Physical unit boundaries and optimistic storage bounds in the offline audit."""

import importlib.util
from pathlib import Path

import pytest

AUDIT_PATH = Path(__file__).resolve().parents[1] / "dev/audit_premise_fcev_power.py"
if not AUDIT_PATH.is_file():
    pytest.skip(
        "Offline audit is only distributed in the checkout.", allow_module_level=True
    )
SPEC = importlib.util.spec_from_file_location("fcev_power_audit", AUDIT_PATH)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def test_motor_shaft_rating_is_not_net_electrical_power():
    # 90 kW at the shaft needs 100 kW electrical + 5 kW auxiliaries.
    # A 92 kW gross stack with 15% parasitics supplies only 80 kW.
    required, net, buffer = AUDIT.dc_rating(90, 0.9, 5, 92, 1.15)
    assert (required, net, buffer) == pytest.approx((105, 80, 25))


def test_storage_can_recharge_between_two_discharge_events():
    # Each event draws 10 kJ; 10 kJ, not the sum 20 kJ, is required.
    assert AUDIT.storage_lower_bound(
        [20, 0, 20, 0], [0] * 4, 10, 1, 1
    ) == pytest.approx(10 / 3600)


def test_periodic_storage_bound_includes_drawdown_across_cycle_boundary():
    # The last and first events occur back-to-back when repeating.
    assert AUDIT.storage_lower_bound(
        [20, 0, 0, 20], [0] * 4, 10, 1, 1
    ) == pytest.approx(20 / 3600)


def test_storage_internal_losses_are_applied_in_the_correct_direction():
    # 8 kJ DC discharge needs 10 kJ stored. 20 kJ spare FC at 50%
    # charging efficiency exactly replenishes those 10 kJ.
    assert AUDIT.storage_lower_bound([28, 0], [0, 0], 20, 0.5, 0.8) == pytest.approx(
        10 / 3600
    )


def test_regeneration_can_supply_the_optimistic_recharge():
    assert AUDIT.storage_lower_bound([8, 0], [0, 20], 0, 0.5, 0.8) == pytest.approx(
        10 / 3600
    )


def test_energy_deficient_period_cannot_repeat_with_finite_storage():
    assert AUDIT.storage_lower_bound([20, 20], [0, 0], 10, 1, 1) is None


@pytest.mark.parametrize("eta", [0, 1.1, float("nan")])
def test_invalid_efficiency_is_rejected(eta):
    with pytest.raises(ValueError):
        AUDIT.dc_rating(100, eta, 0, 90, 1.1)
    with pytest.raises(ValueError):
        AUDIT.storage_lower_bound([10], [0], 10, eta, 0.9)
