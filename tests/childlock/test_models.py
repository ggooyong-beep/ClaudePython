"""모델의 동작이 있는 부분 시험: 측별 기억 조회, reason_code 매핑 (OEM-IF-006)."""
from childlock.models import (
    Decision,
    LockOutput,
    Memory,
    ReasonCode,
    Side,
    SideMemory,
    State,
)


def test_memory_returns_the_remembered_side():
    mem = Memory(SideMemory(last=LockOutput.LOCK), SideMemory(suppressed_since_ms=7))
    assert mem.side(Side.LEFT).last is LockOutput.LOCK
    assert mem.side(Side.RIGHT).suppressed_since_ms == 7


def test_initial_memory_is_released_without_suppression():
    mem = Memory()
    assert mem.left == mem.right == SideMemory(LockOutput.RELEASE, None, False)


def test_reason_code_mirrors_priority_reason():
    decision = Decision(
        LockOutput.LOCK, LockOutput.RELEASE, State.NORMAL, ReasonCode.FIRE, {"speed": "VALID"}
    )
    assert decision.reason_code is ReasonCode.FIRE
