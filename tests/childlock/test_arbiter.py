"""우선순위 중재 시험 (SWR-022 및 시스템 수준 수용기준).

우선순위표: 충돌 확정 > 비상 > 센서 고장 > 충돌 미확정 > 접근위험 > ISOFIX
> 시동 OFF > 자동 잠금 > 운전자 명령
"""
from childlock.arbiter import decide
from childlock.models import (
    Action,
    DriverCommand,
    LockOutput,
    Memory,
    ReasonCode,
    Side,
    SideMemory,
    Source,
    State,
)
from tests.childlock.factories import all_valid, snapshot

LOCK, RELEASE = LockOutput.LOCK, LockOutput.RELEASE


def _cmd(side=Side.ALL, action=Action.UNLOCK):
    return DriverCommand(side, action, Source.AVN)


def _mem(left=RELEASE, right=RELEASE):
    return Memory(SideMemory(last=left), SideMemory(last=right))


def _decide(snap, cmd=None, mem=None):
    return decide(snap, cmd, mem or Memory(), all_valid())


def _outputs(decision):
    return decision.lock_left, decision.lock_right


# --- 기본 동작과 상태 ---------------------------------------------------------------


def test_idle_cycle_keeps_previous_outputs_with_no_change_reason():
    decision, new_mem = _decide(snapshot(), mem=_mem(LOCK, RELEASE))
    assert _outputs(decision) == (LOCK, RELEASE)
    assert decision.state is State.NORMAL
    assert decision.priority_reason is ReasonCode.NO_CHANGE
    assert new_mem == _mem(LOCK, RELEASE)


def test_output_decided_in_one_cycle_is_remembered_for_the_next():
    _, mem = _decide(snapshot(), _cmd(action=Action.LOCK))
    decision, _ = _decide(snapshot(), None, mem)
    assert _outputs(decision) == (LOCK, LOCK)
    assert decision.priority_reason is ReasonCode.NO_CHANGE


def test_ignition_off_state_is_off_and_outputs_released():
    decision, _ = _decide(snapshot(ignition_on=False), mem=_mem(LOCK, LOCK))
    assert _outputs(decision) == (RELEASE, RELEASE)
    assert decision.state is State.OFF
    assert decision.priority_reason is ReasonCode.IGNITION_OFF


# --- 입력 stale (순위 0, SWR-013) ----------------------------------------------------


def test_stale_input_holds_outputs_and_reports_degraded():
    snap = snapshot(timestamp_s=100.201, source_timestamp_s=100.0, crash_status="CONFIRMED")
    decision, new_mem = _decide(snap, mem=_mem(LOCK, RELEASE))
    assert _outputs(decision) == (LOCK, RELEASE)
    assert decision.state is State.DEGRADED
    assert decision.priority_reason is ReasonCode.INPUT_STALE
    assert set(decision.input_validity.values()) == {"STALE"}
    assert new_mem == _mem(LOCK, RELEASE)


def test_input_exactly_200_ms_old_is_still_fresh():
    snap = snapshot(timestamp_s=100.2, source_timestamp_s=100.0, crash_status="CONFIRMED")
    decision, _ = _decide(snap)
    assert decision.state is State.NORMAL
    assert decision.priority_reason is ReasonCode.CRASH_CONFIRMED


# --- 우선순위 쌍 (SWR-022) ----------------------------------------------------------


def test_crash_confirmed_beats_everything_and_stays_released():
    snap = snapshot(
        crash_status="CONFIRMED",
        rear_left_approach_risk=True,
        isofix_left=True,
        vehicle_speed_kph=50.0,
        sensor_fault=True,
    )
    decision, mem = _decide(snap, _cmd(action=Action.LOCK), _mem(LOCK, LOCK))
    assert _outputs(decision) == (RELEASE, RELEASE)
    assert decision.priority_reason is ReasonCode.CRASH_CONFIRMED
    later, _ = _decide(snapshot(crash_status="CONFIRMED", vehicle_speed_kph=50.0), None, mem)
    assert _outputs(later) == (RELEASE, RELEASE)


def test_released_outputs_persist_after_crash_status_returns_to_none():
    _, mem = _decide(snapshot(crash_status="CONFIRMED"), mem=_mem(LOCK, LOCK))
    decision, _ = _decide(snapshot(crash_status="NONE"), None, mem)
    assert _outputs(decision) == (RELEASE, RELEASE)
    assert decision.priority_reason is ReasonCode.NO_CHANGE


def test_emergency_beats_sensor_fault_and_crash_pending():
    snap = snapshot(fire_detected=True, sensor_fault=True, crash_status="PENDING")
    decision, _ = _decide(snap, mem=_mem(LOCK, LOCK))
    assert _outputs(decision) == (RELEASE, RELEASE)
    assert decision.priority_reason is ReasonCode.FIRE
    assert decision.state is State.NORMAL


def test_adult_present_beats_approach_risk_per_user_decision():
    snap = snapshot(adult_present=True, rear_left_approach_risk=True)
    decision, _ = _decide(snap, mem=_mem(LOCK, LOCK))
    assert _outputs(decision) == (RELEASE, RELEASE)
    assert decision.priority_reason is ReasonCode.ADULT_PRESENT


def test_sensor_fault_holds_and_ignores_commands_and_pending_crash():
    snap = snapshot(sensor_fault=True, crash_status="PENDING", vehicle_speed_kph=50.0)
    decision, _ = _decide(snap, _cmd(), _mem(LOCK, RELEASE))
    assert _outputs(decision) == (LOCK, RELEASE)
    assert decision.state is State.FAULT
    assert decision.priority_reason is ReasonCode.SENSOR_FAULT


def test_crash_pending_holds_outputs_and_ignores_commands():
    decision, _ = _decide(snapshot(crash_status="PENDING"), _cmd(), _mem(LOCK, LOCK))
    assert _outputs(decision) == (LOCK, LOCK)
    assert decision.priority_reason is ReasonCode.CRASH_PENDING
    assert decision.state is State.NORMAL


def test_approach_risk_beats_ignition_off_on_that_side_only():
    snap = snapshot(rear_left_approach_risk=True, ignition_on=False)
    decision, _ = _decide(snap, mem=_mem(LOCK, LOCK))
    assert _outputs(decision) == (LOCK, RELEASE)
    assert decision.state is State.OFF
    assert decision.priority_reason is ReasonCode.APPROACH_RISK_LEFT


def test_isofix_beats_ignition_off_per_user_decision():
    decision, _ = _decide(snapshot(isofix_right=True, ignition_on=False), mem=_mem(LOCK, LOCK))
    assert _outputs(decision) == (RELEASE, LOCK)
    assert decision.state is State.OFF
    assert decision.priority_reason is ReasonCode.ISOFIX_RIGHT


def test_ignition_off_beats_auto_lock_and_commands():
    snap = snapshot(ignition_on=False, vehicle_speed_kph=10.0)
    decision, _ = _decide(snap, _cmd(action=Action.LOCK))
    assert _outputs(decision) == (RELEASE, RELEASE)
    assert decision.priority_reason is ReasonCode.IGNITION_OFF


def test_auto_lock_beats_release_command_and_reports_denial():
    decision, _ = _decide(snapshot(vehicle_speed_kph=3.0), _cmd())
    assert _outputs(decision) == (LOCK, LOCK)
    assert decision.priority_reason is ReasonCode.RELEASE_DENIED_MOVING


def test_release_command_applies_when_stopped():
    decision, _ = _decide(snapshot(vehicle_speed_kph=2.9), _cmd(), _mem(LOCK, LOCK))
    assert _outputs(decision) == (RELEASE, RELEASE)
    assert decision.priority_reason is ReasonCode.DRIVER_COMMAND


def test_isofix_side_refuses_release_command_but_other_side_follows_it():
    decision, _ = _decide(snapshot(isofix_left=True), _cmd(), _mem(LOCK, LOCK))
    assert _outputs(decision) == (LOCK, RELEASE)
    assert decision.priority_reason is ReasonCode.ISOFIX_LEFT


# --- 접근위험과 override (SWR-005, 006, 009) -----------------------------------------


def test_approach_risk_on_one_side_does_not_affect_the_other_side():
    snap = snapshot(rear_left_approach_risk=True)
    decision, _ = _decide(snap, _cmd(), _mem(RELEASE, LOCK))
    assert _outputs(decision) == (LOCK, RELEASE)
    assert decision.priority_reason is ReasonCode.APPROACH_RISK_LEFT


def test_repeat_within_10_seconds_overrides_and_override_persists():
    risky = {"rear_left_approach_risk": True}
    _, mem = _decide(snapshot(timestamp_s=100.0, **risky), _cmd(side=Side.LEFT))
    decision, mem = _decide(snapshot(timestamp_s=110.0, **risky), _cmd(side=Side.LEFT), mem)
    assert decision.lock_left is RELEASE
    assert decision.override is True
    assert decision.priority_reason is ReasonCode.APPROACH_OVERRIDE
    later, mem = _decide(snapshot(timestamp_s=111.0, **risky), None, mem)
    assert later.lock_left is RELEASE
    assert later.override is True
    cleared, mem = _decide(snapshot(timestamp_s=112.0), None, mem)
    assert cleared.override is False
    assert mem.left == SideMemory(RELEASE, None, False)


def test_repeat_after_10_seconds_is_suppressed_again():
    risky = {"rear_left_approach_risk": True}
    _, mem = _decide(snapshot(timestamp_s=100.0, **risky), _cmd(side=Side.LEFT))
    decision, _ = _decide(snapshot(timestamp_s=110.001, **risky), _cmd(side=Side.LEFT), mem)
    assert decision.lock_left is LOCK
    assert decision.override is False


def test_suppression_memory_is_cleared_when_risk_disappears():
    _, mem = _decide(snapshot(rear_left_approach_risk=True), _cmd(side=Side.LEFT))
    assert mem.left.suppressed_since_ms == 100000
    _, mem = _decide(snapshot(rear_left_approach_risk=False), None, mem)
    assert mem.left.suppressed_since_ms is None


# --- 이유코드 선택 --------------------------------------------------------------------


def test_priority_reason_is_the_higher_priority_of_the_two_sides():
    decision, _ = _decide(snapshot(isofix_right=True), _cmd(side=Side.LEFT, action=Action.LOCK))
    assert decision.priority_reason is ReasonCode.ISOFIX_RIGHT


def test_priority_reason_tie_prefers_left_side():
    decision, _ = _decide(snapshot(isofix_left=True, isofix_right=True))
    assert decision.priority_reason is ReasonCode.ISOFIX_LEFT
