"""입력 검증 (SWR-001, 002, 013).

@file validator.py
@brief 원시 입력(dict)의 형식과 범위를 검사하고 freshness를 계산한다.
"""
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from functools import partial

from childlock.models import (
    SPEED_MAX_KPH,
    SPEED_MIN_KPH,
    STALE_MS,
    Action,
    CrashStatus,
    DriverCommand,
    Gear,
    Side,
    Source,
    VehicleSnapshot,
)

VALID = "VALID"
INVALID = "INVALID"
_TIME_MAX_S = 1e12

Reader = Callable[[Mapping[str, object], str], tuple[object, str | None]]


@dataclass(frozen=True, slots=True)
class ParseResult:
    """스냅샷 검증 결과. 오류가 있으면 snapshot은 None이다."""

    snapshot: VehicleSnapshot | None
    validity: dict[str, str]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CommandResult:
    """명령 검증 결과. 명령이 없거나 오류이면 command는 None이다."""

    command: DriverCommand | None
    errors: tuple[str, ...]


def _read_bool(raw: Mapping[str, object], key: str) -> tuple[object, str | None]:
    """불리언 값을 읽는다. 정수 0/1과 문자열은 거절한다.

    @param raw 원시 입력
    @param key 필드 이름
    @return (값, 오류 메시지)
    """
    value = raw.get(key)
    if isinstance(value, bool):
        return value, None
    return None, f"{key}: 불리언이 필요합니다 ({value!r})"


def _read_enum(
    raw: Mapping[str, object], key: str, enum_cls: type[Enum]
) -> tuple[object, str | None]:
    """열거형 값을 읽는다. 정의되지 않은 값과 문자열이 아닌 값은 거절한다.

    @param raw 원시 입력
    @param key 필드 이름
    @param enum_cls 허용 값을 정의한 열거형
    @return (열거 값, 오류 메시지)
    """
    value = raw.get(key)
    if isinstance(value, str):
        try:
            return enum_cls(value), None
        except ValueError:
            pass
    return None, f"{key}: 허용되지 않은 값입니다 ({value!r})"


def _read_float(
    raw: Mapping[str, object], key: str, low: float, high: float
) -> tuple[object, str | None]:
    """범위 안의 유한한 숫자를 읽는다. 불리언, NaN, 무한대는 거절한다.

    @param raw 원시 입력
    @param key 필드 이름
    @param low 허용 최솟값(포함)
    @param high 허용 최댓값(포함)
    @return (값, 오류 메시지)
    """
    value = raw.get(key)
    is_number = isinstance(value, int | float) and not isinstance(value, bool)
    if is_number and math.isfinite(value) and low <= value <= high:
        return float(value), None
    return None, f"{key}: {low}~{high} 범위의 숫자가 필요합니다 ({value!r})"


_SPECS: tuple[tuple[str, str, Reader], ...] = (
    ("timestamp_s", "time", partial(_read_float, low=0.0, high=_TIME_MAX_S)),
    ("source_timestamp_s", "time", partial(_read_float, low=0.0, high=_TIME_MAX_S)),
    ("vehicle_speed_kph", "speed", partial(_read_float, low=SPEED_MIN_KPH, high=SPEED_MAX_KPH)),
    ("gear", "gear", partial(_read_enum, enum_cls=Gear)),
    ("crash_status", "crash", partial(_read_enum, enum_cls=CrashStatus)),
    ("rear_left_approach_risk", "approach", _read_bool),
    ("rear_right_approach_risk", "approach", _read_bool),
    ("fire_detected", "emergency", _read_bool),
    ("overtemperature_detected", "emergency", _read_bool),
    ("adult_present", "emergency", _read_bool),
    ("isofix_left", "isofix", _read_bool),
    ("isofix_right", "isofix", _read_bool),
    ("ignition_on", "ignition", _read_bool),
    ("sensor_fault", "sensor_fault", _read_bool),
)
_GROUPS = tuple(dict.fromkeys(group for _, group, _ in _SPECS))


def parse_snapshot(raw: Mapping[str, object]) -> ParseResult:
    """원시 입력을 검증해 스냅샷을 만든다 (SWR-013).

    @param raw 필드 이름을 키로 갖는 원시 입력
    @return 검증 결과. 오류가 하나라도 있으면 snapshot은 None
    """
    values: dict[str, object] = {}
    errors: list[str] = []
    bad_groups: set[str] = set()
    for key, group, reader in _SPECS:
        value, error = reader(raw, key)
        if error:
            errors.append(error)
            bad_groups.add(group)
        else:
            values[key] = value
    validity = {group: INVALID if group in bad_groups else VALID for group in _GROUPS}
    snapshot = None if errors else VehicleSnapshot(**values)
    return ParseResult(snapshot, validity, tuple(errors))


def parse_command(raw: Mapping[str, object] | None) -> CommandResult:
    """운전자 명령을 검증한다 (SWR-001, 002).

    @param raw 명령 원시 입력 또는 None(명령 없음)
    @return 검증 결과. 명령이 없으면 command=None, errors=()
    """
    if raw is None:
        return CommandResult(None, ())
    side, side_error = _read_enum(raw, "side", Side)
    action, action_error = _read_enum(raw, "action", Action)
    source, source_error = _read_enum(raw, "source", Source)
    errors = tuple(e for e in (side_error, action_error, source_error) if e)
    if errors:
        return CommandResult(None, errors)
    return CommandResult(DriverCommand(side, action, source), ())


def age_ms(snapshot: VehicleSnapshot) -> int:
    """입력의 경과시간을 밀리초 정수로 계산한다 (DEC-007).

    @param snapshot 검증된 스냅샷
    @return round((timestamp_s - source_timestamp_s) * 1000)
    """
    return round((snapshot.timestamp_s - snapshot.source_timestamp_s) * 1000)


def is_stale(snapshot: VehicleSnapshot) -> bool:
    """입력이 200 ms를 초과해 갱신되지 않았는지 판단한다 (SWR-013).

    @param snapshot 검증된 스냅샷
    @return 경과시간이 STALE_MS를 초과하면 True
    """
    return age_ms(snapshot) > STALE_MS
