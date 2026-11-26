"""평가주기 오케스트레이션 (SWR-013, 016, 023).

@file controller.py
@brief 입력 검증, 판단, 기억 갱신, 이벤트 기록을 연결한다.
"""
from collections.abc import Mapping
from dataclasses import dataclass, replace

from childlock.arbiter import decide
from childlock.event_log import Event, EventLog
from childlock.models import (
    Decision,
    LockOutput,
    Memory,
    ReasonCode,
    State,
    VehicleSnapshot,
)
from childlock.validator import INVALID, VALID, parse_command, parse_snapshot

NO_INPUT_ERROR = "입력이 아직 없습니다"


@dataclass(frozen=True, slots=True)
class StepResult:
    """한 주기의 처리 결과. 입력이 거절되면 accepted는 False이다."""

    decision: Decision
    accepted: bool
    errors: tuple[str, ...]


class Controller:
    """판단 함수 decide()를 주기마다 호출하고 기억과 이벤트 로그를 관리한다."""

    def __init__(self) -> None:
        """초기 상태(좌·우 RELEASE, OFF)로 시작한다."""
        self._memory = Memory()
        self._log = EventLog()
        self._last_snapshot: VehicleSnapshot | None = None
        self._last_validity: dict[str, str] = {}
        self._last_timestamp_s = 0.0
        self._last_decision = Decision(
            LockOutput.RELEASE, LockOutput.RELEASE, State.OFF, ReasonCode.NO_CHANGE, {}
        )

    def status(self) -> Decision:
        """가장 최근의 결정을 반환한다 (SWR-014).

        @return 마지막 결정. 아직 입력이 없으면 초기 결정
        """
        return self._last_decision

    def events(self) -> list[Event]:
        """최근 이벤트를 오래된 것부터 반환한다 (SWR-012).

        @return 최대 100건의 이벤트
        """
        return self._log.events()

    def _commit(self, decision: Decision, memory: Memory, timestamp_s: float) -> None:
        """결정을 확정하고 기억과 이벤트 로그를 갱신한다.

        @param decision 확정할 결정
        @param memory 다음 주기로 넘길 기억
        @param timestamp_s 결정 시각(초)
        """
        self._memory = memory
        self._last_decision = decision
        self._last_timestamp_s = timestamp_s
        self._log.append(decision, timestamp_s)

    def _reject(self, validity: Mapping[str, str], errors: tuple[str, ...]) -> StepResult:
        """거절된 입력을 INPUT_INVALID로 기록한다. 출력과 기억은 바꾸지 않는다 (SWR-013).

        @param validity 입력 그룹별 유효성
        @param errors 오류 메시지 목록
        @return accepted=False 결과
        """
        decision = Decision(
            self._memory.left.last,
            self._memory.right.last,
            self._last_decision.state,
            ReasonCode.INPUT_INVALID,
            dict(validity),
        )
        self._commit(decision, self._memory, self._last_timestamp_s)
        return StepResult(decision, False, errors)

    def step(
        self, raw_snapshot: Mapping[str, object], raw_command: Mapping[str, object] | None = None
    ) -> StepResult:
        """새 입력으로 한 평가주기를 처리한다 (SWR-013, 023).

        @param raw_snapshot 차량 입력 원시 값
        @param raw_command 운전자 명령 원시 값 또는 None
        @return 처리 결과. 입력 오류가 있으면 평가하지 않고 거절한다.
        """
        parsed = parse_snapshot(raw_snapshot)
        command = parse_command(raw_command)
        validity = {**parsed.validity, "command": INVALID if command.errors else VALID}
        errors = parsed.errors + command.errors
        if errors:
            return self._reject(validity, errors)
        decision, memory = decide(parsed.snapshot, command.command, self._memory, validity)
        self._last_snapshot = parsed.snapshot
        self._last_validity = validity
        self._commit(decision, memory, parsed.snapshot.timestamp_s)
        return StepResult(decision, True, ())

    def tick(self, timestamp_s: float) -> StepResult:
        """새 입력 없이 시간만 흐른 주기를 처리한다. 입력이 낡으면 DEGRADED가 된다 (SWR-013).

        @param timestamp_s 현재 시각(초)
        @return 처리 결과. 입력이 한 번도 없었으면 accepted=False이고 기록하지 않는다.
        """
        if self._last_snapshot is None:
            return StepResult(self._last_decision, False, (NO_INPUT_ERROR,))
        snapshot = replace(self._last_snapshot, timestamp_s=timestamp_s)
        decision, memory = decide(snapshot, None, self._memory, self._last_validity)
        self._commit(decision, memory, timestamp_s)
        return StepResult(decision, True, ())
