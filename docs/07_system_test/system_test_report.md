# 시스템 테스트 보고서 (7단계)

시험 대상: Web API(`childlock.web.api`)를 블랙박스로 시험한 SIL 수준 시스템 테스트.
시험 케이스: `system_test_cases.xlsx`(기능 152, 비기능 10, 제안 75, WoW 검증 28, PICT 유래 69).
테스트 베이시스 22건(OEM-SR 4, FR 7, NFR 2, IF 9)을 22/22 커버하며, `build_xlsx.py` 검증(미커버·고아 TC·모호어·필수 기법 누락)은 오류 0건이다.

## 실행 방법

```
python docs/07_system_test/run_system_tests.py --json docs/07_system_test/system_test_results.json
```

`tc.json`의 HTTP 절차(`POST /evaluate`, `POST /tick`, `GET /status`)를 TC마다 새 애플리케이션에 실행하고 `[n]` 기대값(HTTP 상태, `lock_left`, `lock_right`, `state`, `reason_code`, `override`)과 비교한다.
기대값은 시험 케이스 생성 단계에서 `00_decisions.md`와 사양서 수용기준만으로 계산했으며 구현을 읽고 맞추지 않았다.

## 실행 결과

| 시점 | PASS | FAIL | SKIP |
|---|---|---|---|
| 결함 수정 전 | 146 | 3 | 13 |
| 결함 수정 후 | 149 | 0 | 13 |

## 발견한 결함 (모두 수정)

| ID | TC | 증상 | 근거 | 수정 |
|---|---|---|---|---|
| DEF-001 | TC-F-010, TC-N-009 | 누락된 `source_timestamp_s`가 `timestamp_s`로 자동 채워져 200이 반환된다. 낡은 입력 판정을 우회한다. | OEM-IF-001 "누락 INVALID", OEM-SR-003 | `_with_clock`이 평가 시각만 채운다. 누락은 422. |
| DEF-002 | TC-F-051 | 한쪽 override, 반대쪽 접근위험 잠금이면 `reason_code`가 `APPROACH_RISK_RIGHT`이다. override 이유코드가 응답에 없다. | SWR-006, OEM-FR-003 "override 상태와 이유코드 생성" | `APPROACH_OVERRIDE`를 접근위험 잠금보다 앞선 이유코드 순위로 둔다. |

두 결함 모두 단위·통합 시험이 놓쳤고 시스템 테스트가 잡았다. 회귀 시험은 `test_arbiter.py`와 `test_api.py`에 추가했다.

## 자동 실행하지 못한 TC (13건, SKIP)

서버 프로세스 재시작·강제 종료, 1,000회·20,000회 반복, 실시간 60 s 측정, `GET /events` 본문 검증처럼 별도 실행 환경이 필요한 TC이다. 자동 실행 결과에 포함되지 않았으므로 **미실행 상태**다.

TC-F-089, TC-F-090, TC-F-091, TC-F-095-S, TC-N-001, TC-N-002, TC-N-003, TC-N-004, TC-N-005, TC-N-006, TC-N-007, TC-N-008-S, TC-N-010-S

일부(이벤트 100건 경계, 재기동 후 비어 있음, 결정론 1,000회)는 단위·통합 시험이 같은 성질을 이미 검증한다. 타이밍(TC-N-006, TC-N-007)과 장시간(TC-N-008-S, TC-N-010-S)은 실행하지 않았다.

## 한계와 확인 필요

- 기대값의 일부는 공급자 해석(DEC-001~008, DD-004)에 의존한다. 의존 TC는 xlsx 목적란에 `[DEC-xxx 의존]`으로 표시했다. OEM이 다르게 답하면 해당 TC와 구현을 함께 고쳐야 한다.
- OEM에 확인할 항목(open_issues 15건)은 `system_test_cases.xlsx`의 `요약` 시트와 `tc.json`에 있다. 안전과 관련이 큰 것은 다음과 같다.
  - 경과 200 ms를 넘은 충돌 `CONFIRMED` 입력은 낡은 입력으로 보류되어 해제가 실행되지 않는다(OI-03).
  - 사양서 FR-007(시동 OFF 시 양측 해제)과 사용자 확정(ISOFIX 우선)이 상충한다(OI-05).
- 측정 도구와 환경: 시험은 PC/SIL(TestClient)에서 실행했으며 HIL·실차 시험은 범위 밖이다.
