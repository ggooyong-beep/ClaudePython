"""시스템 테스트 케이스 자동 실행기.

tc.json의 절차(POST /evaluate, POST /tick, GET /status)를 구현에 실행하고
`[n]` 기대값(HTTP 상태, lock_left, lock_right, state, reason_code, override)과 비교한다.
서버 재시작, 대량 반복, GET /events 같은 특수 절차가 있는 TC는 자동 실행 대상에서 제외한다.

사용: python docs/07_system_test/run_system_tests.py [--json 결과.json]
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from childlock.web.api import create_app  # noqa: E402

STEP = re.compile(r"^\d+\.\s*(POST /evaluate|POST /tick|GET /status)\b")
KEYS = ("lock_left", "lock_right", "state", "reason_code", "override")


def _json_at(text: str, start: int):
    """text의 start 위치에서 시작하는 JSON 객체를 읽는다."""
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj


def _base(precondition: str) -> dict:
    """사전조건 문장에서 BASE 스냅샷 JSON을 읽는다."""
    return _json_at(precondition, precondition.index("BASE=") + len("BASE="))


def parse_step(step: str, base: dict):
    """절차 한 줄을 (메서드, 경로, 본문)으로 바꾼다. 해석할 수 없으면 None."""
    match = STEP.match(step)
    if not match:
        return None
    request = match.group(1)
    method, path = request.split(" ")
    if request == "GET /status":
        return method, path, None
    if request == "POST /tick":
        return method, path, _json_at(step, step.index("{"))
    if "snapshot=" not in step:
        return None
    pos = step.index("snapshot=") + len("snapshot=")
    if step.startswith("BASE", pos):
        pos += 4
        overrides = {}
        if step.startswith("+", pos):
            overrides = _json_at(step, pos + 1)
            pos = step.index("}", pos) + 1
        snapshot = {**base, **overrides}
    else:
        snapshot = _json_at(step, pos)
    snapshot.setdefault("source_timestamp_s", snapshot.get("timestamp_s"))
    deleted = re.search(r"키 삭제:\s*([\w,\s]+)\)", step)
    if deleted:
        for key in re.split(r"[,\s]+", deleted.group(1).strip()):
            snapshot.pop(key, None)
    command = None
    if "command=" in step:
        cpos = step.index("command=") + len("command=")
        command = None if step.startswith("null", cpos) else _json_at(step, cpos)
    return method, path, {"snapshot": snapshot, "command": command}


def parse_expected(expected: str) -> dict[int, dict]:
    """기대값 문장에서 단계 번호별 판정 항목을 읽는다."""
    result: dict[int, dict] = {}
    for line in expected.split("\n"):
        match = re.match(r"\[(\d+)\]\s*(.*)", line)
        if not match:
            continue
        number, body = int(match.group(1)), match.group(2)
        items: dict = {}
        http = re.search(r"HTTP (\d{3})", body)
        if http:
            items["http"] = int(http.group(1))
        for key in KEYS:
            found = re.search(rf"\b{key}=(\w+)", body)
            if found:
                value = found.group(1)
                items[key] = {"true": True, "false": False}.get(value, value)
        result[number] = items
    return result


def run_case(case: dict, base: dict):
    """TC 하나를 실행한다. 반환: ("PASS"|"FAIL"|"SKIP", 설명)."""
    steps = case["steps"] if isinstance(case["steps"], list) else [case["steps"]]
    parsed = []
    for step in steps:
        try:
            item = parse_step(step, base)
        except (ValueError, KeyError):
            item = None
        if item is None:
            return "SKIP", "자동 실행 불가 절차"
        parsed.append(item)
    expected = parse_expected(case["expected"])
    client = TestClient(create_app(now_s=lambda: 0.0))
    problems = []
    for number, (method, path, body) in enumerate(parsed, start=1):
        response = client.get(path) if method == "GET" else client.post(path, json=body)
        want = expected.get(number, {})
        if "http" in want and response.status_code != want["http"]:
            problems.append(f"[{number}] HTTP {response.status_code} (기대 {want['http']})")
            continue
        data = response.json() if response.status_code == 200 else {}
        if response.status_code == 422:
            # 기대값의 상태 항목은 거절 직후 GET /status 값을 뜻한다
            data = client.get("/status").json()
        for key in KEYS:
            if key in want and data.get(key) != want[key]:
                problems.append(f"[{number}] {key}={data.get(key)!r} (기대 {want[key]!r})")
    return ("FAIL", "; ".join(problems)) if problems else ("PASS", "")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", help="결과를 저장할 JSON 경로")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    data = json.loads((Path(__file__).parent / "tc.json").read_text(encoding="utf-8"))
    base = next(_base(t["precondition"]) for t in data["testcases"] if "BASE=" in t["precondition"])
    results = []
    for case in data["testcases"]:
        status, detail = run_case(case, base)
        results.append({"id": case["id"], "status": status, "detail": detail,
                        "suggested": bool(case.get("suggested"))})
    counts = {s: sum(r["status"] == s for r in results) for s in ("PASS", "FAIL", "SKIP")}
    for r in results:
        if r["status"] == "FAIL":
            print(f"FAIL {r['id']}: {r['detail']}")
    print(f"결과: PASS {counts['PASS']} / FAIL {counts['FAIL']} / SKIP {counts['SKIP']} (전체 {len(results)})")
    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
