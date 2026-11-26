"""시험 전용 입력 생성기. 운영 코드에는 포함하지 않는다."""
from childlock.validator import parse_snapshot


def raw_snapshot(**overrides):
    """모든 입력이 정상인 원시 스냅샷(정지, 시동 ON)을 만들고 일부 값을 덮어쓴다."""
    raw = {
        "timestamp_s": 100.0,
        "source_timestamp_s": 100.0,
        "vehicle_speed_kph": 0.0,
        "gear": "P",
        "crash_status": "NONE",
        "rear_left_approach_risk": False,
        "rear_right_approach_risk": False,
        "fire_detected": False,
        "overtemperature_detected": False,
        "adult_present": False,
        "isofix_left": False,
        "isofix_right": False,
        "ignition_on": True,
        "sensor_fault": False,
    }
    raw.update(overrides)
    return raw


def snapshot(**overrides):
    """정상 스냅샷 객체를 만든다. 입력이 잘못되면 시험이 즉시 실패한다."""
    result = parse_snapshot(raw_snapshot(**overrides))
    assert result.snapshot is not None, result.errors
    return result.snapshot
