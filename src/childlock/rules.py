"""개별 판단 규칙 (SWR-001~009, 017, 018, 020, 021).

@file rules.py
@brief 각 규칙은 "이 조건이 출력을 정하는가"를 반환한다. 정하지 않으면 None이다.
"""
from childlock.models import (
    AUTO_LOCK_KPH,
    OVERRIDE_WINDOW_MS,
    Action,
    CrashStatus,
    DriverCommand,
    LockOutput,
    Memory,
    ReasonCode,
    Side,
    SideMemory,
    SideVerdict,
    State,
    VehicleSnapshot,
    Verdict,
)

LOCK = LockOutput.LOCK
RELEASE = LockOutput.RELEASE


def _targets(cmd: DriverCommand | None, side: Side) -> bool:
    """명령이 해당 측을 대상으로 하는지 판단한다.

    @param cmd 운전자 명령 또는 None
    @param side Side.LEFT 또는 Side.RIGHT
    @return 명령의 대상이 해당 측이거나 전체이면 True
    """
    return cmd is not None and cmd.side in (side, Side.ALL)


def _wants(cmd: DriverCommand | None, side: Side, action: Action) -> bool:
    """명령이 해당 측에 특정 동작을 요구하는지 판단한다.

    @param cmd 운전자 명령 또는 None
    @param side Side.LEFT 또는 Side.RIGHT
    @param action 확인할 동작
    @return 해당 측을 대상으로 하고 동작이 일치하면 True
    """
    return _targets(cmd, side) and cmd.action is action


def rule_crash_confirmed(snap: VehicleSnapshot) -> Verdict | None:
    """충돌이 확정되면 좌·우를 해제한다 (SWR-007).

    @param snap 검증된 스냅샷
    @return 해제 결정 또는 None
    """
    if snap.crash_status is CrashStatus.CONFIRMED:
        return Verdict(RELEASE, RELEASE, ReasonCode.CRASH_CONFIRMED, None)
    return None


def rule_emergency(snap: VehicleSnapshot) -> Verdict | None:
    """화재, 과온, 성인 존재 중 하나라도 TRUE이면 좌·우를 해제한다 (SWR-017).

    @param snap 검증된 스냅샷
    @return 해제 결정(이유코드는 화재, 과온, 성인 순) 또는 None
    """
    checks = (
        (snap.fire_detected, ReasonCode.FIRE),
        (snap.overtemperature_detected, ReasonCode.OVERTEMPERATURE),
        (snap.adult_present, ReasonCode.ADULT_PRESENT),
    )
    for active, reason in checks:
        if active:
            return Verdict(RELEASE, RELEASE, reason, None)
    return None


def rule_sensor_fault(snap: VehicleSnapshot, mem: Memory) -> Verdict | None:
    """센서 고장이면 직전 출력을 유지하고 FAULT 상태가 된다 (SWR-021).

    @param snap 검증된 스냅샷
    @param mem 직전 주기의 기억
    @return 유지 결정 또는 None
    """
    if snap.sensor_fault:
        return Verdict(mem.left.last, mem.right.last, ReasonCode.SENSOR_FAULT, State.FAULT)
    return None


def rule_crash_pending(snap: VehicleSnapshot, mem: Memory) -> Verdict | None:
    """충돌이 미확정이면 출력을 바꾸지 않는다 (SWR-008).

    @param snap 검증된 스냅샷
    @param mem 직전 주기의 기억
    @return 유지 결정 또는 None
    """
    if snap.crash_status is CrashStatus.PENDING:
        return Verdict(mem.left.last, mem.right.last, ReasonCode.CRASH_PENDING, None)
    return None


def _approach_risk(snap: VehicleSnapshot, side: Side) -> bool:
    """해당 측 후측방 접근위험 입력을 반환한다.

    @param snap 검증된 스냅샷
    @param side Side.LEFT 또는 Side.RIGHT
    @return 접근위험 TRUE 여부
    """
    return snap.rear_left_approach_risk if side is Side.LEFT else snap.rear_right_approach_risk


def _risk_reason(side: Side) -> ReasonCode:
    """접근위험 이유코드를 측에 맞게 고른다.

    @param side Side.LEFT 또는 Side.RIGHT
    @return 해당 측 이유코드
    """
    return ReasonCode.APPROACH_RISK_LEFT if side is Side.LEFT else ReasonCode.APPROACH_RISK_RIGHT


def _approach_while_override(cmd: DriverCommand | None, side: Side, mem: SideMemory) -> SideVerdict:
    """override 중의 판단. lock 명령이 오면 override를 끝내고 잠근다 (DD-004).

    @param cmd 운전자 명령 또는 None
    @param side Side.LEFT 또는 Side.RIGHT
    @param mem 해당 측의 기억
    @return 측 결정
    """
    if _wants(cmd, side, Action.LOCK):
        return SideVerdict(LOCK, ReasonCode.DRIVER_COMMAND)
    return SideVerdict(RELEASE, ReasonCode.APPROACH_OVERRIDE, True, mem.suppressed_since_ms, True)


def _approach_on_release_request(side: Side, mem: SideMemory, now_ms: int) -> SideVerdict:
    """접근위험 중 해제 요청의 판단. 10초 이하 재입력이면 override이다 (SWR-006).

    @param side Side.LEFT 또는 Side.RIGHT
    @param mem 해당 측의 기억
    @param now_ms 현재 시각(밀리초)
    @return 측 결정
    """
    since = mem.suppressed_since_ms
    if since is not None and now_ms - since <= OVERRIDE_WINDOW_MS:
        return SideVerdict(RELEASE, ReasonCode.APPROACH_OVERRIDE, True, since, True)
    return SideVerdict(LOCK, _risk_reason(side), False, now_ms, False)


def rule_approach_risk(
    side: Side, snap: VehicleSnapshot, cmd: DriverCommand | None, mem: SideMemory, now_ms: int
) -> SideVerdict | None:
    """접근위험 측을 잠그고 해제 요청을 억제한다 (SWR-005, 006, 009).

    @param side Side.LEFT 또는 Side.RIGHT
    @param snap 검증된 스냅샷
    @param cmd 운전자 명령 또는 None
    @param mem 해당 측의 기억(접근위험이 없는 주기에는 이미 지워져 있다)
    @param now_ms 현재 시각(밀리초)
    @return 측 결정 또는 None(접근위험 없음)
    """
    if not _approach_risk(snap, side):
        return None
    if mem.override_active:
        return _approach_while_override(cmd, side, mem)
    if _wants(cmd, side, Action.UNLOCK):
        return _approach_on_release_request(side, mem, now_ms)
    return SideVerdict(LOCK, _risk_reason(side), False, mem.suppressed_since_ms, False)


def rule_isofix(side: Side, snap: VehicleSnapshot) -> SideVerdict | None:
    """ISOFIX가 연결된 측을 강제로 잠근다 (SWR-018).

    @param side Side.LEFT 또는 Side.RIGHT
    @param snap 검증된 스냅샷
    @return 잠금 결정 또는 None
    """
    if side is Side.LEFT and snap.isofix_left:
        return SideVerdict(LOCK, ReasonCode.ISOFIX_LEFT)
    if side is Side.RIGHT and snap.isofix_right:
        return SideVerdict(LOCK, ReasonCode.ISOFIX_RIGHT)
    return None


def rule_ignition_off(snap: VehicleSnapshot) -> SideVerdict | None:
    """시동이 꺼지면 출력을 초기 해제 상태로 한다 (SWR-020).

    @param snap 검증된 스냅샷
    @return 해제 결정 또는 None
    """
    if not snap.ignition_on:
        return SideVerdict(RELEASE, ReasonCode.IGNITION_OFF)
    return None


def rule_auto_lock(
    side: Side, snap: VehicleSnapshot, cmd: DriverCommand | None
) -> SideVerdict | None:
    """차속이 3.0 km/h 이상이면 잠그고 해제 명령은 거절한다 (SWR-003, 004).

    @param side Side.LEFT 또는 Side.RIGHT
    @param snap 검증된 스냅샷
    @param cmd 운전자 명령 또는 None
    @return 잠금 결정 또는 None
    """
    if snap.vehicle_speed_kph < AUTO_LOCK_KPH:
        return None
    if _wants(cmd, side, Action.UNLOCK):
        return SideVerdict(LOCK, ReasonCode.RELEASE_DENIED_MOVING)
    return SideVerdict(LOCK, ReasonCode.AUTO_LOCK_SPEED)


def rule_driver_command(side: Side, cmd: DriverCommand | None) -> SideVerdict | None:
    """운전자 명령을 선택된 측에만 적용한다 (SWR-001, 002).

    @param side Side.LEFT 또는 Side.RIGHT
    @param cmd 운전자 명령 또는 None
    @return 명령 결정 또는 None
    """
    if not _targets(cmd, side):
        return None
    output = LOCK if cmd.action is Action.LOCK else RELEASE
    return SideVerdict(output, ReasonCode.DRIVER_COMMAND)
