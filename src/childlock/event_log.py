"""결정 이벤트 로그 (SWR-010, 011, 012).

@file event_log.py
@brief 최근 100건만 메모리에 보관한다. 파일과 DB에는 쓰지 않아 재기동 후 남지 않는다.
"""
from collections import deque
from dataclasses import dataclass

from childlock.models import LOG_CAPACITY, Decision, LockOutput, ReasonCode, State


@dataclass(frozen=True, slots=True)
class Event:
    """이벤트 레코드. 허용 필드 8개만 가진다 (SWR-011)."""

    event_id: int
    timestamp_s: float
    state: State
    lock_left: LockOutput
    lock_right: LockOutput
    reason_code: ReasonCode
    priority_reason: ReasonCode
    input_validity: dict[str, str]


class EventLog:
    """고정 용량 링 버퍼 이벤트 로그."""

    def __init__(self) -> None:
        """빈 로그를 만든다. 이벤트 ID 카운터는 1에서 시작한다."""
        self._events: deque[Event] = deque(maxlen=LOG_CAPACITY)
        self._next_id = 1

    def append(self, decision: Decision, timestamp_s: float) -> Event:
        """결정을 기록한다. 고유하고 단조 증가하는 이벤트 ID를 부여한다 (SWR-010).

        @param decision 기록할 결정
        @param timestamp_s 결정 시각(초)
        @return 저장된 이벤트
        """
        event = Event(
            self._next_id,
            timestamp_s,
            decision.state,
            decision.lock_left,
            decision.lock_right,
            decision.reason_code,
            decision.priority_reason,
            dict(decision.input_validity),
        )
        self._next_id += 1
        self._events.append(event)
        return event

    def events(self) -> list[Event]:
        """보관 중인 이벤트를 오래된 것부터 반환한다 (SWR-012).

        @return 최대 100건의 이벤트 사본 목록
        """
        return list(self._events)
