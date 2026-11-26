"""컨트롤러 시험: 평가주기 오케스트레이션 (SWR-013, 016, 023)."""
from childlock.controller import Controller
from childlock.models import LockOutput, ReasonCode, State
from tests.childlock.factories import raw_snapshot

LOCK, RELEASE = LockOutput.LOCK, LockOutput.RELEASE
LOCK_ALL = {"side": "all", "action": "lock", "source": "avn"}


def test_valid_step_is_accepted_logged_and_remembered():
    ctl = Controller()
    result = ctl.step(raw_snapshot(), LOCK_ALL)
    assert result.accepted is True
    assert result.errors == ()
    assert (result.decision.lock_left, result.decision.lock_right) == (LOCK, LOCK)
    assert [e.event_id for e in ctl.events()] == [1]
    assert ctl.status() == result.decision


def test_outputs_persist_to_next_cycle_without_command():
    ctl = Controller()
    ctl.step(raw_snapshot(timestamp_s=1.0), LOCK_ALL)
    result = ctl.step(raw_snapshot(timestamp_s=1.05))
    assert (result.decision.lock_left, result.decision.lock_right) == (LOCK, LOCK)
    assert result.decision.priority_reason is ReasonCode.NO_CHANGE


def test_invalid_snapshot_is_rejected_before_evaluation_and_outputs_stay():
    ctl = Controller()
    ctl.step(raw_snapshot(timestamp_s=1.0), LOCK_ALL)
    bad = raw_snapshot(timestamp_s=1.05, vehicle_speed_kph=301.0, crash_status="CONFIRMED")
    result = ctl.step(bad)
    assert result.accepted is False
    assert "vehicle_speed_kph" in result.errors[0]
    assert (result.decision.lock_left, result.decision.lock_right) == (LOCK, LOCK)
    assert result.decision.priority_reason is ReasonCode.INPUT_INVALID
    assert result.decision.input_validity["speed"] == "INVALID"
    assert result.decision.input_validity["command"] == "VALID"
    assert ctl.events()[-1].reason_code is ReasonCode.INPUT_INVALID


def test_invalid_command_rejects_the_whole_step():
    ctl = Controller()
    bad_command = {"side": "x", "action": "lock", "source": "avn"}
    result = ctl.step(raw_snapshot(crash_status="CONFIRMED"), bad_command)
    assert result.accepted is False
    assert result.decision.priority_reason is ReasonCode.INPUT_INVALID
    assert result.decision.input_validity["command"] == "INVALID"
    assert (result.decision.lock_left, result.decision.lock_right) == (RELEASE, RELEASE)


def test_first_invalid_step_uses_initial_state():
    result = Controller().step({})
    assert result.decision.state is State.OFF
    assert (result.decision.lock_left, result.decision.lock_right) == (RELEASE, RELEASE)


def test_status_before_any_input_is_initial_off_and_released():
    decision = Controller().status()
    assert decision.state is State.OFF
    assert (decision.lock_left, decision.lock_right) == (RELEASE, RELEASE)
    assert decision.priority_reason is ReasonCode.NO_CHANGE


def test_tick_before_any_input_reports_no_input_and_logs_nothing():
    ctl = Controller()
    result = ctl.tick(5.0)
    assert result.accepted is False
    assert result.errors == ("입력이 아직 없습니다",)
    assert ctl.events() == []


def test_tick_goes_degraded_only_after_input_is_older_than_200_ms():
    ctl = Controller()
    ctl.step(raw_snapshot(timestamp_s=100.0), LOCK_ALL)
    assert ctl.tick(100.2).decision.state is State.NORMAL
    stale = ctl.tick(100.201).decision
    assert stale.state is State.DEGRADED
    assert stale.priority_reason is ReasonCode.INPUT_STALE
    assert (stale.lock_left, stale.lock_right) == (LOCK, LOCK)


def test_degraded_is_reported_within_100_ms_of_exceeding_200_ms_at_50_ms_cycle():
    ctl = Controller()
    ctl.step(raw_snapshot(timestamp_s=100.0))
    first_degraded_ms = None
    for cycle in range(1, 12):
        now = 100.0 + cycle * 0.05
        if ctl.tick(now).decision.state is State.DEGRADED:
            first_degraded_ms = cycle * 50
            break
    assert first_degraded_ms is not None
    assert first_degraded_ms - 200 <= 100


def test_recovers_to_normal_when_fresh_input_returns():
    ctl = Controller()
    ctl.step(raw_snapshot(timestamp_s=100.0))
    ctl.tick(101.0)
    result = ctl.step(raw_snapshot(timestamp_s=101.05))
    assert result.decision.state is State.NORMAL


def test_crash_confirmed_releases_within_one_cycle_and_is_logged():
    ctl = Controller()
    ctl.step(raw_snapshot(timestamp_s=1.0), LOCK_ALL)
    result = ctl.step(raw_snapshot(timestamp_s=1.05, crash_status="CONFIRMED"))
    assert (result.decision.lock_left, result.decision.lock_right) == (RELEASE, RELEASE)
    assert ctl.events()[-1].reason_code is ReasonCode.CRASH_CONFIRMED
