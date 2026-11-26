"""우선순위 중재 (SWR-022).

@file arbiter.py
@brief 규칙을 우선순위표 순서로 평가해 한 주기의 결정과 새 기억을 만든다.

순위: 0 stale > 1 충돌 확정 > 2 비상 > 3 센서 고장 > 3.5 충돌 미확정
> 4 접근위험 > 5 ISOFIX > 6 시동 OFF > 7 자동 잠금 > 8 운전자 명령
"""
from collections.abc import Mapping
from dataclasses import replace

from childlock.models import (
    Decision,
    DriverCommand,
    Memory,
    ReasonCode,
    Side,
    SideMemory,
    SideVerdict,
    State,
    VehicleSnapshot,
    Verdict,
)
from childlock.rules import (
    approach_risk,
    rule_approach_risk,
    rule_auto_lock,
    rule_crash_confirmed,
    rule_crash_pending,
    rule_driver_command,
    rule_emergency,
    rule_ignition_off,
    rule_isofix,
    rule_sensor_fault,
)
from childlock.validator import is_stale

STALE = "STALE"
_RANK = {reason: index for index, reason in enumerate(ReasonCode)}


def _base_state(snap: VehicleSnapshot) -> State:
    """전역 규칙이 상태를 정하지 않았을 때의 기본 상태를 고른다.

    @param snap 검증된 스냅샷
    @return 시동이 꺼져 있으면 OFF, 아니면 NORMAL
    """
    return State.NORMAL if snap.ignition_on else State.OFF


def _pick_priority_reason(left: ReasonCode, right: ReasonCode) -> ReasonCode:
    """두 측의 이유코드 중 우선순위가 높은 것을 고른다. 같으면 좌측이다.

    @param left 좌측 이유코드
    @param right 우측 이유코드
    @return 우선순위가 높은 이유코드
    """
    return min(left, right, key=_RANK.__getitem__)


def _decide_global(snap: VehicleSnapshot, mem: Memory) -> Verdict | None:
    """순위 1, 2, 3, 3.5의 전역 규칙을 순서대로 적용한다.

    @param snap 검증된 스냅샷
    @param mem 직전 주기의 기억
    @return 첫 번째로 성립한 전역 결정 또는 None
    """
    return (
        rule_crash_confirmed(snap)
        or rule_emergency(snap)
        or rule_sensor_fault(snap, mem)
        or rule_crash_pending(snap, mem)
    )


def _decide_side(
    side: Side, snap: VehicleSnapshot, cmd: DriverCommand | None, mem: Memory, now_ms: int
) -> SideVerdict:
    """순위 4~8의 측별 규칙을 순서대로 적용한다.

    접근위험이 없는 측은 억제 시각과 override 기억을 지운 뒤 평가한다.

    @param side Side.LEFT 또는 Side.RIGHT
    @param snap 검증된 스냅샷
    @param cmd 운전자 명령 또는 None
    @param mem 직전 주기의 기억
    @param now_ms 현재 시각(밀리초)
    @return 해당 측의 결정. 어떤 규칙도 정하지 않으면 직전 출력을 유지한다.
    """
    remembered = mem.side(side)
    if not approach_risk(snap, side):
        remembered = replace(remembered, suppressed_since_ms=None, override_active=False)
    verdict = (
        rule_approach_risk(side, snap, cmd, remembered, now_ms)
        or rule_isofix(side, snap)
        or rule_ignition_off(snap)
        or rule_auto_lock(side, snap, cmd)
        or rule_driver_command(side, cmd)
    )
    return verdict or SideVerdict(remembered.last, ReasonCode.NO_CHANGE)


def _from_global(
    snap: VehicleSnapshot, verdict: Verdict, mem: Memory, validity: Mapping[str, str]
) -> tuple[Decision, Memory]:
    """전역 규칙의 결과로 결정과 새 기억을 만든다.

    @param snap 검증된 스냅샷
    @param verdict 성립한 전역 결정
    @param mem 직전 주기의 기억
    @param validity 입력 그룹별 유효성
    @return (결정, 새 기억). 접근위험 기억은 그대로 두고 직전 출력만 갱신한다.
    """
    state = verdict.state or _base_state(snap)
    decision = Decision(verdict.left, verdict.right, state, verdict.reason, dict(validity))
    new_mem = Memory(
        replace(mem.left, last=verdict.left), replace(mem.right, last=verdict.right)
    )
    return decision, new_mem


def _from_sides(
    snap: VehicleSnapshot, cmd: DriverCommand | None, mem: Memory, validity: Mapping[str, str]
) -> tuple[Decision, Memory]:
    """좌·우를 각각 평가해 결정과 새 기억을 만든다.

    @param snap 검증된 스냅샷
    @param cmd 운전자 명령 또는 None
    @param mem 직전 주기의 기억
    @param validity 입력 그룹별 유효성
    @return (결정, 새 기억)
    """
    now_ms = round(snap.timestamp_s * 1000)
    left = _decide_side(Side.LEFT, snap, cmd, mem, now_ms)
    right = _decide_side(Side.RIGHT, snap, cmd, mem, now_ms)
    decision = Decision(
        left.output,
        right.output,
        _base_state(snap),
        _pick_priority_reason(left.reason, right.reason),
        dict(validity),
        left.override or right.override,
    )
    new_mem = Memory(
        SideMemory(left.output, left.suppressed_since_ms, left.override_active),
        SideMemory(right.output, right.suppressed_since_ms, right.override_active),
    )
    return decision, new_mem


def decide(
    snap: VehicleSnapshot,
    cmd: DriverCommand | None,
    mem: Memory,
    validity: Mapping[str, str],
) -> tuple[Decision, Memory]:
    """한 평가주기의 결정을 만든다. 시계와 외부 상태를 쓰지 않는 순수 함수다 (SWR-016, 022).

    @param snap 검증된 스냅샷
    @param cmd 운전자 명령 또는 None
    @param mem 직전 주기의 기억
    @param validity 입력 그룹별 유효성
    @return (결정, 새 기억)
    """
    if is_stale(snap):
        stale = {group: STALE for group in validity}
        decision = Decision(
            mem.left.last, mem.right.last, State.DEGRADED, ReasonCode.INPUT_STALE, stale
        )
        return decision, mem
    verdict = _decide_global(snap, mem)
    if verdict is not None:
        return _from_global(snap, verdict, mem, validity)
    return _from_sides(snap, cmd, mem, validity)
