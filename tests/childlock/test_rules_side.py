"""측별 규칙 시험: 접근위험, ISOFIX, 시동 OFF, 자동 잠금, 운전자 명령.

SWR-001~006, 009, 018, 020
"""
import pytest

from childlock.models import (
    Action,
    DriverCommand,
    LockOutput,
    ReasonCode,
    Side,
    SideMemory,
    SideVerdict,
    Source,
)
from childlock.rules import (
    rule_approach_risk,
    rule_auto_lock,
    rule_driver_command,
    rule_ignition_off,
    rule_isofix,
)
from tests.childlock.factories import snapshot

LOCK, RELEASE = LockOutput.LOCK, LockOutput.RELEASE
LEFT, RIGHT, ALL = Side.LEFT, Side.RIGHT, Side.ALL


def _cmd(side=Side.ALL, action=Action.UNLOCK):
    return DriverCommand(side, action, Source.AVN)


# --- 접근위험 (SWR-005, 006, 009) -------------------------------------------------


def test_no_risk_means_approach_rule_decides_nothing():
    assert rule_approach_risk(LEFT, snapshot(), _cmd(), SideMemory(), 1000) is None


def test_risk_locks_only_the_risky_side():
    snap = snapshot(rear_left_approach_risk=True)
    assert rule_approach_risk(RIGHT, snap, None, SideMemory(), 0) is None
    verdict = rule_approach_risk(LEFT, snap, None, SideMemory(), 0)
    assert verdict == SideVerdict(LOCK, ReasonCode.APPROACH_RISK_LEFT)


def test_right_side_uses_right_reason_code():
    snap = snapshot(rear_right_approach_risk=True)
    verdict = rule_approach_risk(RIGHT, snap, None, SideMemory(), 0)
    assert verdict.reason is ReasonCode.APPROACH_RISK_RIGHT


def test_first_release_request_is_suppressed_and_time_is_remembered():
    snap = snapshot(rear_left_approach_risk=True)
    verdict = rule_approach_risk(LEFT, snap, _cmd(), SideMemory(), 5000)
    assert verdict == SideVerdict(LOCK, ReasonCode.APPROACH_RISK_LEFT, False, 5000, False)


def test_release_request_for_the_other_side_does_not_start_suppression():
    snap = snapshot(rear_left_approach_risk=True)
    verdict = rule_approach_risk(LEFT, snap, _cmd(side=RIGHT), SideMemory(), 5000)
    assert verdict.suppressed_since_ms is None


def test_repeat_within_10_seconds_inclusive_becomes_override():
    snap = snapshot(rear_left_approach_risk=True)
    remembered = SideMemory(LOCK, suppressed_since_ms=5000)
    verdict = rule_approach_risk(LEFT, snap, _cmd(), remembered, 15000)
    assert verdict == SideVerdict(RELEASE, ReasonCode.APPROACH_OVERRIDE, True, 5000, True)


def test_repeat_after_10_seconds_is_suppressed_again_with_new_window():
    snap = snapshot(rear_left_approach_risk=True)
    remembered = SideMemory(LOCK, suppressed_since_ms=5000)
    verdict = rule_approach_risk(LEFT, snap, _cmd(), remembered, 15001)
    assert verdict == SideVerdict(LOCK, ReasonCode.APPROACH_RISK_LEFT, False, 15001, False)


def test_override_stays_released_while_risk_persists():
    snap = snapshot(rear_left_approach_risk=True)
    remembered = SideMemory(RELEASE, suppressed_since_ms=5000, override_active=True)
    verdict = rule_approach_risk(LEFT, snap, None, remembered, 99000)
    assert verdict == SideVerdict(RELEASE, ReasonCode.APPROACH_OVERRIDE, True, 5000, True)


def test_lock_command_ends_override_and_locks():
    snap = snapshot(rear_left_approach_risk=True)
    remembered = SideMemory(RELEASE, suppressed_since_ms=5000, override_active=True)
    verdict = rule_approach_risk(LEFT, snap, _cmd(action=Action.LOCK), remembered, 20000)
    assert verdict == SideVerdict(LOCK, ReasonCode.DRIVER_COMMAND, False, None, False)


def test_lock_command_during_risk_keeps_suppression_time():
    snap = snapshot(rear_left_approach_risk=True)
    remembered = SideMemory(LOCK, suppressed_since_ms=5000)
    verdict = rule_approach_risk(LEFT, snap, _cmd(action=Action.LOCK), remembered, 6000)
    assert verdict == SideVerdict(LOCK, ReasonCode.APPROACH_RISK_LEFT, False, 5000, False)


# --- ISOFIX (SWR-018) ------------------------------------------------------------


def test_isofix_locks_only_its_side():
    snap = snapshot(isofix_left=True)
    assert rule_isofix(LEFT, snap) == SideVerdict(LOCK, ReasonCode.ISOFIX_LEFT)
    assert rule_isofix(RIGHT, snap) is None


def test_isofix_right_uses_right_reason_code():
    verdict = rule_isofix(RIGHT, snapshot(isofix_right=True))
    assert verdict == SideVerdict(LOCK, ReasonCode.ISOFIX_RIGHT)


# --- 시동 OFF (SWR-020) ----------------------------------------------------------


def test_ignition_off_releases_with_reason():
    assert rule_ignition_off(snapshot(ignition_on=False)) == SideVerdict(
        RELEASE, ReasonCode.IGNITION_OFF
    )


def test_ignition_on_decides_nothing():
    assert rule_ignition_off(snapshot(ignition_on=True)) is None


# --- 자동 잠금과 일반 해제 조건 (SWR-003, 004) ---------------------------------------


@pytest.mark.parametrize(
    ("speed", "locks"), [(2.9, False), (3.0, True), (3.1, True), (300.0, True)]
)
def test_auto_lock_boundary_at_3_kph(speed, locks):
    verdict = rule_auto_lock(LEFT, snapshot(vehicle_speed_kph=speed), None)
    assert (verdict == SideVerdict(LOCK, ReasonCode.AUTO_LOCK_SPEED)) is locks
    assert (verdict is None) is (not locks)


def test_release_command_while_moving_is_denied_with_reason():
    verdict = rule_auto_lock(RIGHT, snapshot(vehicle_speed_kph=3.0), _cmd())
    assert verdict == SideVerdict(LOCK, ReasonCode.RELEASE_DENIED_MOVING)


def test_release_command_for_other_side_does_not_change_reason():
    verdict = rule_auto_lock(RIGHT, snapshot(vehicle_speed_kph=10.0), _cmd(side=LEFT))
    assert verdict.reason is ReasonCode.AUTO_LOCK_SPEED


def test_lock_command_while_moving_keeps_auto_lock_reason():
    verdict = rule_auto_lock(LEFT, snapshot(vehicle_speed_kph=10.0), _cmd(action=Action.LOCK))
    assert verdict.reason is ReasonCode.AUTO_LOCK_SPEED


# --- 운전자 명령 (SWR-001, 002) ---------------------------------------------------


@pytest.mark.parametrize(
    ("cmd_side", "left_applies", "right_applies"),
    [(LEFT, True, False), (RIGHT, False, True), (ALL, True, True)],
)
def test_command_applies_only_to_selected_sides(cmd_side, left_applies, right_applies):
    cmd = _cmd(side=cmd_side, action=Action.LOCK)
    assert (rule_driver_command(LEFT, cmd) is not None) is left_applies
    assert (rule_driver_command(RIGHT, cmd) is not None) is right_applies


@pytest.mark.parametrize(
    ("action", "output"), [(Action.LOCK, LOCK), (Action.UNLOCK, RELEASE)]
)
def test_command_action_maps_to_output(action, output):
    verdict = rule_driver_command(LEFT, _cmd(side=LEFT, action=action))
    assert verdict == SideVerdict(output, ReasonCode.DRIVER_COMMAND)


def test_no_command_decides_nothing():
    assert rule_driver_command(LEFT, None) is None
