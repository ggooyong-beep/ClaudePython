# 단위 시험 보고서 (5단계)

자동 검증: `tools/unit_trace.py`가 시험 파일의 `pytest.mark.swr` 표식을 SWR 표와 대조한다. 검증 수준에 "단위"가 있는 SWR은 모두 단위 시험을 가진다.

## 결과 (로컬)

| 기준 | 결과 |
|---|---|
| 시험 케이스(제품) | 함수 100개 (매개변수화 포함 실행 수는 pytest 결과 참조) |
| 성공률 | 100% (실패·건너뜀·예상 실패 없음) |
| Branch 커버리지 | 100% |
| Ruff | 오류 0건 |
| 주석률(cloc) | 28.4% |
| 변이 검사 | 경계·순서 변이 7개 모두 검출 |

## SWR → 단위 시험

| SWR | 검증 수준 | 단위 시험 파일 |
|---|---|---|
| SWR-001 | 단위, 통합 | test_rules_side.py, test_validator.py |
| SWR-002 | 단위, 통합 | test_rules_side.py, test_validator.py |
| SWR-003 | 단위, 시스템 | test_rules_side.py |
| SWR-004 | 단위, 시스템 | test_rules_side.py |
| SWR-005 | 단위, 시스템 | test_rules_side.py |
| SWR-006 | 단위, 시스템 | test_arbiter.py, test_rules_side.py |
| SWR-007 | 단위, 시스템 | test_controller.py, test_rules_global.py |
| SWR-008 | 단위, 시스템 | test_rules_global.py |
| SWR-009 | 단위, 시스템 | test_rules_side.py |
| SWR-010 | 단위 | test_event_log.py |
| SWR-011 | 단위 | test_event_log.py |
| SWR-012 | 단위, 통합 | test_event_log.py |
| SWR-013 | 단위, 시스템 | test_arbiter.py, test_controller.py, test_validator.py |
| SWR-014 | 통합, 시스템 | test_api.py, test_models.py |
| SWR-015 | 통합, 시스템 | (단위 대상 아님) |
| SWR-016 | 단위, 시스템 | test_determinism.py |
| SWR-017 | 단위, 시스템 | test_rules_global.py |
| SWR-018 | 단위, 시스템 | test_rules_side.py |
| SWR-019 | - | (결번) |
| SWR-020 | 단위, 시스템 | test_rules_side.py |
| SWR-021 | 단위, 시스템 | test_rules_global.py |
| SWR-022 | 단위, 시스템 | test_arbiter.py |
| SWR-023 | 단위, 시스템 | test_controller.py |

## 시험 파일

| 파일 | 시험 함수 수 |
|---|---|
| test_api.py | 12 |
| test_arbiter.py | 24 |
| test_controller.py | 11 |
| test_determinism.py | 2 |
| test_event_log.py | 8 |
| test_models.py | 3 |
| test_rules_global.py | 9 |
| test_rules_side.py | 21 |
| test_validator.py | 10 |
