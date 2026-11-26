"""도메인 모델: 열거형, 상수, 불변 데이터 클래스.

@file models.py
@brief 판단 코어가 공유하는 데이터 정의 (상세 설계 1~2절).
"""
from dataclasses import dataclass
from enum import Enum

CYCLE_MS = 50  # 평가주기 (SWR-023)
STALE_MS = 200  # 입력 갱신 지연 한계, 초과 시 stale (SWR-013)
AUTO_LOCK_KPH = 3.0  # 이 속도 이상이면 자동 잠금 (SWR-003)
OVERRIDE_WINDOW_MS = 10_000  # 접근위험 override 허용 시간 (SWR-006)
LOG_CAPACITY = 100  # 보존할 이벤트 수 (SWR-012)
SPEED_MIN_KPH = 0.0
SPEED_MAX_KPH = 300.0


class LockOutput(Enum):
    """도어 잠금 논리 출력."""

    LOCK = "LOCK"
    RELEASE = "RELEASE"


class CrashStatus(Enum):
    """충돌 상태 (OEM-IF-002)."""

    NONE = "NONE"
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"


class Gear(Enum):
    """기어 단 (OEM-IF-001)."""

    P = "P"
    N = "N"
    D = "D"
    R = "R"


class Side(Enum):
    """운전자 명령 대상 (OEM-IF-004)."""

    LEFT = "left"
    RIGHT = "right"
    ALL = "all"


class Action(Enum):
    """운전자 명령 동작 (OEM-IF-004)."""

    LOCK = "lock"
    UNLOCK = "unlock"


class Source(Enum):
    """운전자 명령 경로 (OEM-IF-004)."""

    PHYSICAL_BUTTON = "physical_button"
    AVN = "avn"
    VOICE = "voice"
    MOBILE_APP = "mobile_app"


class State(Enum):
    """제어 상태 (아키텍처 5절)."""

    OFF = "OFF"
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    FAULT = "FAULT"


class ReasonCode(Enum):
    """결정 사유 코드 (아키텍처 7절). 선언 순서가 우선순위(앞이 높음)이다."""

    INPUT_INVALID = "INPUT_INVALID"
    INPUT_STALE = "INPUT_STALE"
    CRASH_CONFIRMED = "CRASH_CONFIRMED"
    FIRE = "FIRE"
    OVERTEMPERATURE = "OVERTEMPERATURE"
    ADULT_PRESENT = "ADULT_PRESENT"
    SENSOR_FAULT = "SENSOR_FAULT"
    CRASH_PENDING = "CRASH_PENDING"
    APPROACH_RISK_LEFT = "APPROACH_RISK_LEFT"
    APPROACH_RISK_RIGHT = "APPROACH_RISK_RIGHT"
    APPROACH_OVERRIDE = "APPROACH_OVERRIDE"
    ISOFIX_LEFT = "ISOFIX_LEFT"
    ISOFIX_RIGHT = "ISOFIX_RIGHT"
    IGNITION_OFF = "ignition_off"
    AUTO_LOCK_SPEED = "AUTO_LOCK_SPEED"
    RELEASE_DENIED_MOVING = "RELEASE_DENIED_MOVING"
    DRIVER_COMMAND = "DRIVER_COMMAND"
    NO_CHANGE = "NO_CHANGE"


@dataclass(frozen=True, slots=True)
class VehicleSnapshot:
    """차량 입력 한 주기분 (OEM-IF-001~003, 007~009)."""

    timestamp_s: float
    source_timestamp_s: float
    vehicle_speed_kph: float
    gear: Gear
    crash_status: CrashStatus
    rear_left_approach_risk: bool
    rear_right_approach_risk: bool
    fire_detected: bool
    overtemperature_detected: bool
    adult_present: bool
    isofix_left: bool
    isofix_right: bool
    ignition_on: bool
    sensor_fault: bool


@dataclass(frozen=True, slots=True)
class DriverCommand:
    """운전자 명령 (OEM-IF-004)."""

    side: Side
    action: Action
    source: Source
