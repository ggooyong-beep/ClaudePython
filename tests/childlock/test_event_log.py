"""이벤트 로그 시험 (SWR-010, 011, 012)."""
import dataclasses

import pytest

from childlock.event_log import Event, EventLog
from childlock.models import Decision, LockOutput, ReasonCode, State

pytestmark = [
    pytest.mark.swr("SWR-010"),
    pytest.mark.swr("SWR-011"),
    pytest.mark.swr("SWR-012"),
]


def _decision(reason=ReasonCode.NO_CHANGE, validity=None):
    return Decision(
        LockOutput.LOCK, LockOutput.RELEASE, State.NORMAL, reason, validity or {"speed": "VALID"}
    )


def test_event_ids_are_unique_and_increasing_from_one():
    log = EventLog()
    first = log.append(_decision(), 1.0)
    second = log.append(_decision(), 1.05)
    assert (first.event_id, second.event_id) == (1, 2)


def test_event_carries_exactly_the_allowed_fields():
    names = {f.name for f in dataclasses.fields(Event)}
    assert names == {
        "event_id",
        "timestamp_s",
        "state",
        "lock_left",
        "lock_right",
        "reason_code",
        "priority_reason",
        "input_validity",
    }


def test_event_copies_decision_values():
    event = EventLog().append(_decision(ReasonCode.FIRE), 12.5)
    assert event.timestamp_s == 12.5
    assert event.state is State.NORMAL
    assert (event.lock_left, event.lock_right) == (LockOutput.LOCK, LockOutput.RELEASE)
    assert event.reason_code is event.priority_reason is ReasonCode.FIRE
    assert event.input_validity == {"speed": "VALID"}


def test_event_keeps_validity_snapshot_even_if_source_dict_changes():
    validity = {"speed": "VALID"}
    event = EventLog().append(_decision(validity=validity), 1.0)
    validity["speed"] = "INVALID"
    assert event.input_validity == {"speed": "VALID"}


def test_only_latest_100_events_are_kept_in_order():
    log = EventLog()
    for index in range(101):
        log.append(_decision(), float(index))
    ids = [event.event_id for event in log.events()]
    assert ids == list(range(2, 102))


def test_exactly_100_events_are_all_kept():
    log = EventLog()
    for index in range(100):
        log.append(_decision(), float(index))
    assert [e.event_id for e in log.events()][0] == 1
    assert len(log.events()) == 100


def test_new_log_is_empty_so_restart_leaves_no_data():
    log = EventLog()
    log.append(_decision(), 1.0)
    assert EventLog().events() == []


def test_returned_list_is_a_copy():
    log = EventLog()
    log.append(_decision(), 1.0)
    log.events().clear()
    assert len(log.events()) == 1
