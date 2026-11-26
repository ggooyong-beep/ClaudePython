"""결정론 시험: 같은 입력 순서와 초기 상태는 같은 결과를 낸다 (SWR-016)."""
import hashlib

import pytest

from childlock.controller import Controller
from tests.childlock.factories import raw_snapshot

pytestmark = [
    pytest.mark.swr("SWR-016"),
]

UNLOCK_LEFT = {"side": "left", "action": "unlock", "source": "voice"}
LOCK_ALL = {"side": "all", "action": "lock", "source": "avn"}

VECTOR = [
    (raw_snapshot(timestamp_s=1.00), LOCK_ALL),
    (raw_snapshot(timestamp_s=1.05, rear_left_approach_risk=True), UNLOCK_LEFT),
    (raw_snapshot(timestamp_s=1.10, rear_left_approach_risk=True), UNLOCK_LEFT),
    (raw_snapshot(timestamp_s=1.15, vehicle_speed_kph=12.5), None),
    (raw_snapshot(timestamp_s=1.20, vehicle_speed_kph=999.0), None),
    (raw_snapshot(timestamp_s=1.25, crash_status="PENDING"), None),
    (raw_snapshot(timestamp_s=1.30, crash_status="CONFIRMED"), None),
    (raw_snapshot(timestamp_s=1.35, source_timestamp_s=1.0), None),
]


def _replay_hash() -> str:
    ctl = Controller()
    digest = hashlib.sha256()
    for raw, command in VECTOR:
        digest.update(repr(ctl.step(raw, command)).encode("utf-8"))
    digest.update(repr(ctl.events()).encode("utf-8"))
    return digest.hexdigest()


def test_replaying_the_same_vector_1000_times_gives_one_hash():
    assert len({_replay_hash() for _ in range(1000)}) == 1


def test_a_different_vector_gives_a_different_hash():
    other = Controller()
    digest = hashlib.sha256()
    for raw, command in VECTOR[:-1]:
        digest.update(repr(other.step(raw, command)).encode("utf-8"))
    digest.update(repr(other.events()).encode("utf-8"))
    assert digest.hexdigest() != _replay_hash()
