"""전역 규칙 시험: 충돌, 비상, 센서 고장 (SWR-007, 008, 017, 021)."""
import pytest

from childlock.models import LockOutput, Memory, ReasonCode, SideMemory, State, Verdict
from childlock.rules import (
    rule_crash_confirmed,
    rule_crash_pending,
    rule_emergency,
    rule_sensor_fault,
)
from tests.childlock.factories import snapshot

LOCK, RELEASE = LockOutput.LOCK, LockOutput.RELEASE


def _memory(left=RELEASE, right=RELEASE):
    return Memory(SideMemory(last=left), SideMemory(last=right))


def test_crash_confirmed_releases_both_sides():
    verdict = rule_crash_confirmed(snapshot(crash_status="CONFIRMED"))
    assert verdict == Verdict(RELEASE, RELEASE, ReasonCode.CRASH_CONFIRMED, None)


@pytest.mark.parametrize("status", ["NONE", "PENDING"])
def test_crash_not_confirmed_decides_nothing(status):
    assert rule_crash_confirmed(snapshot(crash_status=status)) is None


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("fire_detected", ReasonCode.FIRE),
        ("overtemperature_detected", ReasonCode.OVERTEMPERATURE),
        ("adult_present", ReasonCode.ADULT_PRESENT),
    ],
)
def test_each_emergency_input_alone_releases_both_with_its_own_reason(field, reason):
    verdict = rule_emergency(snapshot(**{field: True}))
    assert verdict == Verdict(RELEASE, RELEASE, reason, None)


def test_emergency_reason_follows_fire_overtemperature_adult_order():
    verdict = rule_emergency(snapshot(fire_detected=True, adult_present=True))
    assert verdict.reason is ReasonCode.FIRE
    verdict = rule_emergency(snapshot(overtemperature_detected=True, adult_present=True))
    assert verdict.reason is ReasonCode.OVERTEMPERATURE


def test_no_emergency_decides_nothing():
    assert rule_emergency(snapshot()) is None


@pytest.mark.parametrize(("left", "right"), [(LOCK, RELEASE), (RELEASE, LOCK), (LOCK, LOCK)])
def test_sensor_fault_holds_previous_outputs_and_enters_fault(left, right):
    verdict = rule_sensor_fault(snapshot(sensor_fault=True), _memory(left, right))
    assert verdict == Verdict(left, right, ReasonCode.SENSOR_FAULT, State.FAULT)


def test_sensor_ok_decides_nothing():
    assert rule_sensor_fault(snapshot(), _memory(LOCK, LOCK)) is None


@pytest.mark.parametrize(("left", "right"), [(LOCK, RELEASE), (RELEASE, LOCK)])
def test_crash_pending_holds_previous_outputs(left, right):
    verdict = rule_crash_pending(snapshot(crash_status="PENDING"), _memory(left, right))
    assert verdict == Verdict(left, right, ReasonCode.CRASH_PENDING, None)


@pytest.mark.parametrize("status", ["NONE", "CONFIRMED"])
def test_crash_not_pending_does_not_hold(status):
    assert rule_crash_pending(snapshot(crash_status=status), _memory()) is None
