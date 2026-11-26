"""Web API (SWR-014, 015).

@file api.py
@brief 판단 코어를 HTTP로 노출한다. 코어는 이 모듈을 알지 못한다.
"""
import dataclasses
import time
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from childlock.controller import Controller, StepResult
from childlock.models import Decision

STATIC_DIR = Path(__file__).parent / "static"
Serializer = Callable[[Any], dict[str, Any]]


class EvaluateRequest(BaseModel):
    """POST /evaluate 요청. 시각이 없으면 주입된 시계로 채운다."""

    snapshot: dict[str, Any]
    command: dict[str, Any] | None = None


class TickRequest(BaseModel):
    """POST /tick 요청. 새 입력 없이 시간이 흐른 주기를 시험한다."""

    timestamp_s: float


def _plain(value: Any) -> Any:
    """열거형을 값으로, 딕셔너리를 복사본으로 바꾼다.

    @param value 변환할 값
    @return JSON으로 직렬화 가능한 값
    """
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return dict(value)
    return value


def serialize(item: Decision | Any) -> dict[str, Any]:
    """결정 또는 이벤트를 JSON 딕셔너리로 바꾼다. 결정에는 reason_code를 함께 담는다.

    @param item Decision 또는 Event
    @return 필드 이름을 키로 하는 딕셔너리
    """
    data = {f.name: _plain(getattr(item, f.name)) for f in dataclasses.fields(item)}
    if isinstance(item, Decision):
        data["reason_code"] = item.reason_code.value
    return data


def _with_clock(snapshot: dict[str, Any], now_s: Callable[[], float]) -> dict[str, Any]:
    """누락된 평가 시각(timestamp_s)만 주입된 시계로 채운다.

    source_timestamp_s는 입력이 생성된 시각이므로 채우지 않는다. 누락을 채우면
    낡은 입력 판정(SWR-013)과 OEM-IF-001의 '누락은 INVALID' 규칙이 무력화된다.

    @param snapshot 원시 스냅샷
    @param now_s 현재 시각(초)을 돌려주는 함수
    @return 평가 시각이 채워진 새 딕셔너리
    """
    merged = dict(snapshot)
    merged.setdefault("timestamp_s", now_s())
    return merged


def create_app(
    controller: Controller | None = None,
    now_s: Callable[[], float] = time.monotonic,
    serializer: Serializer = serialize,
) -> FastAPI:
    """Web 애플리케이션을 만든다.

    @param controller 사용할 컨트롤러. None이면 새로 만든다.
    @param now_s 현재 시각(초) 함수. 시험에서는 고정 시계를 주입한다.
    @param serializer 결정과 이벤트의 직렬화 함수. 시험에서는 실패 주입에 쓴다.
    @return FastAPI 애플리케이션
    """
    ctl = controller or Controller()
    app = FastAPI(title="전자식 차일드락 시뮬레이터")

    @app.exception_handler(Exception)
    async def _server_error(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"error": "내부 오류", "detail": str(exc)}, status_code=500)

    def respond(result: StepResult) -> JSONResponse:
        if result.accepted:
            return JSONResponse(serializer(result.decision))
        body = {"errors": list(result.errors), "decision": serializer(result.decision)}
        return JSONResponse(body, status_code=422)

    @app.post("/evaluate")
    def evaluate(request: EvaluateRequest) -> JSONResponse:
        return respond(ctl.step(_with_clock(request.snapshot, now_s), request.command))

    @app.post("/tick")
    def tick(request: TickRequest) -> JSONResponse:
        return respond(ctl.tick(request.timestamp_s))

    @app.get("/status")
    def status() -> JSONResponse:
        return JSONResponse(serializer(ctl.status()))

    @app.get("/events")
    def events() -> JSONResponse:
        return JSONResponse([serializer(event) for event in ctl.events()])

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
