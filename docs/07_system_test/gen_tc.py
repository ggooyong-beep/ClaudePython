#!/usr/bin/env python3
"""tc.json 재생성 스크립트 (docs/07_system_test).

사용: .venv\\Scripts\\python.exe docs\\07_system_test\\gen_tc.py
입력: pict_*_output.tsv (PICT 출력), 출력: tc.json (system-test-skill 스키마)
기대값은 사양서 수용기준과 00_decisions.md 우선순위표로만 도출한다 (src/ 를 읽지 않는다).
PICT 행의 기대값은 oracle()에 우선순위표를 옮겨 계산하며 summary.md 에 수기 검산 결과를 남긴다.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ----------------------------------------------------------------- 공통 표기
BASEDEF = ('BASE={"vehicle_speed_kph":0.0,"gear":"P","crash_status":"NONE","rear_left_approach_risk":false,'
           '"rear_right_approach_risk":false,"fire_detected":false,"overtemperature_detected":false,'
           '"adult_present":false,"isofix_left":false,"isofix_right":false,"ignition_on":true,"sensor_fault":false}. '
           'snapshot=BASE+{...}는 BASE에 중괄호 안 항목을 덮어쓴 전체 JSON. '
           'source_timestamp_s를 따로 적지 않으면 timestamp_s와 같은 값(경과 0 ms). '
           '평가 단계의 HTTP 응답 본문과 직후 GET /status의 값은 같아야 하며 기대값은 둘 모두에 적용한다. '
           '명시하지 않은 필드(override 등)는 판정하지 않는다.')
PRE_FRESH = "서버 신규 기동 직후(초기 상태 lock_left=RELEASE, lock_right=RELEASE, state=OFF, 억제·override 이력 없음). " + BASEDEF
PRE_FRESH_START = ".venv\\Scripts\\python.exe -m uvicorn childlock.web.api:app --app-dir src --port 8000 로 기동. "


def J(v):
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def C(side, action, source="avn"):
    return {"side": side, "action": action, "source": source}


def ev(t, cmd=None, src=None, drop=(), **chg):
    d = {"timestamp_s": t, "source_timestamp_s": t if src is None else src}
    d.update(chg)
    for k in drop:
        d.pop(k, None)
    body = ",".join(f'"{k}":{J(v)}' for k, v in d.items())
    dr = f" (키 삭제: {', '.join(drop)})" if drop else ""
    c = "null" if cmd is None else J(cmd)
    return f"POST /evaluate snapshot=BASE+{{{body}}}{dr}, command={c}"


def X(l=None, r=None, state=None, reason=None, ov=None, http=200, tail=""):
    p = [f"HTTP {http}"]
    if l:
        p.append(f"lock_left={l}")
    if r:
        p.append(f"lock_right={r}")
    if state:
        p.append(f"state={state}")
    if reason:
        p.append(f"reason_code={reason}")
    if ov is not None:
        p.append(f"override={'true' if ov else 'false'}")
    return ", ".join(p) + (" " + tail if tail else "")


class Seq:
    def __init__(self):
        self.steps, self.exp = [], []

    def do(self, text, exp=None):
        n = len(self.steps) + 1
        self.steps.append(f"{n}. {text}")
        if exp:
            self.exp.append(f"[{n}] {exp}")
        return n

    def prime(self, t=1.0):
        self.do(ev(t, vehicle_speed_kph=5.0) + "  (프라이밍: 이전 출력을 LOCK/LOCK으로 만듦)",
                X("LOCK", "LOCK", "NORMAL", "AUTO_LOCK_SPEED"))


# ----------------------------------------------------------------- 테스트 베이시스
TB = [
    ("OEM-SR-001", "충돌 CONFIRMED 긴급 해제", "SW는 OEM 충돌상태가 CONFIRMED가 되면 다른 명령보다 우선하여 후석 좌, 우 잠금 해제를 요구해야 한다. 수용기준: 유효 충돌 입력 시 두 출력이 300 ms 이내 RELEASE이고 이후 입력 주기에도 유지된다.", "functional", "B"),
    ("OEM-SR-002", "후측방 접근위험 잠금과 해제 억제", "SW는 후측방 접근위험이 TRUE인 도어를 LOCK하고 해당 도어의 해제 요청을 억제해야 한다. 수용기준: 접근위험 TRUE가 되면 해당 출력이 LOCK이고 RELEASE 요청에도 LOCK을 유지하며 원인이 기록된다.", "functional", "B"),
    ("OEM-SR-003", "입력 유효성과 freshness", "SW는 안전 관련 입력의 유효성과 freshness를 확인하고 비정상 입력을 정의된 방식으로 처리해야 한다. 수용기준: 필수 입력이 200 ms를 초과해 갱신되지 않으면 100 ms 이내 DEGRADED 상태가 되고, 형식, 범위 오류는 평가 전에 거절된다.", "functional", "B"),
    ("OEM-SR-004", "센서 고장 시 출력 유지", "SW는 정규화 입력의 sensor_fault가 TRUE이면 새 명령을 적용하지 않고 직전 확정 출력을 유지해야 한다. 수용기준: sensor_fault=TRUE인 첫 평가주기에 좌, 우 출력이 유지되고 FAULT 상태와 경고코드가 제공된다.", "functional", "B"),
    ("OEM-FR-001", "운전자 명령 처리", "SW는 물리 버튼, AVN, 음성 및 모바일 앱 경로로 수신한 운전자의 좌, 우, 전체 잠금 및 해제 명령을 처리해야 한다. 수용기준: 정지, 정상입력에서 네 source 각각의 LOCK/RELEASE와 LEFT/RIGHT/ALL 조합이 선택 출력에만 적용된다.", "functional", "QM"),
    ("OEM-FR-002", "이동 시작 자동 잠금", "SW는 차량이 이동을 시작하면 후석 좌, 우 차일드락을 자동으로 활성화해야 한다. 수용기준: 유효 차속이 3 km/h 이상인 첫 평가주기부터 두 출력이 LOCK이다.", "functional", "QM"),
    ("OEM-FR-003", "접근위험 override", "SW는 운전자가 접근위험 경고 후 10초 이하에 같은 해제 명령을 다시 입력하면 명시적 override로 처리해야 한다. 수용기준: 첫 억제 후 경과시간이 10초 이하인 같은 도어 재입력에서 override 상태와 이유코드가 생성된다.", "functional", "QM"),
    ("OEM-FR-004", "상태 표시 인터페이스", "SW는 현재 잠금, 상태, 입력 유효성 및 최근 결정 이유를 표시 인터페이스에 제공해야 한다. 수용기준: 상태조회 응답에 좌, 우 출력, state, 입력유효성 및 이유코드가 포함된다.", "functional", "QM"),
    ("OEM-FR-005", "화재/과온/성인 탑승 강제 해제", "SW는 화재, 과온 또는 성인 탑승이 유효한 불리언 입력으로 확인되면 후석 좌, 우 차일드락을 강제로 해제해야 한다. 수용기준: 각 입력을 단독 주입했을 때 다음 평가주기에 두 출력이 RELEASE이고 입력별 이유코드가 기록된다.", "functional", "QM"),
    ("OEM-FR-006", "ISOFIX 강제 잠금", "SW는 좌, 우 ISOFIX 연결 입력에 따라 해당 후석 차일드락을 강제로 활성화해야 한다. 수용기준: 한쪽 ISOFIX만 TRUE이면 다음 평가주기에 해당 출력만 LOCK이고 반대쪽 출력은 유지된다.", "functional", "QM"),
    ("OEM-FR-007", "시동 OFF 초기 해제", "SW는 ignition_on이 FALSE이면 논리 차일드락 출력을 초기 해제 상태로 전환해야 한다. 수용기준: ignition_on=FALSE인 첫 평가주기에 좌, 우 출력이 RELEASE이고 OFF 상태와 ignition_off 이유가 제공된다.", "functional", "QM"),
    ("OEM-NFR-001", "결정론", "동일한 입력순서와 초기상태에는 동일한 제어결과가 생성되어야 한다. 수용기준: 고정 시계로 같은 벡터 1,000회 재생 시 공개결과 해시가 모두 같다.", "nonfunctional", "QM"),
    ("OEM-NFR-002", "이벤트 저장(100건, 금지정보)", "SW는 최근 제어결정 100건을 메모리 내 저장소에 보존하되 영상, 음성, 개인 식별자를 저장하지 않아야 한다. 수용기준: 101건 입력 후 최신 100건만 순서대로 조회되고 허용 필드만 존재하며 프로세스 재기동 후 데이터가 남지 않는다.", "nonfunctional", "QM"),
    ("OEM-IF-001", "Vehicle→SW 차속/기어/원천시각", "vehicle_speed_kph, gear, source_timestamp_s. km/h 0.0~300.0; P/N/D/R; s. 오류: 누락, 형식, 범위 오류 INVALID.", "functional", "QM"),
    ("OEM-IF-002", "Vehicle→SW 충돌상태", "crash_status NONE/PENDING/CONFIRMED. 오류: 미정 값 INVALID.", "functional", "QM"),
    ("OEM-IF-003", "Vehicle→SW 후측방 접근위험", "rear_left_approach_risk, rear_right_approach_risk (boolean). 오류: 누락, 형식 오류 INVALID.", "functional", "QM"),
    ("OEM-IF-004", "Driver→SW 운전자 명령", "side(left/right/all), action(lock/unlock), source(physical_button/avn/voice/mobile_app). 오류: 누락, 형식, 미등록 enum 거절; 요청 시각은 VehicleSnapshot.timestamp_s 사용.", "functional", "QM"),
    ("OEM-IF-005", "SW→Actuator model 출력", "lock_left/right = LOCK/RELEASE. PC/SIL 논리 출력까지만 검증, 적용 feedback은 범위 밖.", "functional", "QM"),
    ("OEM-IF-006", "SW→Display 표시 데이터", "state, priority_reason, reason_code, input_validity. priority_reason을 reason_code로도 매핑; 직렬화 실패는 HTTP 500.", "functional", "QM"),
    ("OEM-IF-007", "Vehicle→SW 화재/과온/성인", "fire_detected, overtemperature_detected, adult_present (boolean). 오류: 누락, 형식 오류 INVALID.", "functional", "QM"),
    ("OEM-IF-008", "Vehicle→SW ISOFIX", "isofix_left/right (boolean). 오류: 누락, 형식 오류 INVALID.", "functional", "QM"),
    ("OEM-IF-009", "Vehicle→SW 시동/센서 고장", "ignition_on, sensor_fault (boolean). 오류: 누락, 형식 오류 INVALID.", "functional", "QM"),
]

TCS, KEY2ID, DEC_DEP = [], {}, []
_cnt = {"functional": 0, "nonfunctional": 0}


def add(key, basis, title, purpose, seq, inputs, tech, cat="functional", sug=False, dec=None,
        prio="M", pre=None):
    _cnt[cat] += 1
    tid = f"TC-{'F' if cat == 'functional' else 'N'}-{_cnt[cat]:03d}" + ("-S" if sug else "")
    if dec:
        purpose += f" [{', '.join(dec)} 의존]"
        DEC_DEP.append(tid)
    asil = "B" if any(b.startswith("OEM-SR") for b in basis) else "QM"
    TCS.append({
        "id": tid, "basis_ids": basis, "category": cat, "title": title, "purpose": purpose,
        "precondition": pre if pre is not None else PRE_FRESH,
        "inputs": inputs, "steps": seq.steps, "expected": "\n".join(seq.exp),
        "techniques": tech, "suggested": sug, "asil": asil, "priority": prio, "env": "SIL(Web API)",
    })
    KEY2ID[key] = tid
    return tid


BVA, EP, PW, WOW, REQ, ERR, FI = "경계값분석", "동치 클래스", "페어와이즈(PICT)", "WoW 검증", "요구사항 분석", "오류 추정", "결함 주입"

# 무효 입력 TC 공통: 거절 후 출력/상태 유지 -------------------------------------------------


def invalid_tc(key, basis, title, purpose, bad_desc, tech, prime=True, cmd=C("all", "unlock"), drop=(), prio="H",
               **chg):
    s = Seq()
    if prime:
        s.prime(1.0)
        s.do(ev(1.05, cmd=cmd, drop=drop, **chg),
             "HTTP 422, 응답 본문 errors 목록이 비어 있지 않음. GET /status: lock_left=LOCK, lock_right=LOCK, "
             "state=NORMAL, reason_code=INPUT_INVALID (직전 출력·상태 유지, 평가·명령 적용 없음)")
    else:
        s.do(ev(1.0, cmd=cmd, drop=drop, **chg),
             "HTTP 422, 응답 본문 errors 목록이 비어 있지 않음. GET /status: lock_left=RELEASE, lock_right=RELEASE, "
             "state=OFF, reason_code=INPUT_INVALID (초기 상태 유지, 평가 없음)")
    inputs = bad_desc + ("; 직전 출력 LOCK/LOCK(프라이밍), 명령 " + J(cmd) if prime and cmd else
                         "; 초기 출력 RELEASE/RELEASE, 명령 " + (J(cmd) if cmd else "null"))
    return add(key, basis, title, purpose, s, inputs, tech, prio=prio)


# =================================================================== 기능 TC
# ---- IF-001 / SR-003 : 차속 BVA, 형식, 누락 ----------------------------------------------------
s = Seq()
s.do(ev(1.0, vehicle_speed_kph=0.0), X("RELEASE", "RELEASE", "NORMAL", "NO_CHANGE") + ", input_validity의 모든 값이 VALID (0.0은 유효 하한)")
add("speed_min", ["OEM-IF-001", "OEM-SR-003"], "차속 하한 0.0 km/h 수용",
    "하한 경계 0.0을 범위 오류로 오거절(off-by-one, 닫힌 구간 오구현)하거나 0.0에서 자동 잠금을 거는 결함을 발견한다.",
    s, "vehicle_speed_kph=0.0 (경과 0 ms), 명령 없음, 초기 RELEASE/RELEASE", [BVA, EP], prio="H")

s = Seq()
s.do(ev(1.0, vehicle_speed_kph=300.0), X("LOCK", "LOCK", "NORMAL", "AUTO_LOCK_SPEED") + ", input_validity의 모든 값이 VALID (300.0은 유효 상한)")
add("speed_max", ["OEM-IF-001", "OEM-FR-002"], "차속 상한 300.0 km/h 수용",
    "상한 경계 300.0을 범위 오류로 오거절하는 결함(< 300 오구현), 최대 속도에서 잠금이 걸리지 않는 결함을 발견한다.",
    s, "vehicle_speed_kph=300.0, 명령 없음, 초기 RELEASE/RELEASE", [BVA], prio="H")

invalid_tc("speed_below", ["OEM-IF-001", "OEM-SR-003"], "차속 하한 미만 -0.1 km/h 거절",
           "하한 미만 값이 클램프(0.0으로 보정)되거나 평가되어 해제 명령이 적용되는 결함을 발견한다(범위 오류는 평가 전 거절).",
           "vehicle_speed_kph=-0.1", [BVA, EP], vehicle_speed_kph=-0.1)

invalid_tc("speed_above", ["OEM-IF-001", "OEM-SR-003"], "차속 상한 초과 300.1 km/h 거절",
           "상한 초과 값이 클램프(300.0으로 보정)되어 자동 LOCK이 걸리는 결함을 발견한다. 거절되면 초기 RELEASE가 유지되어야 한다.",
           "vehicle_speed_kph=300.1", [BVA, EP], prime=False, cmd=None, vehicle_speed_kph=300.1)

invalid_tc("speed_missing", ["OEM-IF-001", "OEM-SR-003"], "차속 필드 누락 거절",
           "누락된 차속이 0.0 등 기본값으로 채워져 평가되는 결함을 발견한다(누락 무효 클래스).",
           "vehicle_speed_kph 키 없음", [EP, ERR], drop=("vehicle_speed_kph",))

invalid_tc("speed_string", ["OEM-IF-001", "OEM-SR-003"], "차속 형식 오류(문자열) 거절",
           "숫자가 아닌 문자열이 변환 실패 시 0으로 처리되거나 서버 오류(HTTP 500)가 되는 결함을 발견한다(형식 무효 클래스).",
           'vehicle_speed_kph="fast"', [EP, ERR], vehicle_speed_kph="fast")

# ---- IF-001 기어 ----------------------------------------------------------------------------------
s = Seq()
for i, g in enumerate(["P", "N", "D", "R"]):
    s.do(ev(round(1.0 + 0.05 * i, 2), gear=g), X("RELEASE", "RELEASE", "NORMAL", "NO_CHANGE") + f" (gear={g} 수용, 출력 불변)")
s.do(ev(1.2, gear="R", vehicle_speed_kph=3.0), X("LOCK", "LOCK", "NORMAL", "AUTO_LOCK_SPEED") + " (기어와 무관하게 차속 3.0에서 잠금)")
add("gear_valid", ["OEM-IF-001"], "유효 기어 P/N/D/R 네 값 수용과 제어 비의존",
    "유효 enum 중 일부 값을 거절하는 결함, 기어 값(R 등)으로 잠금 판단이 바뀌는 결함을 발견한다.",
    s, "gear=P,N,D,R 순차(차속 0.0), 이후 gear=R 차속 3.0", [EP], dec=["DEC-006"])

invalid_tc("gear_bad", ["OEM-IF-001", "OEM-SR-003"], "미정의 기어 'X' 거절",
           "정의되지 않은 기어 값이 수용되거나 기본 기어로 대체되어 평가되는 결함을 발견한다(enum 무효 클래스).",
           'gear="X"', [EP], gear="X")

invalid_tc("gear_missing", ["OEM-IF-001", "OEM-SR-003"], "기어 필드 누락 거절",
           "기어 누락이 허용되어 평가되는 결함을 발견한다(DEC-006: 기어는 필수 입력으로 검증).",
           "gear 키 없음", [EP, ERR], drop=("gear",))

invalid_tc("srcts_missing", ["OEM-IF-001", "OEM-SR-003"], "source_timestamp_s 누락 거절",
           "원천 시각 누락 시 timestamp_s로 대체되어 freshness 검사가 우회되는 결함을 발견한다.",
           "source_timestamp_s 키 없음", [EP, ERR], drop=("source_timestamp_s",))

invalid_tc("srcts_string", ["OEM-IF-001", "OEM-SR-003"], "source_timestamp_s 형식 오류(문자열) 거절",
           "문자열 시각이 0 또는 현재 시각으로 변환되어 stale 판정이 틀어지는 결함을 발견한다.",
           'source_timestamp_s="noon"', [EP, ERR], source_timestamp_s="noon")

# ---- IF-002 크래시 ----------------------------------------------------------------------------------
s = Seq()
s.prime(1.0)
s.do(ev(1.05, cmd=None, crash_status="NONE"), X("LOCK", "LOCK", "NORMAL", "NO_CHANGE") + " (crash_status=NONE은 출력을 바꾸지 않음)")
add("crash_none", ["OEM-IF-002"], "crash_status=NONE 수용, 출력 불변",
    "NONE이 해제 조건으로 오분류되거나 거절되는 결함을 발견한다(유효 클래스 NONE).",
    s, "crash_status=NONE, 직전 LOCK/LOCK, 명령 없음", [EP])

invalid_tc("crash_bad", ["OEM-IF-002", "OEM-SR-003"], "미정 crash_status 'UNKNOWN' 거절",
           "미정 값이 CONFIRMED로 해석(안전측 오해석)되거나 NONE으로 대체되는 결함을 발견한다. 거절되어 직전 LOCK이 유지되어야 한다.",
           'crash_status="UNKNOWN"', [EP], crash_status="UNKNOWN")

invalid_tc("crash_missing", ["OEM-IF-002", "OEM-SR-003"], "crash_status 누락 거절",
           "누락이 NONE 기본값으로 처리되어 충돌 입력 누락이 은폐되는 결함을 발견한다.",
           "crash_status 키 없음", [EP, ERR], drop=("crash_status",))

# ---- IF-003/007/008/009 불리언 무효 클래스 (필드별 1건, 무효 유형 순환) -----------------------------
invalid_tc("risk_l_string", ["OEM-IF-003", "OEM-SR-003"], "rear_left_approach_risk 문자열 'true' 거절",
           "문자열 'true'가 TRUE로 강제 변환되어 좌측 LOCK이 걸리는(느슨한 형 변환) 결함을 발견한다.",
           'rear_left_approach_risk="true"', [EP, ERR], rear_left_approach_risk="true")
invalid_tc("risk_r_missing", ["OEM-IF-003", "OEM-SR-003"], "rear_right_approach_risk 누락 거절",
           "누락된 우측 접근위험이 FALSE로 간주되어 위험 정보 유실이 은폐되는 결함을 발견한다.",
           "rear_right_approach_risk 키 없음", [EP, ERR], drop=("rear_right_approach_risk",))
invalid_tc("fire_missing", ["OEM-IF-007", "OEM-SR-003"], "fire_detected 누락 거절",
           "누락된 화재 입력이 FALSE로 간주되는 결함을 발견한다.",
           "fire_detected 키 없음", [EP, ERR], drop=("fire_detected",))
invalid_tc("overtemp_string", ["OEM-IF-007", "OEM-SR-003"], "overtemperature_detected 문자열 'false' 거절",
           "비어 있지 않은 문자열이 truthy로 평가되어 강제 해제(RELEASE)되는 결함을 발견한다.",
           'overtemperature_detected="false"', [EP, ERR], overtemperature_detected="false")
invalid_tc("adult_int", ["OEM-IF-007", "OEM-SR-003"], "adult_present 정수 1 거절",
           "정수 1이 TRUE로 강제 변환되어 성인 탑승 강제 해제가 동작하는 결함을 발견한다(JSON boolean만 유효, OI-13).",
           "adult_present=1", [EP, ERR], adult_present=1)
invalid_tc("isofix_l_missing", ["OEM-IF-008", "OEM-SR-003"], "isofix_left 누락 거절",
           "누락된 ISOFIX 입력이 FALSE로 간주되는 결함을 발견한다.",
           "isofix_left 키 없음", [EP, ERR], drop=("isofix_left",))
invalid_tc("isofix_r_string", ["OEM-IF-008", "OEM-SR-003"], "isofix_right 문자열 'yes' 거절",
           "비 boolean 문자열이 TRUE로 해석되어 우측 LOCK이 걸리는 결함을 발견한다.",
           'isofix_right="yes"', [EP, ERR], isofix_right="yes")
invalid_tc("ign_missing", ["OEM-IF-009", "OEM-SR-003"], "ignition_on 누락 거절",
           "누락된 시동 입력이 FALSE로 간주되어 RELEASE(OFF)로 전환되거나 TRUE로 간주되는 결함을 발견한다.",
           "ignition_on 키 없음", [EP, ERR], drop=("ignition_on",))
invalid_tc("fault_string", ["OEM-IF-009", "OEM-SR-003"], "sensor_fault 문자열 '1' 거절",
           "문자열이 TRUE로 변환되어 FAULT 상태로 진입하거나 FALSE로 변환되어 고장이 은폐되는 결함을 발견한다.",
           'sensor_fault="1"', [EP, ERR], sensor_fault="1")

# ---- IF-004 명령 무효 클래스 ---------------------------------------------------------------------
invalid_tc("cmd_side_bad", ["OEM-IF-004", "OEM-SR-003"], "명령 side 미등록 값 'center' 거절",
           "미등록 side가 all 등으로 대체되어 해제가 적용되는 결함을 발견한다. 주기 전체가 거절되어야 한다.",
           'command.side="center"', [EP], cmd={"side": "center", "action": "unlock", "source": "avn"})
invalid_tc("cmd_action_bad", ["OEM-IF-004", "OEM-SR-003"], "명령 action 미등록 값 'toggle' 거절",
           "미등록 action이 unlock 등으로 해석되어 출력이 바뀌는 결함을 발견한다.",
           'command.action="toggle"', [EP], cmd={"side": "all", "action": "toggle", "source": "avn"})
invalid_tc("cmd_source_bad", ["OEM-IF-004", "OEM-SR-003"], "명령 source 미등록 값 'bluetooth' 거절",
           "미등록 source의 명령이 처리되는(source 화이트리스트 누락) 결함을 발견한다.",
           'command.source="bluetooth"', [EP], cmd={"side": "all", "action": "unlock", "source": "bluetooth"})
invalid_tc("cmd_source_missing", ["OEM-IF-004", "OEM-SR-003"], "명령 source 누락 거절",
           "source가 없는 명령이 기본 source로 처리되는 결함을 발견한다(누락 무효 클래스).",
           "command={side:all, action:unlock} (source 없음)", [EP, ERR], cmd={"side": "all", "action": "unlock"})
invalid_tc("cmd_side_type", ["OEM-IF-004", "OEM-SR-003"], "명령 side 형식 오류(숫자 0) 거절",
           "숫자 값이 인덱스로 해석되어 좌측 등에 적용되거나 서버 오류(500)가 되는 결함을 발견한다(형식 무효 클래스).",
           "command.side=0", [EP, ERR], cmd={"side": 0, "action": "unlock", "source": "avn"})

# ---- FR-001 PICT (Source x Side x Action) ------------------------------------------------------------
rowsA = [l.split("\t") for l in (HERE / "pict_command_output.tsv").read_text(encoding="utf-8").strip().splitlines()[1:]]
PICT_A_KEYS = []
for i, (src, side, act) in enumerate(rowsA, 1):
    s = Seq()
    if act == "lock":
        pl, pr = "RELEASE", "RELEASE"
        s.do(ev(1.0, cmd=C(side, act, src)), "")
        t_idx = 1
    else:
        pl, pr = "LOCK", "LOCK"
        s.prime(1.0)
        s.do(ev(1.05, cmd=C(side, act, src)), "")
        t_idx = 2
    res = "LOCK" if act == "lock" else "RELEASE"
    l = res if side in ("left", "all") else pl
    r = res if side in ("right", "all") else pr
    s.exp.append(f"[{t_idx}] " + X(l, r, "NORMAL", "DRIVER_COMMAND") +
                 f" (선택 측 {side}만 {res}, 선택되지 않은 측은 직전 값 유지)")
    k = f"pictA_{i}"
    PICT_A_KEYS.append((k, src, side, act))
    add(k, ["OEM-FR-001", "OEM-IF-004"], f"명령 조합 #{i}: source={src}, side={side}, action={act}",
        "선택 측이 아닌 출력까지 바뀌는 결함, 특정 source/side/action 조합이 무시되거나 반대로 적용되는 결함을 발견한다 (페어와이즈).",
        s, f"command={J(C(side, act, src))}, 차속 0.0, 직전 출력 {pl}/{pr}", [PW, EP],
        pre=PRE_FRESH + " (페어와이즈 모델 pict_command_model.txt 행 %d)" % i)

# ---- FR-001 연속 입력 (WoW) -----------------------------------------------------------------------------
s = Seq()
seqc = [("all", "lock", "physical_button", "LOCK", "LOCK"), ("all", "unlock", "avn", "RELEASE", "RELEASE"),
        ("left", "lock", "voice", "LOCK", "RELEASE"), ("left", "unlock", "mobile_app", "RELEASE", "RELEASE"),
        ("right", "lock", "physical_button", "RELEASE", "LOCK"), ("all", "lock", "avn", "LOCK", "LOCK"),
        ("right", "unlock", "voice", "LOCK", "RELEASE"), ("all", "unlock", "mobile_app", "RELEASE", "RELEASE"),
        ("all", "lock", "voice", "LOCK", "LOCK"), ("left", "unlock", "avn", "RELEASE", "LOCK"),
        ("left", "unlock", "avn", "RELEASE", "LOCK")]
for i, (sd, ac, sr, l, r) in enumerate(seqc):
    s.do(ev(round(1.0 + 0.05 * i, 2), cmd=C(sd, ac, sr)), X(l, r, "NORMAL", "DRIVER_COMMAND") + ("  (직전과 동일 명령 중복: 멱등)" if i == 10 else ""))
s.do(ev(1.55, cmd=None), X("RELEASE", "LOCK", "NORMAL", "NO_CHANGE") + " (명령 없음: 직전 출력 유지)")
add("cmd_burst", ["OEM-FR-001"], "50 ms 주기 연속 명령 12주기(source·side·action 교차, 중복 포함)",
    "연속 명령 시 일부 주기 명령이 누락·지연되거나 직전 명령 잔상이 남는 결함, 중복 명령이 상태를 뒤집는 결함을 발견한다.",
    s, "차속 0.0, 50 ms 간격 11개 명령 + 명령 없는 1주기", [WOW, EP])

# ---- SR-001 충돌 ----------------------------------------------------------------------------------------
s = Seq()
s.prime(1.0)
allbad = dict(crash_status="CONFIRMED", vehicle_speed_kph=50.0, isofix_left=True, isofix_right=True,
              rear_left_approach_risk=True, rear_right_approach_risk=True)
s.do(ev(1.05, cmd=C("all", "lock"), **allbad), X("RELEASE", "RELEASE", "NORMAL", "CRASH_CONFIRMED", ov=False) + " (첫 평가주기에 RELEASE)")
for i in range(1, 7):
    cm = C("all", "lock", "voice") if i <= 3 else (None if i <= 5 else C("all", "unlock"))
    s.do(ev(round(1.05 + 0.05 * i, 2), cmd=cm, **allbad), X("RELEASE", "RELEASE", "NORMAL", "CRASH_CONFIRMED") +
         f" (충돌 입력 후 {50 * i} ms, 유지)")
add("crash_main", ["OEM-SR-001"], "CONFIRMED가 모든 잠금 요인과 잠금 명령보다 우선하고 300 ms 구간 유지",
    "충돌 해제가 LOCK 명령·ISOFIX·접근위험·자동 잠금에 밀리는 결함, 첫 주기에 해제되지 않는 결함, 해제 후 몇 주기 뒤 다시 LOCK되는 결함을 발견한다.",
    s, "crash_status=CONFIRMED + 차속 50.0 + isofix L/R=true + 접근위험 L/R=true + 명령 lock all, 직전 LOCK/LOCK, 6주기 추가 유지(총 300 ms)",
    [EP, REQ, BVA], prio="H")

s = Seq()
s.prime(10.0)
s.do(ev(10.25, src=10.05, crash_status="CONFIRMED", vehicle_speed_kph=0.0), X("RELEASE", "RELEASE", "NORMAL", "CRASH_CONFIRMED") + " (경과 200 ms는 fresh, 해제 적용)")
add("crash_age200", ["OEM-SR-001", "OEM-SR-003"], "경과 200 ms(경계) 충돌 입력의 해제 적용",
    "freshness 경계에서 충돌 해제가 stale로 오분류되어 무시되는(>= 200 오구현) 결함을 발견한다.",
    s, "timestamp_s=10.25, source_timestamp_s=10.05 (경과 200 ms), crash_status=CONFIRMED, 직전 LOCK/LOCK", [BVA], prio="H")

# ---- SR-002 접근위험 -----------------------------------------------------------------------------------
s = Seq()
s.do(ev(1.0, rear_left_approach_risk=True), X("LOCK", "RELEASE", "NORMAL", "APPROACH_RISK_LEFT", ov=False) + " (좌측만 LOCK, 우측은 영향 없음)")
s.do(ev(1.05, cmd=C("left", "unlock"), rear_left_approach_risk=True), X("LOCK", "RELEASE", "NORMAL", "APPROACH_RISK_LEFT", ov=False) + " (해제 요청 억제)")
s.do(ev(1.10, cmd=C("right", "lock", "voice"), rear_left_approach_risk=True), X("LOCK", "LOCK", "NORMAL", "APPROACH_RISK_LEFT") + " (우측 명령은 정상 적용, 사유는 상위 순위인 접근위험)")
add("risk_left", ["OEM-SR-002", "OEM-IF-003"], "좌측 접근위험: 좌 LOCK, 해제 요청 억제, 우측 독립",
    "접근위험이 우측 출력까지 바꾸는 결함, 해제 요청이 억제되지 않는 결함, 원인(이유코드)이 기록되지 않는 결함을 발견한다.",
    s, "rear_left_approach_risk=true, 명령 unlock left(avn), lock right(voice), 초기 RELEASE/RELEASE", [EP, REQ], prio="H")

s = Seq()
s.prime(1.0)
s.do(ev(1.05, cmd=C("all", "unlock"), rear_right_approach_risk=True), X("RELEASE", "LOCK", "NORMAL", "APPROACH_RISK_RIGHT", ov=False) + " (우측만 억제, 좌측은 해제 적용)")
add("risk_right", ["OEM-SR-002", "OEM-IF-003"], "우측 접근위험: unlock all에서 우측만 억제(좌우 대칭)",
    "좌우 로직 비대칭(우측 접근위험 처리 누락)과 all 명령이 접근위험 측까지 해제하는 결함을 발견한다.",
    s, "rear_right_approach_risk=true, 명령 unlock all(avn), 직전 LOCK/LOCK", [EP, REQ], prio="H")

s = Seq()
s.do(ev(1.0, cmd=C("all", "unlock"), rear_left_approach_risk=True, rear_right_approach_risk=True),
     X("LOCK", "LOCK", "NORMAL", "APPROACH_RISK_LEFT", ov=False) + " (양측 억제; 같은 순위의 좌우 사유는 좌측 우선: OI-09)")
add("risk_both", ["OEM-SR-002", "OEM-IF-003"], "양측 접근위험 동시 + unlock all: 양측 LOCK",
    "양측 동시 위험에서 한쪽만 처리되는 결함을 발견한다.",
    s, "rear_left/right_approach_risk=true, 명령 unlock all(avn), 초기 RELEASE/RELEASE", [EP])

s = Seq()
s.do(ev(1.0, rear_left_approach_risk=True), X("LOCK", "RELEASE", "NORMAL", "APPROACH_RISK_LEFT"))
s.do(ev(1.05, cmd=C("left", "unlock"), rear_left_approach_risk=False), X("RELEASE", "RELEASE", "NORMAL", "DRIVER_COMMAND", ov=False) + " (접근위험 해제 후 해제 명령 허용)")
add("risk_clear", ["OEM-SR-002"], "접근위험 FALSE 복귀 후 해제 명령 허용",
    "접근위험이 사라진 뒤에도 억제가 남아 해제가 계속 거절되는(래치) 결함을 발견한다.",
    s, "rear_left_approach_risk true→false, 이후 명령 unlock left(avn)", [WOW, EP])

# ---- FR-003 override BVA ---------------------------------------------------------------------------------


def override_tc(key, t2, expect_override, title, purpose, tech, t1=1.0, extra_basis=()):
    s = Seq()
    s.do(ev(t1, cmd=C("left", "unlock"), rear_left_approach_risk=True), X("LOCK", "RELEASE", "NORMAL", "APPROACH_RISK_LEFT", ov=False) + f" (최초 억제, 기준 시각 {t1:.3f} s)")
    if expect_override:
        s.do(ev(t2, cmd=C("left", "unlock"), rear_left_approach_risk=True),
             X("RELEASE", "RELEASE", "NORMAL", "APPROACH_OVERRIDE", ov=True) + f" (경과 {round((t2 - t1) * 1000)} ms ≤ 10000 ms: override)")
    else:
        s.do(ev(t2, cmd=C("left", "unlock"), rear_left_approach_risk=True),
             X("LOCK", "RELEASE", "NORMAL", "APPROACH_RISK_LEFT", ov=False) + f" (경과 {round((t2 - t1) * 1000)} ms > 10000 ms: override 아님, 다시 억제)")
    return add(key, ["OEM-FR-003", "OEM-SR-002"] + list(extra_basis), title, purpose, s,
               f"rear_left_approach_risk=true, unlock left(avn) 2회: t={t1:.3f}, t={t2:.3f} (간격 {round((t2 - t1) * 1000)} ms)",
               tech, dec=["DEC-007"], prio="H")


override_tc("ov_9999", 10.999, True, "override 경계 9.999 s(경계 -1 ms) 재입력 = override",
            "윈도 경계 직전에서 override가 성립하지 않는 결함(< 9 s 등 윈도 축소)을 발견한다.", [BVA])
override_tc("ov_10000", 11.0, True, "override 경계 10.000 s 재입력 = override (이하 포함)",
            "'10초 이하'를 '미만'으로 구현한 경계 오류(< 10000)를 발견한다.", [BVA])
override_tc("ov_10001", 11.001, False, "override 경계 10.001 s 재입력 = override 아님",
            "윈도가 10초를 넘어 연장되는 결함(<= 10001 등), 부동소수점 오차로 경계가 틀어지는 결함을 발견한다.", [BVA])

s = Seq()
s.do(ev(1.0, cmd=C("left", "unlock"), rear_left_approach_risk=True, rear_right_approach_risk=True), X("LOCK", "LOCK", "NORMAL", "APPROACH_RISK_LEFT", ov=False) + " (좌 최초 억제 기준 1.000 s)")
s.do(ev(5.0, cmd=C("right", "unlock"), rear_left_approach_risk=True, rear_right_approach_risk=True), X("LOCK", "LOCK", "NORMAL", "APPROACH_RISK_LEFT", ov=False) + " (우 최초 억제 기준 5.000 s, 우측 입력은 좌측 override를 만들지 않음)")
s.do(ev(11.0, cmd=C("left", "unlock"), rear_left_approach_risk=True, rear_right_approach_risk=True),
     X("RELEASE", "LOCK", "NORMAL", "APPROACH_OVERRIDE", ov=True) + " (좌: 1.000 s 기준 10.000 s라 override, 우: 명령 없음이라 LOCK 유지)")
add("ov_indep", ["OEM-FR-003", "OEM-SR-002"], "override 도어별 독립: 반대쪽 도어 입력이 타이머/override에 영향 없음",
    "억제 시각을 도어별로 기억하지 않고 공유하거나(우측 입력이 좌측 기준시각을 덮어씀) override가 반대쪽 도어로 번지는 결함을 발견한다.",
    s, "양측 접근위험 true, t=1.000 unlock left, t=5.000 unlock right, t=11.000 unlock left", [EP, REQ], dec=["DEC-007"], prio="H")

# ---- SR-004 센서 고장 --------------------------------------------------------------------------------------
s = Seq()
s.prime(1.0)
s.do(ev(1.05, cmd=C("all", "unlock"), sensor_fault=True), X("LOCK", "LOCK", "FAULT", "SENSOR_FAULT") + " (첫 평가주기에 명령 미적용, 직전 LOCK 유지, 경고코드 SENSOR_FAULT)")
add("fault_hold_lock", ["OEM-SR-004", "OEM-IF-009"], "sensor_fault=TRUE 첫 주기: 직전 LOCK/LOCK 유지, 해제 명령 미적용",
    "고장 시 새 명령이 적용되는 결함, 첫 주기가 아닌 다음 주기부터 유지되는 지연 결함, FAULT 상태/경고코드 누락을 발견한다.",
    s, "sensor_fault=true, 명령 unlock all(avn), 직전 LOCK/LOCK", [FI, EP], prio="H")

s = Seq()
s.do(ev(1.0, cmd=C("all", "lock"), sensor_fault=True, vehicle_speed_kph=50.0, isofix_left=True),
     X("RELEASE", "RELEASE", "FAULT", "SENSOR_FAULT") + " (직전 RELEASE 유지: 자동 잠금·ISOFIX·명령 모두 미적용)")
add("fault_hold_release", ["OEM-SR-004", "OEM-IF-009"], "sensor_fault=TRUE: 직전 RELEASE/RELEASE 유지(자동 잠금·ISOFIX·lock 명령 미적용)",
    "고장 시 출력이 안전측으로 가정된 LOCK으로 고정되거나 자동 잠금/ISOFIX 규칙이 계속 적용되는 결함을 발견한다(유지 방향 양방향 검증).",
    s, "sensor_fault=true + 차속 50.0 + isofix_left=true + 명령 lock all, 초기 RELEASE/RELEASE", [FI, EP], prio="H")

s = Seq()
s.do(ev(1.0, cmd=C("left", "lock")), X("LOCK", "RELEASE", "NORMAL", "DRIVER_COMMAND"))
s.do(ev(1.05, cmd=C("all", "unlock"), sensor_fault=True), X("LOCK", "RELEASE", "FAULT", "SENSOR_FAULT") + " (좌우 서로 다른 직전 출력이 각각 유지)")
s.do(ev(1.10, cmd=C("all", "unlock"), sensor_fault=False), X("RELEASE", "RELEASE", "NORMAL", "DRIVER_COMMAND") + " (고장 해소 다음 주기에 FAULT 탈출, 명령 적용)")
add("fault_hold_asym", ["OEM-SR-004"], "sensor_fault 유지가 측별로 독립이고 해소 후 복귀",
    "유지 시 한쪽 값을 양쪽에 복사하는 결함, FAULT가 래치되어 복귀하지 못하는 결함을 발견한다.",
    s, "좌 LOCK/우 RELEASE에서 sensor_fault=true+unlock all, 다음 주기 sensor_fault=false+unlock all", [FI, WOW], prio="H")

# ---- FR-002 자동 잠금 BVA ----------------------------------------------------------------------------------
for key, v, l, reason, ttl, pur in (
        ("auto_29", 2.9, "RELEASE", "NO_CHANGE", "차속 2.9 km/h(임계 -0.1): 자동 잠금 미적용", "임계 미만에서 잠금이 걸리는(> 2.5 등 임계 오설정, 반올림) 결함을 발견한다."),
        ("auto_30", 3.0, "LOCK", "AUTO_LOCK_SPEED", "차속 3.0 km/h(임계): 첫 평가주기부터 LOCK", "'이상'을 '초과'로 구현한 경계 오류(> 3.0)를 발견한다."),
        ("auto_31", 3.1, "LOCK", "AUTO_LOCK_SPEED", "차속 3.1 km/h(임계 +0.1): LOCK", "임계 초과 영역에서 잠금이 걸리지 않는 결함을 발견한다.")):
    s = Seq()
    s.do(ev(1.0, vehicle_speed_kph=v), X(l, l, "NORMAL", reason) + (" (같은 첫 평가주기에 적용)" if l == "LOCK" else " (규칙 미적용, 초기 RELEASE 유지)"))
    add(key, ["OEM-FR-002", "OEM-IF-001"], ttl, pur, s, f"vehicle_speed_kph={v}, 명령 없음, 초기 RELEASE/RELEASE", [BVA], prio="H")

s = Seq()
for i, v in enumerate([0.0, 2.9, 3.0, 2.9, 0.0]):
    exp = (X("RELEASE", "RELEASE", "NORMAL", "NO_CHANGE") if i < 2 else
           X("LOCK", "LOCK", "NORMAL", "AUTO_LOCK_SPEED") if i == 2 else X("LOCK", "LOCK", "NORMAL", "NO_CHANGE"))
    s.do(ev(round(1.0 + 0.05 * i, 2), vehicle_speed_kph=v), exp + (" (임계 아래로 내려가도 자동 해제 없음)" if i >= 3 else ""))
add("auto_hold", ["OEM-FR-002"], "차속이 3.0 임계를 오르내릴 때 LOCK은 자동 해제되지 않음",
    "속도가 내려가면 LOCK이 풀리는(히스테리시스 없는 토글) 결함을 발견한다.",
    s, "차속 0.0→2.9→3.0→2.9→0.0 (50 ms 간격), 명령 없음", [WOW, BVA], sug=True, dec=["DEC-001"])

# ---- SWR-004 / DEC-005 해제 거절 ------------------------------------------------------------------------
s = Seq()
s.prime(1.0)
s.do(ev(1.05, cmd=C("all", "unlock"), vehicle_speed_kph=2.9), X("RELEASE", "RELEASE", "NORMAL", "DRIVER_COMMAND") + " (2.9 km/h에서 해제 허용)")
add("deny_29", ["OEM-FR-001", "OEM-FR-002"], "차속 2.9 km/h에서 unlock all 허용",
    "해제 허용 조건을 3 km/h보다 낮게(예: 0 km/h만) 설정한 결함을 발견한다.",
    s, "vehicle_speed_kph=2.9, 명령 unlock all(avn), 직전 LOCK/LOCK", [BVA], sug=True, dec=["DEC-005"])
s = Seq()
s.prime(1.0)
s.do(ev(1.05, cmd=C("all", "unlock"), vehicle_speed_kph=3.0), X("LOCK", "LOCK", "NORMAL", "RELEASE_DENIED_MOVING") + " (3.0 km/h에서 해제 거절, 사유 기록)")
add("deny_30", ["OEM-FR-001", "OEM-FR-002"], "차속 3.0 km/h에서 unlock all 거절(RELEASE_DENIED_MOVING)",
    "이동 중 해제 명령이 적용되는 결함, 거절 사유가 기록되지 않는 결함을 발견한다.",
    s, "vehicle_speed_kph=3.0, 명령 unlock all(avn), 직전 LOCK/LOCK", [BVA], sug=True, dec=["DEC-005"])

# ---- SR-003 freshness ----------------------------------------------------------------------------------
s = Seq()
s.prime(10.0)
s.do(ev(10.25, src=10.05, cmd=C("all", "unlock")), X("RELEASE", "RELEASE", "NORMAL", "DRIVER_COMMAND") + " (경과 200 ms는 정상, 명령 적용)")
add("stale_200", ["OEM-SR-003", "OEM-IF-001"], "경과 200 ms(경계)는 정상 평가",
    "'초과'를 '이상'으로 구현한 경계 오류(>= 200)로 200 ms에서 DEGRADED가 되는 결함을 발견한다.",
    s, "timestamp_s=10.25, source_timestamp_s=10.05 (경과 200 ms), 명령 unlock all, 직전 LOCK/LOCK", [BVA], dec=["DEC-007"], prio="H")
s = Seq()
s.prime(10.0)
s.do(ev(10.251, src=10.05, cmd=C("all", "unlock")), X("LOCK", "LOCK", "DEGRADED", "INPUT_STALE") + " (경과 201 ms는 stale: 명령 미적용, 직전 출력 유지)")
add("stale_201", ["OEM-SR-003", "OEM-IF-001"], "경과 201 ms(경계+1)는 DEGRADED",
    "stale 판정이 늦거나(> 250 등) 반올림 오류로 201 ms가 정상이 되는 결함, DEGRADED에서 명령이 적용되는 결함을 발견한다.",
    s, "timestamp_s=10.251, source_timestamp_s=10.05 (경과 201 ms), 명령 unlock all, 직전 LOCK/LOCK", [BVA], dec=["DEC-007", "DEC-004"], prio="H")

s = Seq()
s.prime(10.0)
for tt, ex in ((10.05, "NORMAL"), (10.10, "NORMAL"), (10.15, "NORMAL"), (10.20, "NORMAL"), (10.201, "DEGRADED"), (10.25, "DEGRADED"), (10.30, "DEGRADED")):
    e = (X("LOCK", "LOCK", ex) if ex == "NORMAL" else X("LOCK", "LOCK", ex, "INPUT_STALE"))
    why = {10.20: " (경과 200 ms)", 10.201: " (경과 201 ms)", 10.25: " (200 ms 초과 후 50 ms, 100 ms 이내)", 10.30: " (200 ms 초과 후 100 ms 시점)"}.get(tt, "")
    s.do(f"POST /tick {{\"timestamp_s\":{tt}}}", e + why)
s.exp.append("[판정] 마지막 유효 입력(source_timestamp_s=10.0) 기준 200 ms 초과 후 첫 주기(10.25 이전 최초 DEGRADED 응답 시각)가 한도 +100 ms(10.30) 이내")
add("stale_tick", ["OEM-SR-003"], "입력이 갱신되지 않을 때 /tick 경과: 200 ms 초과 후 100 ms 이내 DEGRADED",
    "무입력 시 stale 감지가 지연(평가가 입력 도착 시에만 수행)되거나 200 ms 직후 DEGRADED가 되지 않는 결함, DEGRADED에서 출력이 바뀌는 결함을 발견한다.",
    s, "프라이밍 후 입력 없이 /tick timestamp_s=10.05, 10.10, 10.15, 10.20, 10.201, 10.25, 10.30", [BVA, WOW], dec=["DEC-002", "DEC-007"], prio="H")

s = Seq()
s.prime(10.0)
s.do(ev(10.30, src=10.0, cmd=C("all", "unlock")), X("LOCK", "LOCK", "DEGRADED", "INPUT_STALE") + " (stale 입력의 명령 미적용)")
s.do(ev(10.35), X("LOCK", "LOCK", "NORMAL", "NO_CHANGE") + " (fresh 입력 복귀 첫 주기에 NORMAL, 이전 stale 명령은 소급 적용되지 않음)")
s.do(ev(10.40, cmd=C("all", "unlock")), X("RELEASE", "RELEASE", "NORMAL", "DRIVER_COMMAND") + " (복귀 후 명령 정상 적용)")
add("stale_recover", ["OEM-SR-003"], "DEGRADED 복귀: fresh 입력 첫 주기 NORMAL, stale 중 명령 미소급",
    "DEGRADED가 래치되어 복귀하지 않는 결함, stale 중 거부된 명령이 복귀 시 적용되는 결함을 발견한다.",
    s, "경과 300 ms + unlock all → 경과 0 ms 무명령 → unlock all", [WOW, EP], sug=True, dec=["DEC-004"], prio="H")

s = Seq()
s.prime(10.0)
s.do(ev(10.30, src=10.0, sensor_fault=True), X("LOCK", "LOCK", "DEGRADED", "INPUT_STALE") + " (stale이 sensor_fault보다 상위: 사유 INPUT_STALE)")
s.do(ev(10.35, sensor_fault=True), X("LOCK", "LOCK", "FAULT", "SENSOR_FAULT") + " (fresh + 고장: DEGRADED→FAULT)")
s.do(ev(10.60, src=10.35, sensor_fault=True), X("LOCK", "LOCK", "DEGRADED", "INPUT_STALE") + " (경과 250 ms: FAULT→DEGRADED)")
add("stale_fault", ["OEM-SR-003", "OEM-SR-004"], "stale과 sensor_fault 동시/전이: DEGRADED가 FAULT보다 우선",
    "상태 우선순위(DEGRADED→FAULT) 역전, 상태 전이 경로 누락(FAULT↔DEGRADED)을 발견한다.",
    s, "경과 300 ms+sensor_fault, 경과 0+sensor_fault, 경과 250 ms+sensor_fault", [WOW, FI], sug=True, dec=["DEC-001", "DEC-004"])

s = Seq()
s.prime(10.0)
s.do(ev(10.30, src=10.0, crash_status="CONFIRMED"), X("LOCK", "LOCK", "DEGRADED", "INPUT_STALE") + " (stale 입력의 CONFIRMED는 평가 전 단계(순위 0)에서 보류: OI-03)")
add("stale_crash", ["OEM-SR-001", "OEM-SR-003"], "stale 충돌 입력(경과 300 ms)은 해제를 일으키지 않고 DEGRADED 유지",
    "순위 0(stale)과 순위 1(충돌)의 상호작용이 우선순위표와 다르게 구현된 결함을 발견한다. 안전 영향은 OI-03로 OEM 확인 필요.",
    s, "경과 300 ms, crash_status=CONFIRMED, 직전 LOCK/LOCK", [WOW, EP], sug=True, dec=["DEC-001", "DEC-004"])

# ---- 롤오버 경계 (WoW) -----------------------------------------------------------------------------
def f3(ms):
    return round(ms / 1000.0, 3)


s = Seq()
for base_ms in (65536, 2147483648, 4294967296):
    s.do(ev(f3(base_ms), vehicle_speed_kph=5.0) + "  (프라이밍)", X("LOCK", "LOCK", "NORMAL", "AUTO_LOCK_SPEED"))
    s.do(ev(f3(base_ms + 250), src=f3(base_ms + 50), cmd=C("all", "unlock")), X("RELEASE", "RELEASE", "NORMAL", "DRIVER_COMMAND") + f" (기준 {base_ms} ms에서 경과 200 ms: 정상)")
    s.do(ev(f3(base_ms + 300), src=f3(base_ms + 100), cmd=C("all", "lock")), X("LOCK", "LOCK", "NORMAL", "DRIVER_COMMAND") + " (경과 200 ms: 정상, 재잠금)")
    s.do(ev(f3(base_ms + 301), src=f3(base_ms + 100), cmd=C("all", "unlock")), X("LOCK", "LOCK", "DEGRADED", "INPUT_STALE") + " (경과 201 ms: DEGRADED)")
add("rollover", ["OEM-SR-003"], "시각 절대값이 16/31/32비트 ms 카운터 경계(65.536 s, 2147483.648 s, 4294967.296 s)에서도 200/201 ms 판정 유지",
    "시각을 정수 ms로 환산하는 과정의 오버플로·정밀도 손실로 경계 판정이 틀어지는 결함을 발견한다.",
    s, "각 기준 B(ms)=65536, 2147483648, 4294967296에서 timestamp_s/source_timestamp_s 쌍(경과 200 ms, 200 ms, 201 ms)", [WOW, BVA], dec=["DEC-007"])

s = Seq()
s.do(ev(4294962.0, cmd=C("left", "unlock"), rear_left_approach_risk=True), X("LOCK", "RELEASE", "NORMAL", "APPROACH_RISK_LEFT", ov=False) + " (최초 억제 기준 4294962.000 s)")
s.do(ev(4294972.0, cmd=C("left", "unlock"), rear_left_approach_risk=True), X("RELEASE", "RELEASE", "NORMAL", "APPROACH_OVERRIDE", ov=True) + " (32비트 ms 경계를 가로지르는 10.000 s: override)")
add("ov_rollover", ["OEM-FR-003"], "override 10.000 s 윈도가 2^32 ms(4294967.296 s) 경계를 가로질러도 성립",
    "억제 시각 저장·차분이 32비트로 래핑되어 override 판정이 틀어지는 결함을 발견한다.",
    s, "rear_left_approach_risk=true, unlock left 2회: t=4294962.000, t=4294972.000", [WOW, BVA], dec=["DEC-007"])

# ---- FR-003 추가(제안) ---------------------------------------------------------------------------------
s = Seq()
s.do(ev(1.0, cmd=C("left", "unlock"), rear_left_approach_risk=True), X("LOCK", "RELEASE", "NORMAL", "APPROACH_RISK_LEFT", ov=False))
s.do(ev(2.0, cmd=C("left", "unlock"), rear_left_approach_risk=True), X("RELEASE", "RELEASE", "NORMAL", "APPROACH_OVERRIDE", ov=True))
s.do(ev(2.05, rear_left_approach_risk=True), X("RELEASE", "RELEASE", "NORMAL", "APPROACH_OVERRIDE", ov=True) + " (override 유지: 접근위험 TRUE인 동안 RELEASE)")
s.do(ev(2.10, cmd=C("left", "lock"), rear_left_approach_risk=True), X("LOCK", "RELEASE", "NORMAL", "DRIVER_COMMAND", ov=False) + " (lock 명령이 override 해제)")
s.do(ev(2.15, rear_left_approach_risk=True), X("LOCK", "RELEASE", "NORMAL", "APPROACH_RISK_LEFT", ov=False) + " (접근위험 규칙 복귀)")
add("ov_persist", ["OEM-FR-003", "OEM-SR-002"], "override 지속과 lock 명령에 의한 해제",
    "override가 한 주기만 지속되고 곧바로 다시 LOCK되는 결함, lock 명령이 override를 해제하지 못하는 결함을 발견한다.",
    s, "rear_left_approach_risk=true 유지, unlock left 2회(간격 1.0 s) → 무명령 → lock left → 무명령", [WOW, REQ], sug=True, dec=["DD-004"])

s = Seq()
s.do(ev(1.0, cmd=C("left", "unlock"), rear_left_approach_risk=True), X("LOCK", "RELEASE", "NORMAL", "APPROACH_RISK_LEFT", ov=False))
s.do(ev(3.0, rear_left_approach_risk=False), X("LOCK", "RELEASE", "NORMAL", "NO_CHANGE") + " (접근위험 해소: 억제 이력 삭제)")
s.do(ev(4.0, cmd=C("left", "unlock"), rear_left_approach_risk=True), X("LOCK", "RELEASE", "NORMAL", "APPROACH_RISK_LEFT", ov=False) + " (재발생 후 첫 해제 요청은 최초 억제이므로 override 아님)")
add("ov_clear", ["OEM-FR-003"], "접근위험 해소 후 재발생 시 억제 이력 초기화(override 아님)",
    "억제 시각이 접근위험 해소 후에도 남아 재발생 직후 해제 요청이 override로 오처리되는 결함을 발견한다.",
    s, "t=1.0 unlock left(위험 true), t=3.0 위험 false, t=4.0 unlock left(위험 true)", [WOW], sug=True, dec=["DD-004", "DEC-007"])

s = Seq()
s.do(ev(1.0, cmd=C("left", "unlock"), rear_left_approach_risk=True), X("LOCK", "RELEASE", "NORMAL", "APPROACH_RISK_LEFT", ov=False))
s.do(ev(1.05, cmd=C("left", "unlock"), rear_left_approach_risk=True), X("RELEASE", "RELEASE", "NORMAL", "APPROACH_OVERRIDE", ov=True) + " (0.05 s ≤ 10 s이므로 문서 문언상 override: OI-06 최소 간격 미정의)")
add("ov_fast", ["OEM-FR-003"], "첫 억제 직후 50 ms 만에 같은 명령이 연속 수신(메시지 중복/버튼 유지)",
    "수신 중복이 곧바로 override가 되는 안전 영향 가능성을 확인한다. 문언상 기대값(override)과 다른 구현(디바운스 등)이 있으면 결함 또는 사양 불일치로 판정한다.",
    s, "rear_left_approach_risk=true, unlock left 2회: t=1.00, t=1.05", [WOW, BVA], sug=True, dec=["DEC-007"])

s = Seq()
s.do(ev(1.0, cmd=C("all", "unlock"), rear_left_approach_risk=True, rear_right_approach_risk=True), X("LOCK", "LOCK", "NORMAL", "APPROACH_RISK_LEFT", ov=False))
s.do(ev(6.0, cmd=C("all", "unlock", "voice"), rear_left_approach_risk=True, rear_right_approach_risk=True), X("RELEASE", "RELEASE", "NORMAL", "APPROACH_OVERRIDE", ov=True) + " (all 명령의 재입력: 양 도어 5.000 s 경과 → 둘 다 override; OI-06)")
add("ov_all", ["OEM-FR-003", "OEM-SR-002"], "unlock all 재입력으로 양측 동시 override",
    "all 명령이 한쪽 도어에만 억제 이력을 남기거나 override가 한쪽만 성립하는 결함을 발견한다.",
    s, "양측 접근위험 true, unlock all 2회: t=1.0(avn), t=6.0(voice)", [EP, WOW], sug=True, dec=["DEC-007"])

# ---- FR-005 -----------------------------------------------------------------------------------------------
for key, fld, code, ifid in (("fire", "fire_detected", "FIRE", "OEM-IF-007"), ("overtemp", "overtemperature_detected", "OVERTEMPERATURE", "OEM-IF-007"),
                              ("adult", "adult_present", "ADULT_PRESENT", "OEM-IF-007")):
    s = Seq()
    s.prime(1.0)
    s.do(ev(1.05, **{fld: True}), X("RELEASE", "RELEASE", "NORMAL", code) + " (다음 평가주기에 양측 강제 해제, 입력별 사유)")
    if key == "fire":
        s.do(ev(1.10, cmd=C("all", "lock"), **{fld: True}), X("RELEASE", "RELEASE", "NORMAL", code) + " (lock all 명령보다 우선)")
    add(f"emerg_{key}", ["OEM-FR-005", ifid], f"{fld} 단독 TRUE: 양측 강제 해제({code})",
        f"{fld} 입력의 해제 경로 누락, 사유코드가 다른 입력과 같거나 누락되는 결함, 단독 입력이 한쪽만 해제하는 결함을 발견한다.",
        s, f"{fld}=true 단독(차속 0.0), 직전 LOCK/LOCK" + (", 이후 lock all 명령 추가" if key == "fire" else ""), [EP, REQ], prio="H" if key == "adult" else "M")

s = Seq()
s.prime(1.0)
s.do(ev(1.05, fire_detected=True, overtemperature_detected=True, adult_present=True), X("RELEASE", "RELEASE", "NORMAL", "FIRE") + " (복수 비상 입력 동시: 양측 해제, 사유는 화재>과온>성인 순서: OI-09)")
add("emerg_multi", ["OEM-FR-005"], "화재·과온·성인 동시 TRUE: 양측 해제와 사유 선택",
    "복수 비상 입력에서 해제가 상쇄되거나 사유 기록이 비어 있는 결함을 발견한다.",
    s, "fire/overtemperature/adult 모두 true, 직전 LOCK/LOCK", [WOW, EP], sug=True, dec=["DEC-001"])

s = Seq()
s.prime(1.0)
s.do(ev(1.05, adult_present=True, rear_left_approach_risk=True, rear_right_approach_risk=True, cmd=C("all", "lock")),
     X("RELEASE", "RELEASE", "NORMAL", "ADULT_PRESENT") + " (사용자 확정: 성인 존재가 접근위험보다 우선)")
add("adult_vs_risk", ["OEM-FR-005", "OEM-SR-002"], "성인 존재와 접근위험 동시: 성인 존재 우선 해제",
    "접근위험(순위 4)이 성인 해제(순위 2)를 이기는 우선순위 역전 결함을 발견한다.",
    s, "adult_present=true + 접근위험 L/R=true + lock all, 직전 LOCK/LOCK", [WOW], sug=True, dec=["DEC-001", "사용자 확정 1"])

# ---- FR-006 ISOFIX --------------------------------------------------------------------------------------
s = Seq()
s.do(ev(1.0, isofix_left=True), X("LOCK", "RELEASE", "NORMAL", "ISOFIX_LEFT") + " (해당 측만 LOCK, 반대쪽 유지)")
add("isofix_l", ["OEM-FR-006", "OEM-IF-008"], "isofix_left 단독 TRUE: 좌만 LOCK",
    "ISOFIX가 양측을 잠그거나 좌측 처리가 누락되는 결함을 발견한다.", s, "isofix_left=true, 초기 RELEASE/RELEASE", [EP, REQ])
s = Seq()
s.do(ev(1.0, isofix_right=True), X("RELEASE", "LOCK", "NORMAL", "ISOFIX_RIGHT") + " (우만 LOCK)")
add("isofix_r", ["OEM-FR-006", "OEM-IF-008"], "isofix_right 단독 TRUE: 우만 LOCK",
    "좌우 대칭성 결함(우측 ISOFIX 미처리/좌측으로 오적용)을 발견한다.", s, "isofix_right=true, 초기 RELEASE/RELEASE", [EP, REQ])
s = Seq()
s.do(ev(1.0, cmd=C("left", "lock")), X("LOCK", "RELEASE", "NORMAL", "DRIVER_COMMAND"))
s.do(ev(1.05, isofix_right=True), X("LOCK", "LOCK", "NORMAL", "ISOFIX_RIGHT") + " (반대쪽 좌측은 직전 LOCK 유지)")
add("isofix_keep", ["OEM-FR-006"], "ISOFIX 한쪽 TRUE에서 반대쪽 출력은 직전 값 유지",
    "ISOFIX 처리 시 반대쪽 출력을 RELEASE로 초기화하는 결함을 발견한다('반대쪽 유지' 검증).",
    s, "직전 좌 LOCK/우 RELEASE, isofix_right=true", [EP, REQ])
s = Seq()
s.prime(1.0)
s.do(ev(1.05, cmd=C("all", "unlock"), isofix_left=True), X("LOCK", "RELEASE", "NORMAL", "ISOFIX_LEFT") + " (좌측 해제 명령이 ISOFIX에 의해 무시, 우측은 해제)")
add("isofix_cmd", ["OEM-FR-006", "OEM-FR-001"], "ISOFIX 측은 해제 명령이 와도 LOCK 유지",
    "운전자 해제 명령이 ISOFIX 강제 잠금을 해제하는 결함을 발견한다.",
    s, "isofix_left=true, 명령 unlock all(avn), 직전 LOCK/LOCK", [EP, REQ])
s = Seq()
s.do(ev(1.0, isofix_left=True), X("LOCK", "RELEASE", "NORMAL", "ISOFIX_LEFT"))
s.do(ev(1.05, isofix_left=False), X("LOCK", "RELEASE", "NORMAL", "NO_CHANGE") + " (ISOFIX 해제 후 자동 해제 없음)")
add("isofix_off", ["OEM-FR-006"], "ISOFIX TRUE→FALSE 후 LOCK 자동 해제 없음",
    "ISOFIX 해제 시 잠금이 함께 풀리는(레벨→에지 오구현) 결함을 발견한다.",
    s, "isofix_left true→false", [WOW], sug=True, dec=["DEC-001"])

# ---- FR-007 ---------------------------------------------------------------------------------------------
s = Seq()
s.prime(1.0)
s.do(ev(1.05, ignition_on=False), X("RELEASE", "RELEASE", "OFF", "ignition_off") + " (첫 평가주기: 양측 RELEASE, OFF, ignition_off)")
add("ign_off", ["OEM-FR-007", "OEM-IF-009"], "ignition_on=FALSE 첫 평가주기: 양측 RELEASE, OFF, ignition_off",
    "시동 OFF에서 출력이 유지되거나 한 주기 늦게 해제되는 결함, OFF 상태/이유코드 누락을 발견한다.",
    s, "ignition_on=false(차속 0.0), 직전 LOCK/LOCK", [EP, REQ], prio="H")
s = Seq()
s.do(ev(1.0, cmd=C("all", "lock"), ignition_on=False), X("RELEASE", "RELEASE", "OFF", "ignition_off") + " (lock all 명령은 무시)")
add("ign_cmd", ["OEM-FR-007", "OEM-FR-001"], "시동 OFF 중 lock 명령은 적용되지 않음",
    "시동 OFF 상태에서 운전자 LOCK 명령이 출력을 바꾸는(순위 6<8 역전) 결함을 발견한다.",
    s, "ignition_on=false + 명령 lock all(avn), 초기 RELEASE/RELEASE", [EP], dec=["DEC-001"])
s = Seq()
s.prime(1.0)
s.do(ev(1.05, ignition_on=False, vehicle_speed_kph=50.0), X("RELEASE", "RELEASE", "OFF", "ignition_off") + " (시동 OFF가 자동 잠금보다 우선)")
add("ign_vs_speed", ["OEM-FR-007", "OEM-FR-002"], "시동 OFF와 차속 50 km/h 동시: RELEASE(순위 6 > 7)",
    "자동 잠금(순위 7)이 시동 OFF(순위 6)를 이기는 우선순위 역전 결함을 발견한다.",
    s, "ignition_on=false + 차속 50.0, 직전 LOCK/LOCK", [WOW], sug=True, dec=["DEC-001"])
s = Seq()
s.do(ev(1.0, ignition_on=False, isofix_left=True), X("LOCK", "RELEASE", "OFF", "ISOFIX_LEFT") + " (사용자 확정: ISOFIX 우선. 사양서 FR-007 문언(양측 RELEASE)과 상충: OI-05)")
add("ign_vs_isofix", ["OEM-FR-007", "OEM-FR-006"], "시동 OFF와 ISOFIX 좌 동시: 좌 LOCK 유지, 우 RELEASE, OFF",
    "ISOFIX(순위 5)와 시동 OFF(순위 6)의 우선순위 역전을 발견하고 사양서 문언과의 상충을 가시화한다.",
    s, "ignition_on=false + isofix_left=true, 초기 RELEASE/RELEASE", [WOW], sug=True, dec=["DEC-001", "사용자 확정 2"])
s = Seq()
s.prime(1.0)
s.do(ev(1.05, ignition_on=False), X("RELEASE", "RELEASE", "OFF", "ignition_off"))
s.do(ev(1.10, ignition_on=True), X("RELEASE", "RELEASE", "NORMAL", "NO_CHANGE") + " (시동 재ON: 이전 LOCK 복원 없음)")
s.do(ev(1.15, cmd=C("all", "lock", "physical_button")), X("LOCK", "LOCK", "NORMAL", "DRIVER_COMMAND"))
add("ign_cycle", ["OEM-FR-007"], "시동 ON→OFF→ON 사이클: 재ON 시 이전 LOCK이 복원되지 않음",
    "시동 OFF 중 출력을 별도 기억해 재ON 시 이전 LOCK을 되살리는 결함, OFF 상태가 래치되는 결함을 발견한다.",
    s, "직전 LOCK/LOCK, ignition_on true→false→true(50 ms 간격), 이후 lock all(physical_button)", [WOW, EP])
s = Seq()
s.do(ev(1.0, cmd=C("left", "lock"), ignition_on=False), X("RELEASE", "RELEASE", "OFF", "ignition_off"))
s.do(ev(1.05, cmd=C("all", "lock", "voice"), ignition_on=False), X("RELEASE", "RELEASE", "OFF", "ignition_off"))
s.do(ev(1.10, cmd=C("right", "lock", "mobile_app"), ignition_on=False), X("RELEASE", "RELEASE", "OFF", "ignition_off"))
s.do(ev(1.15, cmd=C("all", "lock", "physical_button")), X("LOCK", "LOCK", "NORMAL", "DRIVER_COMMAND") + " (시동 ON 첫 주기부터 명령 적용)")
add("ign_burst", ["OEM-FR-007", "OEM-FR-001"], "시동 OFF 직후 연속 명령(3개 source)은 모두 무시되고 재ON 첫 주기부터 적용",
    "OFF 구간의 명령이 버퍼링되어 재ON 때 적용되는 결함, 재ON 첫 주기의 명령이 누락되는 결함을 발견한다.",
    s, "ignition_on=false 3주기 동안 lock left(avn), lock all(voice), lock right(mobile_app), 이후 ignition_on=true + lock all(physical_button)", [WOW])
s = Seq()
s.do(ev(1.0, vehicle_speed_kph=50.0), X("LOCK", "LOCK", "NORMAL", "AUTO_LOCK_SPEED"))
s.do("GET /events 로 이벤트 1건 이상 존재 확인 후, 서버 프로세스를 강제 종료(kill -9 / taskkill /F)하고 같은 명령으로 재기동(전원 순단 모사)", "이벤트 1건 이상(재기동 전 확인)")
s.do("GET /status", "lock_left=RELEASE, lock_right=RELEASE, state=OFF (초기 상태로 복귀, 이전 LOCK 복원 없음)")
s.do("GET /events", "빈 배열(0건)")
s.do(ev(1.0, vehicle_speed_kph=50.0, ignition_on=True), X("LOCK", "LOCK", "NORMAL", "AUTO_LOCK_SPEED") + " (재기동 후 첫 평가주기에 정상 동작)")
add("power_cycle", ["OEM-FR-007", "OEM-NFR-002"], "주행 중 전원 순단(프로세스 강제 종료) 후 재기동: 초기 상태 복귀와 첫 주기 정상 동작",
    "재기동 후 이전 출력/이벤트가 남는 결함, 초기화 직후 첫 입력이 무시되는 결함을 발견한다.",
    s, "차속 50.0으로 LOCK 후 프로세스 강제 종료·재기동, 동일 입력 재전송", [WOW])

# ---- FR-004 / IF-005 / IF-006 -------------------------------------------------------------------------
s = Seq()
s.do("GET /status", "HTTP 200, 응답 JSON에 키 lock_left, lock_right, state, input_validity, reason_code, priority_reason, override가 모두 존재. lock_left=RELEASE, lock_right=RELEASE, state=OFF (reason_code 값은 초기값 미정: OI-12로 키 존재만 판정)")
s.do("GET /events", "HTTP 200, 이벤트 0건")
add("status_initial", ["OEM-FR-004", "OEM-IF-005", "OEM-IF-006"], "평가 이전 상태조회: 필수 항목 존재와 초기값",
    "초기 상태에서 상태조회가 500/빈 응답이 되는 결함, 필수 항목(출력·state·입력유효성·이유코드) 누락, 초기 출력이 LOCK인 결함을 발견한다.",
    s, "GET /status, GET /events (평가 입력 없음)", [EP, REQ])
s = Seq()
s.do(ev(1.0, rear_left_approach_risk=True), X("LOCK", "RELEASE", "NORMAL", "APPROACH_RISK_LEFT") + ". GET /status의 lock_left, lock_right, state, reason_code가 이 응답과 일치하고 input_validity가 존재")
s.do(ev(1.05, crash_status="CONFIRMED"), X("RELEASE", "RELEASE", "NORMAL", "CRASH_CONFIRMED") + ". GET /status의 reason_code가 CRASH_CONFIRMED로 갱신(이전 사유 캐시 아님)")
s.do("GET /events", "마지막 이벤트의 lock_left=RELEASE, lock_right=RELEASE, reason_code=CRASH_CONFIRMED가 GET /status와 같음")
add("status_after", ["OEM-FR-004", "OEM-IF-006"], "결정 후 상태조회가 최신 결정과 일치하고 이력과도 일치",
    "상태조회가 직전 결정의 값을 보여주는 지연/캐시 결함, 상태조회와 이벤트 이력의 불일치를 발견한다.",
    s, "rear_left_approach_risk=true 후 crash_status=CONFIRMED", [EP, REQ])

s = Seq()
s.do(ev(1.0, rear_left_approach_risk=True), "priority_reason=APPROACH_RISK_LEFT, reason_code=APPROACH_RISK_LEFT (두 값 동일)")
s.do(ev(1.05, crash_status="CONFIRMED"), "priority_reason=CRASH_CONFIRMED, reason_code=CRASH_CONFIRMED (두 값 동일)")
s.do(ev(1.10, cmd=C("all", "lock")), "priority_reason=DRIVER_COMMAND, reason_code=DRIVER_COMMAND (두 값 동일)")
add("if006_map", ["OEM-IF-006"], "priority_reason이 reason_code로도 동일하게 매핑",
    "표시 데이터에서 priority_reason과 reason_code가 서로 다른 값/누락으로 노출되는 결함을 발견한다.",
    s, "접근위험(좌), 충돌 CONFIRMED, 명령 lock all 순차", [EP])

s = Seq()
s.do("GET /status", "state=OFF (초기)")
s.do(ev(1.0), "state=NORMAL")
s.do(ev(1.05, sensor_fault=True), "state=FAULT")
s.do(ev(1.10, sensor_fault=False), "state=NORMAL")
s.do(ev(1.15, ignition_on=False), "state=OFF")
s.do(ev(1.45, src=1.20), "state=DEGRADED (경과 250 ms), GET /status의 input_validity 값 중 하나 이상이 STALE (OI-11)")
s.do(ev(1.50), "state=NORMAL, input_validity의 모든 값이 VALID")
s.do(ev(1.55, vehicle_speed_kph=-0.1), "HTTP 422. GET /status: state=NORMAL(직전 유지), reason_code=INPUT_INVALID, input_validity.speed=INVALID (그룹명 speed: 상세설계 근거, OI-11)")
add("if006_states", ["OEM-IF-006", "OEM-FR-004"], "state 열거값 OFF/NORMAL/DEGRADED/FAULT와 input_validity(VALID/STALE/INVALID) 노출",
    "state 문자열 오표기, 특정 state가 표시되지 않는 결함, 입력 유효성이 stale/무효 상황을 반영하지 않는 결함을 발견한다.",
    s, "초기 → 정상 → sensor_fault → 복귀 → ignition off → 경과 250 ms → 정상 → 차속 -0.1", [EP, WOW], dec=["DEC-004"])

s = Seq()
s.do("GET /status", "lock_left, lock_right 값이 각각 문자열 LOCK 또는 RELEASE (대소문자 일치, null·그 외 값 없음)")
s.do(ev(1.0, cmd=C("all", "lock")), "LOCK/LOCK")
s.do(ev(1.05, cmd=C("all", "unlock")), "RELEASE/RELEASE")
s.do(f"POST /tick {{\"timestamp_s\":1.40}}", "DEGRADED 상태에서도 lock_left, lock_right는 LOCK 또는 RELEASE (null 아님)")
s.do(ev(1.45, sensor_fault=True), "FAULT 상태에서도 두 값이 LOCK 또는 RELEASE")
s.do(ev(1.50, vehicle_speed_kph=300.1), "HTTP 422 후 GET /status의 두 값이 LOCK 또는 RELEASE (직전 값)")
add("if005_domain", ["OEM-IF-005"], "출력 도메인: 모든 상태에서 lock_left/lock_right가 LOCK 또는 RELEASE",
    "DEGRADED/FAULT/거절 시 출력이 null·UNKNOWN 등 도메인 밖 값이 되는 결함을 발견한다.",
    s, "초기, lock all, unlock all, 경과 400 ms tick, sensor_fault, 차속 300.1 순차", [EP])

s = Seq()
s.do("GET / (헤더 Accept: text/html)", "HTTP 200, Content-Type이 text/html, 본문이 비어 있지 않음")
add("ui_root", ["OEM-FR-004"], "Web 시뮬레이터 화면 제공",
    "표시 인터페이스(화면)가 제공되지 않거나 라우트가 누락되는 결함을 발견한다.",
    s, "GET /", [REQ], sug=True, dec=["DEC-010"], prio="L")

# ---- PICT B/C (우선순위 조합) ------------------------------------------------------------------------
EMAP = {"FIRE": ("fire_detected", "FIRE"), "OVERTEMP": ("overtemperature_detected", "OVERTEMPERATURE"), "ADULT": ("adult_present", "ADULT_PRESENT")}
CMAP = {"NONE": None, "L_UNLOCK": ("left", "unlock"), "R_LOCK": ("right", "lock"), "ALL_UNLOCK": ("all", "unlock"), "ALL_LOCK": ("all", "lock")}
RANK = {"APPROACH_RISK_LEFT": 4, "APPROACH_RISK_RIGHT": 4, "ISOFIX_LEFT": 5, "ISOFIX_RIGHT": 5, "ignition_off": 6,
        "AUTO_LOCK_SPEED": 7, "RELEASE_DENIED_MOVING": 7, "DRIVER_COMMAND": 8, "NO_CHANGE": 9}


def oracle(r):
    """00_decisions.md 우선순위표를 그대로 옮긴 기대값 계산. 반환: (left, right, state|None, reason|None)"""
    pl = pr = r["Prior"]
    ign_on = r["Ignition"] == "ON"
    fault = r.get("Fault", "F") == "T"
    crash = r.get("Crash", "NONE")
    emerg = r.get("Emergency", "NONE")
    # 상태는 입력만으로 DEGRADED>FAULT>OFF>NORMAL (상세설계 7절). 전역 규칙(충돌/비상/PENDING)과 FAULT/OFF가 겹치면 OI-04로 판정 제외
    if crash == "CONFIRMED" or emerg != "NONE":
        state = "NORMAL" if (ign_on and not fault) else None
        reason = "CRASH_CONFIRMED" if crash == "CONFIRMED" else EMAP[emerg][1]
        return "RELEASE", "RELEASE", state, reason
    if fault:
        return pl, pr, "FAULT", "SENSOR_FAULT"
    if crash == "PENDING":
        return pl, pr, ("NORMAL" if ign_on else None), "CRASH_PENDING"
    cmd = CMAP[r["Command"]]
    speed = 1.0 if r["Speed"] == "STOP" else 50.0
    res = {}
    for s, prior, risk, iso in (("left", pl, r["RiskL"] == "T", r["IsofixL"] == "T"),
                                ("right", pr, r["RiskR"] == "T", r["IsofixR"] == "T")):
        targeted = cmd is not None and cmd[0] in (s, "all")
        if risk:
            res[s] = ("LOCK", "APPROACH_RISK_" + s.upper())
        elif iso:
            res[s] = ("LOCK", "ISOFIX_" + s.upper())
        elif not ign_on:
            res[s] = ("RELEASE", "ignition_off")
        elif speed >= 3.0:
            res[s] = ("LOCK", "RELEASE_DENIED_MOVING" if targeted and cmd[1] == "unlock" else "AUTO_LOCK_SPEED")
        elif targeted:
            res[s] = ("LOCK" if cmd[1] == "lock" else "RELEASE", "DRIVER_COMMAND")
        else:
            res[s] = (prior, "NO_CHANGE")
    rl, rr = res["left"][1], res["right"][1]
    if RANK[rl] == RANK[rr] and rl != rr and RANK[rl] == 7:
        reason = None  # 순위 7의 서로 다른 사유(AUTO_LOCK vs RELEASE_DENIED): 선택 규칙 미정 (OI-09)
    else:
        reason = rl if RANK[rl] <= RANK[rr] else rr
    return res["left"][0], res["right"][0], ("NORMAL" if ign_on else "OFF"), reason


def pict_tc(prefix, idx, r, model_file, order):
    s = Seq()
    chg = {"vehicle_speed_kph": 1.0 if r["Speed"] == "STOP" else 50.0}
    if r.get("Crash", "NONE") != "NONE":
        chg["crash_status"] = r["Crash"]
    if r.get("Emergency", "NONE") != "NONE":
        chg[EMAP[r["Emergency"]][0]] = True
    if r.get("Fault", "F") == "T":
        chg["sensor_fault"] = True
    if r["RiskL"] == "T":
        chg["rear_left_approach_risk"] = True
    if r["RiskR"] == "T":
        chg["rear_right_approach_risk"] = True
    if r["IsofixL"] == "T":
        chg["isofix_left"] = True
    if r["IsofixR"] == "T":
        chg["isofix_right"] = True
    if r["Ignition"] == "OFF":
        chg["ignition_on"] = False
    cmd = CMAP[r["Command"]]
    cdict = C(cmd[0], cmd[1]) if cmd else None
    l, rr, state, reason = oracle(r)
    exp = f"HTTP 200, lock_left={l}, lock_right={rr}, " + (f"state={state}, " if state else "state 판정 제외(OI-04), ") + \
          (f"reason_code={reason}, " if reason else "reason_code 판정 제외(OI-09), ") + "override=false"
    t = 1.0
    if r["Prior"] == "LOCK":
        s.prime(1.0)
        t = 1.05
    s.do(ev(t, cmd=cdict, **chg), exp)
    summ = ", ".join(f"{k}={v}" for k, v in r.items())
    basis = ["OEM-SR-001", "OEM-SR-002", "OEM-SR-004", "OEM-FR-001", "OEM-FR-002", "OEM-FR-005", "OEM-FR-006", "OEM-FR-007"]
    key = f"{prefix}_{idx}"
    add(key, basis, f"우선순위 조합 {prefix[-1].upper()}-{idx}: {summ}",
        "복수 조건이 동시에 성립할 때 우선순위표(DEC-001)와 다른 결과를 내는 결함(상위 조건이 하위 조건에 밀림, 측별 독립 위반, 유지 규칙 오적용)을 발견한다.",
        s, f"{summ}; 명령 source=avn; 차속 STOP=1.0 / MOVE=50.0 km/h; " + ("직전 LOCK/LOCK(프라이밍)" if r["Prior"] == "LOCK" else "초기 RELEASE/RELEASE"),
        [PW, EP], sug=True, dec=["DEC-001"],
        pre=PRE_FRESH + f" (PICT 모델 {model_file} order={order} 행 {idx}. 기대값은 00_decisions.md 우선순위표로 계산, reason_code 선택은 상세설계 _pick_priority_reason 근거)")


def read_tsv(name):
    lines = (HERE / name).read_text(encoding="utf-8").strip().splitlines()
    hdr = lines[0].split("\t")
    return [dict(zip(hdr, l.split("\t"))) for l in lines[1:]]


rowsB = read_tsv("pict_priority_output.tsv")
rowsC = read_tsv("pict_side_output.tsv")
for i, r in enumerate(rowsB, 1):
    pict_tc("pictB", i, r, "pict_priority_model.txt", 2)
for i, r in enumerate(rowsC, 1):
    r = dict(r)
    pict_tc("pictC", i, r, "pict_side_model.txt", 3)

# =================================================================== 비기능 TC
V = [
    (1.00, None, dict(vehicle_speed_kph=5.0)),
    (1.05, C("all", "unlock"), {}),
    (1.10, C("left", "unlock", "voice"), dict(rear_left_approach_risk=True)),
    (1.15, C("left", "unlock", "voice"), dict(rear_left_approach_risk=True)),
    (1.20, None, dict(isofix_right=True)),
    (1.25, None, dict(crash_status="PENDING")),
    (1.30, None, dict(crash_status="CONFIRMED")),
    (1.35, C("all", "lock", "mobile_app"), dict(sensor_fault=True)),
    (1.40, None, dict(ignition_on=False)),
    (1.45, None, dict(adult_present=True)),
    (1.50, None, dict(fire_detected=True)),
]
VEC_TEXT = []
for i, (t, c, chg) in enumerate(V, 1):
    VEC_TEXT.append(f"v{i}: " + ev(t, cmd=c, **chg).replace("POST /evaluate ", ""))
VEC_TEXT.append("v12: " + ev(1.80, src=1.50).replace("POST /evaluate ", "") + " (경과 300 ms)")
VEC_TEXT.append('v13: POST /tick {"timestamp_s":2.0}')
VEC_TEXT.append("v14: " + ev(2.05, vehicle_speed_kph=-0.1).replace("POST /evaluate ", "") + " (422 거절)")
VEC_TEXT.append("v15: " + ev(2.10, cmd=C("all", "unlock", "physical_button"), vehicle_speed_kph=3.0).replace("POST /evaluate ", ""))

s = Seq()
s.do("고정 벡터 V(타임스탬프는 모두 요청에 명시, 서버 시계 비사용)를 확정한다:\n   " + "\n   ".join(VEC_TEXT))
s.do("i=1..1000 반복: (a) 서버 신규 기동 (b) V를 v1~v15 순서로 호출하며 각 응답의 HTTP 상태코드와 본문을 기록 (c) GET /status, GET /events 본문 기록 "
     "(d) 위 기록 전체를 키 정렬·공백 없는 canonical JSON으로 직렬화해 SHA-256 H_i 계산 (e) 서버 종료")
s.do("H_1..H_1000을 비교한다", "1,000개 해시가 모두 동일(서로 다른 값 1개). v14는 매 회 HTTP 422, 나머지는 HTTP 200. HTTP 5xx 0건, 응답 시간 초과·누락 0건")
add("nfr1_replay", ["OEM-NFR-001"], "고정 벡터 1,000회 재생 결과 해시 동일",
    "시계·난수·해시 순서(set/dict)·전역 상태 누수로 같은 입력의 결과가 달라지는 비결정성을 발견한다.",
    s, "벡터 V 15개 요청(우선순위·접근위험·충돌·고장·시동·stale·거절 포함), 1,000회, 매회 서버 신규 기동", [REQ, WOW], cat="nonfunctional", prio="H",
    pre="자동화 스크립트(요청 전송, canonical JSON, SHA-256)와 서버 기동/종료 제어가 가능한 환경. " + BASEDEF)

s = Seq()
s.do("벡터 V는 nfr1_replay와 같다. 기준 해시 H_ref를 1회 재생으로 구한다(서버 신규 기동)")
s.do("변형 A: 요청 간 대기 0 ms / 100 ms / 500 ms로 각 20회 재생(매회 서버 신규 기동)", "모든 회차 해시 = H_ref (실제 경과 시간·벽시계 비의존)")
s.do("변형 B: 각 요청 본문의 JSON 키 순서를 역순으로 하고 공백을 삽입해 20회 재생(매회 서버 신규 기동)", "모든 회차 해시 = H_ref (키 순서 비의존)")
s.do("변형 C: 서버를 기동하고 2초 대기한 뒤 재생, 또 다른 서버를 동시에 기동한 상태에서 재생(각 20회)", "모든 회차 해시 = H_ref (기동 시각·다중 프로세스 비의존)")
add("nfr1_variants", ["OEM-NFR-001"], "벽시계·JSON 키 순서·기동 시각 변형에도 결과 해시 동일",
    "판단 로직이 벽시계, 필드 순서, 프로세스 기동 시각에 의존하는 결함을 발견한다(시계 주입 위반).",
    s, "벡터 V, 변형 A/B/C 합계 180회", [WOW, ERR], cat="nonfunctional",
    pre="nfr1_replay와 같은 자동화 환경. " + BASEDEF)

# 이벤트 100건 -----------------------------------------------------------------------------------------
s = Seq()
s.do("i=1..101에 대해 POST /evaluate snapshot=BASE+{timestamp_s:T_i, source_timestamp_s:T_i, vehicle_speed_kph: (i가 홀수면 0.0, 짝수면 5.0)}, command=null 을 보낸다. "
     "T_i = 1.00 + 0.05*(i-1)를 소수 둘째 자리 십진 문자열로 전송(예: T_1=1.00, T_100=5.95, T_101=6.00). 모든 응답 HTTP 200. i=99, 100, 101 직후 각각 GET /events 를 호출한다")
s.exp.append("[i=99 직후] 이벤트 99건, 첫 레코드 timestamp_s=1.00, 마지막 5.90")
s.exp.append("[i=100 직후] 이벤트 100건, 첫 레코드 timestamp_s=1.00, 마지막 5.95")
s.exp.append("[i=101 직후] 이벤트 정확히 100건, 첫 레코드 timestamp_s=1.05, 마지막 6.00 (T=1.00 레코드 탈락), timestamp_s가 1.05부터 0.05(±0.0005) 간격으로 오름차순(오래된 것부터, OI-10)")
s.do("i=101 직후 이벤트 100건의 event_id를 검사한다", "event_id가 모두 서로 다르고 엄격 증가, i=100 직후의 마지막 event_id보다 i=101의 마지막 event_id가 큼(링 버퍼 회전 후에도 ID 비초기화)")
add("nfr2_100", ["OEM-NFR-002"], "이벤트 99/100/101건 경계: 최신 100건만 순서대로 보존",
    "저장 한도 오류(99 또는 101건 보존), 오래된 레코드가 아닌 최신 레코드를 버리는 결함, 정렬 오류, ID 중복·초기화를 발견한다.",
    s, "평가 101회(50 ms 간격), 조회 시점 i=99/100/101", [BVA, REQ], cat="nonfunctional", prio="H")

s = Seq()
s.do("서버 신규 기동 후 서로 다른 결정 12건을 만든다: " + "; ".join([
    ev(1.00, cmd=C("all", "lock", "physical_button"), vehicle_speed_kph=0.0),
    ev(1.05, cmd=C("left", "unlock", "voice"), rear_left_approach_risk=True),
    ev(1.10, cmd=C("right", "lock", "mobile_app"), adult_present=True),
    ev(1.15, crash_status="PENDING"),
    ev(1.20, crash_status="CONFIRMED"),
    ev(1.25, sensor_fault=True, cmd=C("all", "unlock", "avn")),
    ev(1.30, ignition_on=False),
    ev(1.35, isofix_left=True),
    ev(1.40, fire_detected=True),
    ev(1.45, overtemperature_detected=True),
    ev(1.80, src=1.45),
    ev(1.85, vehicle_speed_kph=50.0)]).replace("POST /evaluate ", ""))
s.do("GET /events 를 호출해 모든 레코드의 키 집합을 검사한다",
     "모든 레코드의 키 집합이 정확히 {event_id, timestamp_s, state, lock_left, lock_right, reason_code, priority_reason, input_validity}와 같음(SWR-011의 허용 필드 목록 기준, 추가·누락 0)")
s.do("GET /events 응답 본문 전체를 소문자 문자열로 변환해 금지 토큰을 검색한다: voice, mobile_app, physical_button, avn, audio, video, image, camera, driver_id, user_id, vin, phone, email, gps, face, name",
     "금지 토큰 일치 0건 (명령 source·side·action 값이 이벤트에 저장되지 않음, 영상·음성·개인 식별 필드 없음)")
s.do("GET /status 응답 본문에도 같은 금지 토큰 검색", "금지 토큰 일치 0건")
add("nfr2_fields", ["OEM-NFR-002"], "이벤트 레코드는 허용 8개 필드만 포함하고 금지 정보가 없음",
    "명령 원문(source)·성인존재 원본 신호·부가 식별 필드가 이벤트에 누출되는 결함, 허용 필드 누락을 발견한다.",
    s, "12개 결정(4개 source, 접근위험, 성인, 충돌, 고장, 시동 OFF, ISOFIX, 화재, 과온, stale, 이동) 후 GET /events", [REQ, ERR], cat="nonfunctional", prio="H",
    dec=None, pre=PRE_FRESH + " 허용 필드는 SWR-011(event_id, timestamp_s, state, lock_left, lock_right, reason_code, priority_reason, input_validity).")

s = Seq()
s.do("POST /evaluate 를 5회 보낸다(t=1.00~1.20, 차속 5.0)", "모두 HTTP 200")
s.do("GET /events", "이벤트 5건 이상(재기동 전 데이터 존재)")
s.do("서버를 정상 종료(Ctrl+C)하고 같은 명령으로 재기동한다. 작업 디렉터리·임시 폴더에서 이벤트 저장 파일(*.db, *.json, *.log, *.sqlite 등 신규 생성 파일)이 없는지 확인한다", "신규 생성된 이벤트 영속 파일 0개")
s.do("GET /events", "HTTP 200, 이벤트 0건")
s.do("GET /status", "lock_left=RELEASE, lock_right=RELEASE, state=OFF")
add("nfr2_volatile", ["OEM-NFR-002"], "프로세스 재기동 후 이벤트 비어 있음(비영속)",
    "이벤트가 파일/DB에 저장되어 재기동 후에도 남는 결함(메모리 내 저장 위반)을 발견한다.",
    s, "5건 결정 후 서버 재기동", [REQ, EP], cat="nonfunctional")

# 응답/타이밍 ---------------------------------------------------------------------------------------------
s = Seq()
s.do("i=1..100 반복: (a) POST /evaluate snapshot=BASE+{timestamp_s:t_i, source_timestamp_s:t_i, vehicle_speed_kph:5.0} 로 LOCK/LOCK 프라이밍 (b) 직후 "
     "POST /evaluate snapshot=BASE+{timestamp_s:t_i+0.05, source_timestamp_s:t_i+0.05, crash_status:\"CONFIRMED\", vehicle_speed_kph:5.0}, command={\"side\":\"all\",\"action\":\"lock\",\"source\":\"avn\"} 를 전송하고 "
     "요청 전송 직전~응답 수신 완료까지의 벽시계 시간 L_i(ms, 시간 해상도 1 ms 이하의 monotonic 시계)를 기록. t_i = 1.00 + 0.10*(i-1)")
s.do("L_1..L_100 과 (b)의 응답을 판정한다",
     "100/100회 응답이 lock_left=RELEASE, lock_right=RELEASE, reason_code=CRASH_CONFIRMED (같은 평가주기 = 논리 지연 0주기 ≤ 50 ms). 100회 모두 L_i ≤ 300 ms (사양 한도, 최댓값 L_max 보고)")
add("nfr_crash_latency", ["OEM-SR-001"], "충돌 CONFIRMED 응답시간: 같은 주기 해제와 300 ms 이내",
    "충돌 처리가 폴링/큐 지연으로 300 ms를 넘기거나 다음 주기로 밀리는 결함을 발견한다.",
    s, "충돌 CONFIRMED 요청 100회, 측정: HTTP 왕복 시간 L_i와 응답 출력값", [BVA, REQ], cat="nonfunctional", prio="H", dec=["DEC-002"],
    pre="자동화 클라이언트(1 ms 이하 해상도 monotonic 시계)와 로컬 서버 기동 환경(루프백 접속, 다른 부하 없음). " + BASEDEF)

s = Seq()
s.do(ev(10.0, vehicle_speed_kph=5.0) + "  (프라이밍, LOCK/LOCK)", X("LOCK", "LOCK", "NORMAL", "AUTO_LOCK_SPEED"))
s.do("논리 지연 측정: POST /tick timestamp_s=10.05, 10.10, 10.15, 10.20, 10.25, 10.30 을 순서대로 호출한다",
     "10.05~10.20 응답 state=NORMAL, 10.25 와 10.30 응답 state=DEGRADED, reason_code=INPUT_STALE, lock_left=LOCK, lock_right=LOCK. "
     "최초 DEGRADED 응답 시각 10.25 ≤ (10.00+0.200)+0.100 = 10.30 (200 ms 초과 후 100 ms 이내, 이 시험의 시각 해상도 50 ms)")
s.do("벽시계 측정: 프라이밍(t=10.0)과 POST /tick 10.25를 한 쌍으로 100회 반복(쌍마다 t를 10.0씩 증가)하며 /tick 호출 왕복 시간 M_i를 기록", "100/100회 응답 state=DEGRADED, M_i ≤ 100 ms (사양 한도, 최댓값 M_max 보고)")
add("nfr_degraded_latency", ["OEM-SR-003"], "DEGRADED 전이 지연: 200 ms 초과 후 100 ms 이내",
    "stale 감지가 주기 의존으로 지연되어 100 ms 한도를 넘기거나 200 ms 이전에 DEGRADED가 되는 결함을 발견한다.",
    s, "프라이밍 후 /tick 6회(논리 시각), 프라이밍+/tick 100쌍(벽시계)", [BVA, REQ], cat="nonfunctional", prio="H", dec=["DEC-002", "DEC-007"],
    pre="자동화 클라이언트와 로컬 서버 기동 환경. " + BASEDEF)

s = Seq()
s.do("클라이언트가 monotonic 시계로 50 ms마다 1회, 60 s 동안 총 1,200회 POST /evaluate 를 전송한다. 요청 본문의 timestamp_s=source_timestamp_s=경과 시간(s, 소수 셋째 자리), 차속 0.0, 명령 없음. 각 요청 간 실제 송신 간격 J_i와 응답 시간 R_i를 기록")
s.do("결과 집계", "1,200/1,200회 HTTP 200 및 state=NORMAL(DEGRADED 0회). R_i ≤ 100 ms 100% (최댓값 R_max 보고), 송신 간격 J_i가 목표 50 ms에서 100 ms를 넘은 경우 0건(초과 시 클라이언트 측 지연으로 판정해 재측정)")
add("nfr_cycle_realtime", ["OEM-SR-001", "OEM-SR-003"], "50 ms 주기 실시간 입력 60 s: 응답 지연 100 ms 이내, DEGRADED 오검출 없음",
    "50 ms 주기 부하에서 처리 지연이 누적되어 100 ms를 넘기거나, 정상 입력이 stale로 오판되는 결함을 발견한다.",
    s, "50 ms 간격 1,200회 평가(60 s)", [REQ, WOW], cat="nonfunctional", sug=True, dec=["DEC-002"],
    pre="자동화 클라이언트(monotonic 시계)와 로컬 서버 기동 환경. " + BASEDEF)

# 신뢰성 ---------------------------------------------------------------------------------------------------
bad_list = [
    ('vehicle_speed_kph=-0.1', dict(vehicle_speed_kph=-0.1), ()),
    ('vehicle_speed_kph=300.1', dict(vehicle_speed_kph=300.1), ()),
    ('vehicle_speed_kph="fast"', dict(vehicle_speed_kph="fast"), ()),
    ('vehicle_speed_kph 누락', {}, ("vehicle_speed_kph",)),
    ('gear="X"', dict(gear="X"), ()),
    ('gear 누락', {}, ("gear",)),
    ('crash_status="UNKNOWN"', dict(crash_status="UNKNOWN"), ()),
    ('crash_status 누락', {}, ("crash_status",)),
    ('rear_left_approach_risk="true"', dict(rear_left_approach_risk="true"), ()),
    ('fire_detected 누락', {}, ("fire_detected",)),
    ('isofix_left 누락', {}, ("isofix_left",)),
    ('ignition_on 누락', {}, ("ignition_on",)),
    ('sensor_fault="1"', dict(sensor_fault="1"), ()),
    ('source_timestamp_s 누락', {}, ("source_timestamp_s",)),
    ('source_timestamp_s="noon"', dict(source_timestamp_s="noon"), ()),
]
s = Seq()
n = 0
t = 1.0
for k, (desc, chg, drop) in enumerate(bad_list, 1):
    # 홀수 k: LOCK 프라이밍, 짝수 k: unlock 후 RELEASE
    if k % 2 == 1:
        s.do(ev(round(t, 3), vehicle_speed_kph=5.0), X("LOCK", "LOCK", "NORMAL", "AUTO_LOCK_SPEED") + f" (유효 주기 {k})")
        exp_l = "LOCK"
    else:
        s.do(ev(round(t, 3), cmd=C("all", "unlock")), X("RELEASE", "RELEASE", "NORMAL", "DRIVER_COMMAND") + f" (유효 주기 {k})")
        exp_l = "RELEASE"
    t += 0.05
    s.do(ev(round(t, 3), cmd=C("all", "lock" if exp_l == "RELEASE" else "unlock"), drop=drop, **chg) + f"   [무효: {desc}]",
         f"HTTP 422, errors 비어 있지 않음. GET /status: lock_left={exp_l}, lock_right={exp_l}, state=NORMAL, reason_code=INPUT_INVALID (직전 유지)")
    t += 0.05
s.do(ev(round(t, 3), cmd=C("all", "unlock")), X("RELEASE", "RELEASE", "NORMAL", "DRIVER_COMMAND") + " (15회 거절 뒤 마지막 유효 주기: 정상 복구)")
s.do("GET /status, GET /events, GET / 를 호출한다", "세 요청 모두 HTTP 200 (서버 프로세스 생존, 5xx 응답 총 0건)")
add("nfr_reliab_invalid", ["OEM-SR-003", "OEM-IF-001", "OEM-IF-002", "OEM-IF-003", "OEM-IF-004", "OEM-IF-007", "OEM-IF-008", "OEM-IF-009"],
    "무효 입력 15종 연속 주입 중 서버 생존과 유효 입력 즉시 복구",
    "무효 입력 처리 중 예외로 상태가 오염되거나(직전 출력 손상), 서버가 중단·5xx를 내거나, 거절 후 다음 유효 주기가 영향을 받는 결함을 발견한다.",
    s, "유효 주기와 무효 주기(15종)를 교대 전송(50 ms 간격), 유효 주기는 LOCK 프라이밍/해제 명령 교대", [ERR, EP, WOW], cat="nonfunctional", prio="H")

# 장시간 -----------------------------------------------------------------------------------------------------
PERIOD = [
    (dict(vehicle_speed_kph=5.0), None, ("LOCK", "LOCK", "NORMAL", "AUTO_LOCK_SPEED")),
    ({}, C("all", "unlock"), ("RELEASE", "RELEASE", "NORMAL", "DRIVER_COMMAND")),
    (dict(isofix_left=True), None, ("LOCK", "RELEASE", "NORMAL", "ISOFIX_LEFT")),
    (dict(fire_detected=True), None, ("RELEASE", "RELEASE", "NORMAL", "FIRE")),
    (dict(crash_status="CONFIRMED"), None, ("RELEASE", "RELEASE", "NORMAL", "CRASH_CONFIRMED")),
    (dict(rear_left_approach_risk=True, rear_right_approach_risk=True), None, ("LOCK", "LOCK", "NORMAL", "APPROACH_RISK_LEFT")),
    (dict(ignition_on=False), None, ("RELEASE", "RELEASE", "OFF", "ignition_off")),
    ({}, C("all", "lock"), ("LOCK", "LOCK", "NORMAL", "DRIVER_COMMAND")),
]
s = Seq()
s.do("8주기 패턴 P를 정의한다(주기 내 각 단계는 BASE에서 명시 항목만 변경, 이전 단계의 변경은 이월하지 않음). 단계별 기대:\n   " + "\n   ".join(
    f"p{i + 1}: snapshot=BASE+{{timestamp_s=source_timestamp_s=T" + "".join(f',"{k}":{J(v)}' for k, v in chg.items()) + "}, command=" +
    ("null" if c is None else J(c)) + " → " + X(*e)
    for i, (chg, c, e) in enumerate(PERIOD)))
s.do("패턴 P를 2,500회 연속 반복해 총 20,000회 POST /evaluate 를 50 ms 간격 논리 시각(T=1.00에서 시작, 0.05씩 증가, 소수 둘째 자리 십진 문자열)으로 전송한다. 1,000회마다 GET /events 길이와 프로세스 메모리(RSS)를 기록한다")
s.do("결과 집계", "20,000/20,000회 응답이 위 패턴 기대와 일치(HTTP 5xx 0건, 이상 응답 0건). GET /events 길이가 매 조회 100. 마지막 1,000회 구간의 RSS가 첫 1,000회 구간 대비 증가율 10% 이내(자원 한도 사양 없음: 증가율은 시험 판정 기준으로 제안, OI-15)")
add("nfr_soak", ["OEM-NFR-002", "OEM-NFR-001"], "20,000주기 장시간 반복: 판정 불변, 이벤트 100건 상한 유지, 메모리 비누수",
    "카운터·타임스탬프 누적 오류, 이벤트 버퍼 비제한 증가, 장시간 후 판정이 변하는 결함을 발견한다.",
    s, "8주기 패턴 2,500회 반복(20,000 평가)", [WOW, REQ], cat="nonfunctional", sug=True,
    pre="자동화 클라이언트와 프로세스 메모리 측정(RSS) 도구가 있는 환경. " + BASEDEF)

# =================================================================== 분석표 (EP/BVA)
AN = []


def an(b, p, tech, item, value, key, note=""):
    AN.append({"basis_id": b, "parameter": p, "technique": tech, "item": item, "value": value, "tc_id": KEY2ID.get(key, key) if key else "", "note": note})


def an_na(b, p, item, note):
    AN.append({"basis_id": b, "parameter": p, "technique": "n/a", "item": item, "value": "-", "tc_id": "", "note": note})


# IF-001
an("OEM-IF-001", "vehicle_speed_kph", "BVA", "하한-1 (무효)", "-0.1", "speed_below")
an("OEM-IF-001", "vehicle_speed_kph", "BVA", "하한 (유효)", "0.0", "speed_min")
an_na("OEM-IF-001", "vehicle_speed_kph", "하한+1 (0.1), 상한-1 (299.9)", "내부 유효값과 같은 결과 경로(수용·NO_CHANGE/AUTO_LOCK)이며 off-by-one은 하한/상한 직접값으로 검출되어 생략(분해능 0.1)")
an("OEM-IF-001", "vehicle_speed_kph", "BVA", "상한 (유효)", "300.0", "speed_max")
an("OEM-IF-001", "vehicle_speed_kph", "BVA", "상한+1 (무효)", "300.1", "speed_above")
an("OEM-IF-001", "vehicle_speed_kph", "EP", "유효 클래스 내부값", "3.1 / 5.0 / 50.0", "auto_31")
an("OEM-IF-001", "vehicle_speed_kph", "EP", "무효 클래스: 누락", "키 없음", "speed_missing")
an("OEM-IF-001", "vehicle_speed_kph", "EP", "무효 클래스: 형식(문자열)", '"fast"', "speed_string")
an("OEM-IF-001", "gear", "EP", "유효 클래스: P/N/D/R", "P, N, D, R", "gear_valid")
an("OEM-IF-001", "gear", "EP", "무효 클래스: 미정의 값", '"X"', "gear_bad")
an("OEM-IF-001", "gear", "EP", "무효 클래스: 누락", "키 없음", "gear_missing")
an("OEM-IF-001", "source_timestamp_s", "EP", "무효 클래스: 누락", "키 없음", "srcts_missing")
an("OEM-IF-001", "source_timestamp_s", "EP", "무효 클래스: 형식", '"noon"', "srcts_string")
an_na("OEM-IF-001", "source_timestamp_s", "음수·역행·source>timestamp 값", "사양서에 범위/단조성 정의 없음 → TC 미작성, open_issues OI-07")
# IF-002
an("OEM-IF-002", "crash_status", "EP", "유효 클래스: NONE", "NONE", "crash_none")
an("OEM-IF-002", "crash_status", "EP", "유효 클래스: PENDING", "PENDING", "pictB_1")  # 아래에서 PENDING 행으로 교체
an("OEM-IF-002", "crash_status", "EP", "유효 클래스: CONFIRMED", "CONFIRMED", "crash_main")
an("OEM-IF-002", "crash_status", "EP", "무효 클래스: 미정 값", '"UNKNOWN"', "crash_bad")
an("OEM-IF-002", "crash_status", "EP", "무효 클래스: 누락", "키 없음", "crash_missing")
# IF-003
an("OEM-IF-003", "rear_left_approach_risk", "EP", "유효 TRUE", "true", "risk_left")
an("OEM-IF-003", "rear_left_approach_risk", "EP", "유효 FALSE", "false", "risk_clear")
an("OEM-IF-003", "rear_left_approach_risk", "EP", "무효: 문자열", '"true"', "risk_l_string")
an("OEM-IF-003", "rear_right_approach_risk", "EP", "유효 TRUE", "true", "risk_right")
an("OEM-IF-003", "rear_right_approach_risk", "EP", "무효: 누락", "키 없음", "risk_r_missing")
an_na("OEM-IF-003", "rear_*_approach_risk", "경계값", "불리언은 경계가 없음")
# IF-004
for val, col in (("physical_button", "Source"), ("avn", "Source"), ("voice", "Source"), ("mobile_app", "Source")):
    first = next(k for (k, a, b, c) in PICT_A_KEYS if a == val)
    an("OEM-IF-004", "source", "EP", f"유효 클래스: {val}", val, first)
for val in ("left", "right", "all"):
    first = next(k for (k, a, b, c) in PICT_A_KEYS if b == val)
    an("OEM-IF-004", "side", "EP", f"유효 클래스: {val}", val, first)
for val in ("lock", "unlock"):
    first = next(k for (k, a, b, c) in PICT_A_KEYS if c == val)
    an("OEM-IF-004", "action", "EP", f"유효 클래스: {val}", val, first)
an("OEM-IF-004", "side", "EP", "무효: 미등록 enum", '"center"', "cmd_side_bad")
an("OEM-IF-004", "side", "EP", "무효: 형식(숫자)", "0", "cmd_side_type")
an("OEM-IF-004", "action", "EP", "무효: 미등록 enum", '"toggle"', "cmd_action_bad")
an("OEM-IF-004", "source", "EP", "무효: 미등록 enum", '"bluetooth"', "cmd_source_bad")
an("OEM-IF-004", "source", "EP", "무효: 누락", "키 없음", "cmd_source_missing")
an("OEM-IF-004", "command", "EP", "유효 클래스: 명령 없음(null)", "null", "crash_none")
# IF-005..009
an("OEM-IF-005", "lock_left/right", "EP", "출력 도메인 LOCK / RELEASE", "LOCK, RELEASE", "if005_domain")
for st, k in (("OFF", "if006_states"), ("NORMAL", "if006_states"), ("DEGRADED", "if006_states"), ("FAULT", "if006_states")):
    an("OEM-IF-006", "state", "EP", f"출력 클래스: {st}", st, k)
an("OEM-IF-006", "priority_reason/reason_code", "EP", "두 필드 동일 매핑", "3개 사유", "if006_map")
an("OEM-IF-007", "fire_detected", "EP", "유효 TRUE", "true", "emerg_fire")
an("OEM-IF-007", "overtemperature_detected", "EP", "유효 TRUE", "true", "emerg_overtemp")
an("OEM-IF-007", "adult_present", "EP", "유효 TRUE", "true", "emerg_adult")
an("OEM-IF-007", "fire_detected", "EP", "무효: 누락", "키 없음", "fire_missing")
an("OEM-IF-007", "overtemperature_detected", "EP", "무효: 문자열", '"false"', "overtemp_string")
an("OEM-IF-007", "adult_present", "EP", "무효: 정수", "1", "adult_int")
an("OEM-IF-008", "isofix_left", "EP", "유효 TRUE", "true", "isofix_l")
an("OEM-IF-008", "isofix_right", "EP", "유효 TRUE", "true", "isofix_r")
an("OEM-IF-008", "isofix_left", "EP", "무효: 누락", "키 없음", "isofix_l_missing")
an("OEM-IF-008", "isofix_right", "EP", "무효: 문자열", '"yes"', "isofix_r_string")
an("OEM-IF-009", "ignition_on", "EP", "유효 FALSE", "false", "ign_off")
an("OEM-IF-009", "sensor_fault", "EP", "유효 TRUE", "true", "fault_hold_lock")
an("OEM-IF-009", "ignition_on", "EP", "무효: 누락", "키 없음", "ign_missing")
an("OEM-IF-009", "sensor_fault", "EP", "무효: 문자열", '"1"', "fault_string")
an_na("OEM-IF-007", "boolean 3종", "경계값", "불리언은 경계가 없음")
an_na("OEM-IF-008", "boolean 2종", "경계값", "불리언은 경계가 없음")
an_na("OEM-IF-009", "boolean 2종", "경계값", "불리언은 경계가 없음")
# SR
an("OEM-SR-001", "crash_status=CONFIRMED", "EP", "유효 클래스 + 모든 잠금 요인 동시", "CONFIRMED", "crash_main")
an("OEM-SR-001", "응답 시간", "BVA", "1주기(50 ms)/300 ms 한도", "첫 응답에 RELEASE, 6주기(300 ms) 유지", "crash_main")
an("OEM-SR-001", "응답 시간(벽시계)", "BVA", "300 ms 한도", "L_max ≤ 300 ms", "nfr_crash_latency")
an("OEM-SR-001", "입력 경과", "BVA", "경과 200 ms 충돌 입력", "200 ms", "crash_age200")
an("OEM-SR-002", "접근위험 좌/우", "EP", "좌만 / 우만 / 양측 / 해소", "T/F 조합", "risk_left")
an("OEM-SR-002", "접근위험 우", "EP", "우만", "true", "risk_right")
an("OEM-SR-002", "접근위험 양측", "EP", "양측 동시", "true,true", "risk_both")
an("OEM-SR-002", "접근위험 해소", "EP", "FALSE 복귀", "true→false", "risk_clear")
an("OEM-SR-003", "경과(ms)", "BVA", "임계 200 ms (정상)", "200", "stale_200")
an("OEM-SR-003", "경과(ms)", "BVA", "임계+1 201 ms (DEGRADED)", "201", "stale_201")
an_na("OEM-SR-003", "경과(ms)", "임계-1 199 ms", "200 ms와 같은 정상 결과 경로이며 200 ms가 경계 직접 검증, 생략")
an("OEM-SR-003", "DEGRADED 지연", "BVA", "200 ms 초과 후 50 ms / 100 ms", "tick 10.25 / 10.30", "stale_tick")
an("OEM-SR-003", "DEGRADED 지연(벽시계)", "BVA", "100 ms 한도", "M_max ≤ 100 ms", "nfr_degraded_latency")
an("OEM-SR-003", "시각 절대값", "BVA", "16/31/32비트 ms 경계", "65536, 2147483648, 4294967296 ms", "rollover")
an("OEM-SR-003", "무효 입력 15종", "EP", "연속 주입 후 복구", "15종", "nfr_reliab_invalid")
an("OEM-SR-004", "sensor_fault", "EP", "TRUE + 직전 LOCK", "true", "fault_hold_lock")
an("OEM-SR-004", "sensor_fault", "EP", "TRUE + 직전 RELEASE", "true", "fault_hold_release")
an("OEM-SR-004", "sensor_fault", "EP", "TRUE + 측별 서로 다른 직전값, FALSE 복귀", "true→false", "fault_hold_asym")
an_na("OEM-SR-004", "sensor_fault", "경계값", "불리언은 경계가 없음")
# FR
an("OEM-FR-001", "source x side x action", "EP", "4 x 3 x 2 조합(페어와이즈 12행)", "PICT 12행", "pictA_1")
an("OEM-FR-001", "연속 입력", "EP", "11개 명령 연속", "50 ms 간격", "cmd_burst")
an("OEM-FR-002", "vehicle_speed_kph", "BVA", "임계-0.1", "2.9", "auto_29")
an("OEM-FR-002", "vehicle_speed_kph", "BVA", "임계", "3.0", "auto_30")
an("OEM-FR-002", "vehicle_speed_kph", "BVA", "임계+0.1", "3.1", "auto_31")
an("OEM-FR-002", "vehicle_speed_kph", "BVA", "해제 허용 임계 2.9 (DEC-005)", "2.9", "deny_29")
an("OEM-FR-002", "vehicle_speed_kph", "BVA", "해제 거절 임계 3.0 (DEC-005)", "3.0", "deny_30")
an("OEM-FR-003", "재입력 경과", "BVA", "임계-1 ms", "9.999 s", "ov_9999")
an("OEM-FR-003", "재입력 경과", "BVA", "임계", "10.000 s", "ov_10000")
an("OEM-FR-003", "재입력 경과", "BVA", "임계+1 ms", "10.001 s", "ov_10001")
an("OEM-FR-003", "도어별 독립", "EP", "좌/우 서로 다른 억제 시각", "1.000/5.000/11.000", "ov_indep")
an("OEM-FR-003", "시각 절대값", "BVA", "2^32 ms 경계 통과", "4294962.000~4294972.000", "ov_rollover")
an("OEM-FR-004", "상태조회", "EP", "평가 전 / 평가 후", "-", "status_initial")
an("OEM-FR-004", "상태조회 일치", "EP", "결정 직후 최신값", "-", "status_after")
an("OEM-FR-005", "fire_detected", "EP", "단독 TRUE", "true", "emerg_fire")
an("OEM-FR-005", "overtemperature_detected", "EP", "단독 TRUE", "true", "emerg_overtemp")
an("OEM-FR-005", "adult_present", "EP", "단독 TRUE", "true", "emerg_adult")
an("OEM-FR-006", "isofix 좌/우", "EP", "좌만 / 우만 / 반대쪽 유지", "-", "isofix_l")
an("OEM-FR-006", "isofix_right", "EP", "우만", "true", "isofix_r")
an("OEM-FR-006", "반대쪽 유지", "EP", "직전 LOCK 유지", "-", "isofix_keep")
an("OEM-FR-007", "ignition_on", "EP", "FALSE", "false", "ign_off")
an("OEM-FR-007", "ignition_on", "EP", "FALSE→TRUE 재ON", "-", "ign_cycle")
an_na("OEM-FR-007", "ignition_on", "경계값", "불리언은 경계가 없음")
an("OEM-NFR-001", "재생 횟수", "BVA", "1,000회", "1000", "nfr1_replay")
an("OEM-NFR-002", "이벤트 건수", "BVA", "99 / 100 / 101건", "99, 100, 101", "nfr2_100")
an("OEM-NFR-002", "레코드 필드", "EP", "허용 필드 8개 / 금지 토큰", "-", "nfr2_fields")
an("OEM-NFR-002", "재기동", "EP", "재기동 후 0건", "-", "nfr2_volatile")

# 가정으로 만든 PICT_B 첫 PENDING 행 찾기 (분석표의 PENDING 클래스 증거)
pend = next(i for i, r in enumerate(rowsB, 1) if r["Crash"] == "PENDING" and r["Emergency"] == "NONE" and r["Fault"] == "F")
for a in AN:
    if a["parameter"] == "crash_status" and a["item"] == "유효 클래스: PENDING":
        a["tc_id"] = KEY2ID[f"pictB_{pend}"]

# =================================================================== 기타
OPEN = [
    "OI-01 [IF-006/SWR-014] '직렬화 실패를 주입하면 HTTP 500'은 시스템 수준 블랙박스(Web API)에서 주입 수단이 없어 TC를 만들지 않았다. 통합 시험(tests/)에서 검증하거나 시험용 결함 주입 훅(예: 환경변수)의 제공 여부를 결정해 달라.",
    "OI-02 [SR-001] '이후 입력 주기에도 유지된다'가 (a) CONFIRMED 입력이 지속되는 동안만 유지인지 (b) NONE 복귀 후에도 래치인지 사양서에 없다. 우선순위표(DEC-001)에는 래치가 없다. TC는 두 해석이 모두 같은 값을 주는 부분(CONFIRMED 지속 중 유지)만 판정하고, NONE 복귀 후 ISOFIX/명령 적용 여부는 TC에서 제외했다.",
    "OI-03 [SR-001/SR-003, DEC-001 순위 0] 경과 200 ms를 넘은 충돌 CONFIRMED 입력은 stale로 보류되어 해제가 실행되지 않는다(TC stale_crash, 제안). 안전 영향을 OEM이 확인해야 한다.",
    "OI-04 [IF-006] 충돌 CONFIRMED/비상/PENDING 규칙과 sensor_fault 또는 ignition_on=FALSE가 동시에 성립할 때의 state(OFF/FAULT/NORMAL)가 사양서·결정 기록에 정해져 있지 않다(상세설계 7절의 입력 기반 우선순위와 아키텍처 _state_for 기술이 충돌 가능). 해당 PICT 행은 state를 판정에서 제외했다.",
    "OI-05 [FR-007] 수용기준 '좌, 우 출력이 RELEASE'와 사용자 확정(ISOFIX가 시동 OFF보다 우선하여 해당 측 LOCK 유지)이 상충한다. TC ign_vs_isofix(제안)는 사용자 확정을 따른다. OEM 확인 필요.",
    "OI-06 [FR-003] (a) 첫 억제 직후(0~50 ms) 같은 명령이 오면 override인지(문언상 10초 이하 → 성립), 최소 간격/디바운스 요구가 있는지 (b) '같은 해제 명령'이 source까지 같아야 하는지 (c) all 명령과 left/right 명령이 같은 도어 기준에서 어떻게 합산되는지 사양서에 없다. TC는 문언 그대로(경과만 판정, source 무관) 기대값을 두었고 ov_fast, ov_all은 제안으로 분리했다.",
    "OI-07 [IF-001] timestamp_s/source_timestamp_s의 범위(음수, 시계 역행, source가 timestamp보다 미래인 음의 경과)에 대한 처리 요구가 없어 TC를 만들지 않았다. 롤오버(큰 값)는 사양서 200 ms 규칙으로 판정 가능하여 TC화했다.",
    "OI-08 [SR-003] 입력 거절(422) 주기가 freshness 기준(마지막 수용 입력 시각)을 갱신하는지, 거절도 이벤트로 기록되는지는 사양서에 없다(상세설계는 INPUT_INVALID 이벤트 기록). TC는 /status의 reason_code=INPUT_INVALID와 출력·state 유지만 판정하고 이벤트 건수에는 거절을 포함하지 않는다.",
    "OI-09 reason_code 선택 규칙(좌우 사유가 다를 때 상위 순위 사유, 같은 순위면 좌측, 비상 복수 시 화재>과온>성인)은 결정 기록이 아니라 상세설계(_pick_priority_reason, rule_emergency)만 근거이다. PICT 행의 reason_code는 이를 따르며, 순위 7의 서로 다른 사유(AUTO_LOCK_SPEED vs RELEASE_DENIED_MOVING)가 맞붙는 행은 reason_code 판정을 제외했다.",
    "OI-10 [NFR-002] GET /events의 정렬 방향과 응답 구조(최상위 배열 여부)가 사양서에 없다. TC는 오래된 것부터 오름차순(상세설계 8절)을 가정한다.",
    "OI-11 [IF-006] input_validity의 그룹명과 stale 시 값은 상세설계(speed, gear, crash, approach, emergency, isofix, ignition, sensor_fault, command, time / VALID, INVALID, STALE)에 근거한다. TC는 speed 그룹 INVALID와 stale 시 'STALE이 하나 이상'만 판정한다.",
    "OI-12 평가 이전 초기 reason_code 값이 정해져 있지 않아 키 존재만 판정한다(status_initial).",
    "OI-13 [IF-003/007/008/009] JSON 정수 1, 문자열 'true'/'yes'/'1'을 '형식 오류'로 보아 거절을 기대했다(JSON boolean만 유효하다는 해석). OEM이 느슨한 변환을 허용하면 해당 TC(adult_int, risk_l_string, overtemp_string, isofix_r_string, fault_string)를 수정한다.",
    "OI-14 /tick 호출 시 직전 스냅샷의 명령이 재적용되는지, 스냅샷이 없을 때의 동작은 사양서에 없다. TC는 평가 입력 직후의 tick만 사용하고 fresh tick 응답은 출력·state만 판정한다.",
    "OI-15 [NFR] 장시간 TC(nfr_soak)의 메모리 증가율 10% 기준은 사양서에 없는 시험 판정 기준 제안값이다(제안 TC로 분리). 사양에 명시된 수치는 50 ms 주기(DEC-002), 100 ms, 300 ms, 200 ms, 10 s, 100건, 1,000회뿐이다.",
    "가정 A1 모든 시험은 SIL(Web API 블랙박스)이며 HIL/실차는 범위 밖(사양서 1.3). 환경 표기는 'SIL(Web API)'.",
    "가정 A2 평가주기 50 ms(DEC-002), 경계 방향과 ms 반올림(DEC-007), 우선순위표(DEC-001), 이동 중 해제 거절(DEC-005), PENDING 직전 출력 유지(DEC-003), DEGRADED 복귀(DEC-004), 기어 비사용(DEC-006), override 지속(DD-004)은 공급자 해석이며 해당 의존 TC는 목적란에 'DEC-xxx 의존'을 표기했다. 사양서 문언으로만 도출되지 않는 TC는 제안(-S)이다.",
    "가정 A3 서버 신규 기동 = 초기화 상태이다. 초기 상태에서 전용 리셋 API는 없다고 보고 PICT/초기상태 TC는 TC마다 신규 기동을 전제로 한다(자동화 시 프로세스 재사용 불가).",
    "가정 A4 PICT 행의 기대값은 00_decisions.md 우선순위표를 옮긴 oracle(gen_tc.py)로 계산했고, 행 일부는 summary.md에 수기 검산했다. 구현(src/)은 읽거나 실행해 맞추지 않았다.",
]


def main():
    pict = []
    for name, model, outn, order in (("FR-001 명령 조합(Source x Side x Action)", "pict_command_model.txt", "pict_command_output.tsv", 2),
                                     ("우선순위 조합 B(전역 규칙 포함)", "pict_priority_model.txt", "pict_priority_output.tsv", 2),
                                     ("우선순위 조합 C(측별 규칙, ASIL B 상호작용)", "pict_side_model.txt", "pict_side_output.tsv", 3)):
        pict.append({"name": name, "model": (HERE / model).read_text(encoding="utf-8"),
                     "output": (HERE / outn).read_text(encoding="utf-8"), "order": order})
    d = {
        "meta": {"project": "전자식 차일드락 제어 SW (Volsojoda, OEM-A 공급자)", "version": "0.1", "asil": "B", "env": "SIL(Web API)",
                 "basis_doc": "OEM-SWR-001 Rev1.0 (BL-OEM-1.0) 5장 요구사항 13건 + 6장 인터페이스 9건; 해석: docs/01_requirements/00_decisions.md"},
        "columns": None,
        "test_basis": [{"id": i, "title": t, "text": x, "type": ty, "asil": a} for (i, t, x, ty, a) in TB],
        "analysis": AN,
        "testcases": TCS,
        "pict": pict,
        "open_issues": OPEN,
    }
    (HERE / "tc.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "dec_dependent_tcs.json").write_text(json.dumps(DEC_DEP, ensure_ascii=False), encoding="utf-8")
    print("TC", len(TCS), "DEC 의존", len(DEC_DEP))


if __name__ == "__main__":
    main()
