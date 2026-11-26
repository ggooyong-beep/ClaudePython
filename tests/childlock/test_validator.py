"""입력 검증 시험 (SWR-001, 002, 013)."""
import pytest

from childlock.models import CrashStatus, Gear
from childlock.validator import age_ms, is_stale, parse_command, parse_snapshot
from tests.childlock.factories import raw_snapshot, snapshot


def test_valid_input_is_parsed_with_all_groups_valid():
    result = parse_snapshot(raw_snapshot(vehicle_speed_kph=50, gear="D", crash_status="PENDING"))
    assert result.errors == ()
    assert result.snapshot.vehicle_speed_kph == 50.0
    assert result.snapshot.gear is Gear.D
    assert result.snapshot.crash_status is CrashStatus.PENDING
    assert set(result.validity.values()) == {"VALID"}


@pytest.mark.parametrize("speed", [0.0, 0.1, 299.9, 300.0])
def test_speed_inside_range_is_accepted(speed):
    assert parse_snapshot(raw_snapshot(vehicle_speed_kph=speed)).snapshot is not None


@pytest.mark.parametrize("speed", [-0.1, 300.1, float("nan"), float("inf"), True, "50", None])
def test_speed_outside_range_or_wrong_type_is_rejected(speed):
    result = parse_snapshot(raw_snapshot(vehicle_speed_kph=speed))
    assert result.snapshot is None
    assert result.validity["speed"] == "INVALID"
    assert result.validity["gear"] == "VALID"
    assert len(result.errors) == 1


def test_missing_field_is_rejected_and_named_in_error():
    raw = raw_snapshot()
    del raw["ignition_on"]
    result = parse_snapshot(raw)
    assert result.snapshot is None
    assert result.validity["ignition"] == "INVALID"
    assert "ignition_on" in result.errors[0]


@pytest.mark.parametrize(
    ("key", "bad", "group"),
    [
        ("gear", "X", "gear"),
        ("gear", "d", "gear"),
        ("gear", 1, "gear"),
        ("crash_status", "MAYBE", "crash"),
        ("rear_left_approach_risk", 1, "approach"),
        ("fire_detected", "true", "emergency"),
        ("isofix_right", None, "isofix"),
        ("sensor_fault", 0, "sensor_fault"),
        ("timestamp_s", -1.0, "time"),
        ("source_timestamp_s", "0", "time"),
    ],
)
def test_wrong_enum_bool_or_time_values_are_rejected(key, bad, group):
    result = parse_snapshot(raw_snapshot(**{key: bad}))
    assert result.snapshot is None
    assert result.validity[group] == "INVALID"


def test_multiple_errors_are_all_reported():
    result = parse_snapshot(raw_snapshot(gear="X", fire_detected=1))
    assert len(result.errors) == 2
    assert result.validity["gear"] == result.validity["emergency"] == "INVALID"


@pytest.mark.parametrize(
    ("timestamp", "source", "age", "stale"),
    [(100.2, 100.0, 200, False), (100.201, 100.0, 201, True), (100.0, 100.0, 0, False)],
)
def test_age_and_stale_boundary_at_200_ms(timestamp, source, age, stale):
    snap = snapshot(timestamp_s=timestamp, source_timestamp_s=source)
    assert age_ms(snap) == age
    assert is_stale(snap) is stale


def test_no_command_is_valid_and_empty():
    result = parse_command(None)
    assert result.command is None
    assert result.errors == ()


def test_valid_command_is_parsed():
    result = parse_command({"side": "left", "action": "unlock", "source": "voice"})
    assert result.command.side.value == "left"
    assert result.command.action.value == "unlock"
    assert result.command.source.value == "voice"


@pytest.mark.parametrize(
    "raw",
    [
        {"side": "front", "action": "lock", "source": "avn"},
        {"side": "all", "action": "toggle", "source": "avn"},
        {"side": "all", "action": "lock", "source": "key"},
        {"side": "all", "action": "lock"},
        {},
    ],
)
def test_invalid_command_is_rejected(raw):
    result = parse_command(raw)
    assert result.command is None
    assert result.errors
