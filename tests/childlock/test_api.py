"""Web API 시험 (SWR-014, 015)."""
import pytest
from fastapi.testclient import TestClient

from childlock.web.api import create_app
from tests.childlock.factories import raw_snapshot

pytestmark = [
    pytest.mark.swr("SWR-014"),
]

LOCK_ALL = {"side": "all", "action": "lock", "source": "mobile_app"}
EVENT_FIELDS = {
    "event_id",
    "timestamp_s",
    "state",
    "lock_left",
    "lock_right",
    "reason_code",
    "priority_reason",
    "input_validity",
}


@pytest.fixture
def client():
    return TestClient(create_app(now_s=lambda: 50.0))


def test_evaluate_returns_decision_with_outputs_and_reason(client):
    response = client.post("/evaluate", json={"snapshot": raw_snapshot(), "command": LOCK_ALL})
    assert response.status_code == 200
    body = response.json()
    assert (body["lock_left"], body["lock_right"]) == ("LOCK", "LOCK")
    assert body["state"] == "NORMAL"
    assert body["reason_code"] == "DRIVER_COMMAND"


def test_evaluate_fills_missing_evaluation_time_from_injected_clock(client):
    snapshot = raw_snapshot(source_timestamp_s=49.9)
    del snapshot["timestamp_s"]
    response = client.post("/evaluate", json={"snapshot": snapshot})
    assert response.status_code == 200
    assert client.get("/events").json()[0]["timestamp_s"] == 50.0


def test_missing_source_timestamp_is_rejected_not_filled_in(client):
    snapshot = raw_snapshot()
    del snapshot["source_timestamp_s"]
    response = client.post("/evaluate", json={"snapshot": snapshot})
    assert response.status_code == 422
    assert "source_timestamp_s" in response.json()["errors"][0]
    assert client.get("/status").json()["reason_code"] == "INPUT_INVALID"


def test_invalid_input_returns_422_with_errors_and_no_decision_change(client):
    response = client.post("/evaluate", json={"snapshot": raw_snapshot(gear="X")})
    assert response.status_code == 422
    assert "gear" in response.json()["errors"][0]
    status = client.get("/status").json()
    assert status["reason_code"] == "INPUT_INVALID"
    assert status["input_validity"]["gear"] == "INVALID"


def test_request_without_snapshot_is_rejected(client):
    assert client.post("/evaluate", json={"command": LOCK_ALL}).status_code == 422


def test_status_has_all_fields_and_reason_code_equals_priority_reason(client):
    client.post("/evaluate", json={"snapshot": raw_snapshot(fire_detected=True)})
    body = client.get("/status").json()
    assert set(body) == {
        "lock_left",
        "lock_right",
        "state",
        "input_validity",
        "reason_code",
        "priority_reason",
        "override",
    }
    assert body["reason_code"] == body["priority_reason"] == "FIRE"
    assert body["input_validity"]["emergency"] == "VALID"


def test_status_before_any_input_is_initial(client):
    body = client.get("/status").json()
    assert (body["lock_left"], body["lock_right"], body["state"]) == ("RELEASE", "RELEASE", "OFF")


def test_events_list_only_allowed_fields_in_order(client):
    for index in range(3):
        snapshot = raw_snapshot(timestamp_s=50.0 + index * 0.05)
        client.post("/evaluate", json={"snapshot": snapshot})
    events = client.get("/events").json()
    assert [e["event_id"] for e in events] == [1, 2, 3]
    assert all(set(e) == EVENT_FIELDS for e in events)


def test_tick_makes_stale_input_degraded(client):
    client.post("/evaluate", json={"snapshot": raw_snapshot(timestamp_s=100.0)})
    response = client.post("/tick", json={"timestamp_s": 100.201})
    assert response.status_code == 200
    assert response.json()["state"] == "DEGRADED"


def test_tick_before_any_input_is_rejected(client):
    response = client.post("/tick", json={"timestamp_s": 1.0})
    assert response.status_code == 422
    assert response.json()["errors"] == ["입력이 아직 없습니다"]


def test_index_page_is_served_as_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def _failing_serializer(_):
    raise ValueError("직렬화 실패")


@pytest.mark.parametrize("path", ["/status", "/events"])
def test_serialization_failure_returns_http_500(path):
    failing = TestClient(create_app(serializer=_failing_serializer), raise_server_exceptions=False)
    failing.post("/evaluate", json={"snapshot": raw_snapshot()})
    assert failing.get(path).status_code == 500


def test_serialization_failure_on_evaluate_returns_http_500():
    failing = TestClient(create_app(serializer=_failing_serializer), raise_server_exceptions=False)
    assert failing.post("/evaluate", json={"snapshot": raw_snapshot()}).status_code == 500
