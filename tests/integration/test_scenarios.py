"""통합 시험: HTTP API부터 컨트롤러, 이벤트 로그까지 평가주기 단위로 검증한다.

단위 시험이 함수 하나를 본다면, 여기서는 여러 주기에 걸친 사용 시나리오를 본다.
"""
import pytest
from fastapi.testclient import TestClient

from childlock.web.api import create_app
from tests.childlock.factories import raw_snapshot

pytestmark = [
    pytest.mark.swr("SWR-001"),
    pytest.mark.swr("SWR-002"),
    pytest.mark.swr("SWR-006"),
    pytest.mark.swr("SWR-007"),
    pytest.mark.swr("SWR-012"),
    pytest.mark.swr("SWR-013"),
    pytest.mark.swr("SWR-014"),
]

CYCLE_S = 0.05
SOURCES = ["physical_button", "avn", "voice", "mobile_app"]


@pytest.fixture
def client():
    return TestClient(create_app(now_s=lambda: 0.0))


def _cycle(client, index, command=None, **overrides):
    """index번째 평가주기(50 ms 간격)를 보내고 응답을 돌려준다."""
    snapshot = raw_snapshot(timestamp_s=1.0 + index * CYCLE_S, **overrides)
    return client.post("/evaluate", json={"snapshot": snapshot, "command": command})


def _outputs(response):
    body = response.json()
    return body["lock_left"], body["lock_right"]


@pytest.mark.parametrize("source", SOURCES)
def test_each_command_source_locks_then_releases_when_stopped(client, source):
    lock = {"side": "all", "action": "lock", "source": source}
    unlock = {"side": "all", "action": "unlock", "source": source}
    assert _outputs(_cycle(client, 0, lock)) == ("LOCK", "LOCK")
    assert _outputs(_cycle(client, 1, unlock)) == ("RELEASE", "RELEASE")


@pytest.mark.parametrize(
    ("side", "expected"),
    [("left", ("LOCK", "RELEASE")), ("right", ("RELEASE", "LOCK")), ("all", ("LOCK", "LOCK"))],
)
def test_command_side_changes_only_selected_outputs(client, side, expected):
    response = _cycle(client, 0, {"side": side, "action": "lock", "source": "avn"})
    assert _outputs(response) == expected


def test_crash_confirmed_releases_in_the_next_cycle_and_survives_later_cycles(client):
    _cycle(client, 0, {"side": "all", "action": "lock", "source": "avn"})
    assert _outputs(_cycle(client, 1, crash_status="CONFIRMED")) == ("RELEASE", "RELEASE")
    assert _outputs(_cycle(client, 2, crash_status="CONFIRMED")) == ("RELEASE", "RELEASE")
    assert _outputs(_cycle(client, 3, crash_status="NONE")) == ("RELEASE", "RELEASE")
    assert client.get("/events").json()[1]["reason_code"] == "CRASH_CONFIRMED"


def test_approach_risk_scenario_suppress_then_override_then_clear(client):
    risky = {"rear_left_approach_risk": True}
    unlock = {"side": "left", "action": "unlock", "source": "voice"}
    _cycle(client, 0, {"side": "all", "action": "lock", "source": "avn"})
    first = _cycle(client, 1, unlock, **risky).json()
    assert (first["lock_left"], first["reason_code"]) == ("LOCK", "APPROACH_RISK_LEFT")
    second = _cycle(client, 2, unlock, **risky).json()
    assert (second["lock_left"], second["reason_code"]) == ("RELEASE", "APPROACH_OVERRIDE")
    assert second["override"] is True
    assert client.get("/status").json()["lock_right"] == "LOCK"
    cleared = _cycle(client, 3).json()
    assert cleared["override"] is False


def test_invalid_input_in_the_middle_changes_nothing_and_is_visible_in_status(client):
    _cycle(client, 0, {"side": "all", "action": "lock", "source": "avn"})
    bad = _cycle(client, 1, vehicle_speed_kph=-5.0, crash_status="CONFIRMED")
    assert bad.status_code == 422
    status = client.get("/status").json()
    assert (status["lock_left"], status["lock_right"]) == ("LOCK", "LOCK")
    assert status["reason_code"] == "INPUT_INVALID"
    assert _outputs(_cycle(client, 2)) == ("LOCK", "LOCK")


def test_stale_input_degrades_through_tick_and_recovers_with_fresh_input(client):
    _cycle(client, 0, {"side": "all", "action": "lock", "source": "avn"})
    base = 1.0
    states = [
        client.post("/tick", json={"timestamp_s": base + n * CYCLE_S}).json()["state"]
        for n in range(1, 8)
    ]
    assert states[:4] == ["NORMAL"] * 4
    assert states[4:] == ["DEGRADED"] * 3
    assert client.get("/status").json()["lock_left"] == "LOCK"
    assert _cycle(client, 8).json()["state"] == "NORMAL"


def test_only_latest_100_decisions_are_listed_in_order(client):
    for index in range(101):
        _cycle(client, index)
    ids = [event["event_id"] for event in client.get("/events").json()]
    assert ids == list(range(2, 102))


def test_new_application_starts_without_previous_events():
    first = TestClient(create_app(now_s=lambda: 0.0))
    _cycle(first, 0)
    restarted = TestClient(create_app(now_s=lambda: 0.0))
    assert restarted.get("/events").json() == []
    assert restarted.get("/status").json()["state"] == "OFF"
