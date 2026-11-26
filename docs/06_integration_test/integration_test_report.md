# 통합 시험 보고서 (6단계)

HTTP API에서 컨트롤러, 판단 코어, 이벤트 로그까지 이어 붙여 평가주기 단위 시나리오를 검증한다.
화면(SWR-015)은 실제 Chromium 브라우저(Playwright)로 검증한다.

## 결과 (로컬)

| 기준 | 결과 |
|---|---|
| 전체 시험 | 181개 통과 (통합 19개: 시나리오 13, 브라우저 6) |
| Branch 커버리지 | 100% |
| Ruff | 오류 0건 |
| 주석률(cloc) | 28.4% |
| 변이 검사 | 통합 시험만으로 구현 변이 6개, 화면 변이 3개 모두 검출 |

## SWR → 통합 시험

| SWR | 검증 내용 | 시험 |
|---|---|---|
| SWR-001 | 네 가지 명령 경로 모두 잠금·해제 처리 | `test_scenarios.py::test_each_command_source_locks_then_releases_when_stopped` |
| SWR-002 | 대상(left/right/all)에 해당하는 출력만 변경 | `test_scenarios.py::test_command_side_changes_only_selected_outputs` |
| SWR-006 | 접근위험 억제 → override → 해제 시나리오 | `test_scenarios.py::test_approach_risk_scenario_suppress_then_override_then_clear` |
| SWR-007 | 충돌 확정 해제가 이후 주기에도 유지 | `test_scenarios.py::test_crash_confirmed_releases_in_the_next_cycle_and_survives_later_cycles` |
| SWR-012 | 최근 100건 보존, 재기동 후 비어 있음 | `test_scenarios.py::test_only_latest_100_decisions_are_listed_in_order`, `test_new_application_starts_without_previous_events` |
| SWR-013 | 거절 입력은 출력을 바꾸지 않고, 낡은 입력은 `DEGRADED`, 신선한 입력으로 복귀 | `test_scenarios.py::test_invalid_input_in_the_middle_...`, `test_stale_input_degrades_through_tick_...` |
| SWR-014 | 상태조회에 출력, state, 유효성, 이유코드 | `test_scenarios.py`(여러 시나리오의 `/status`, `/events`) |
| SWR-015 | 화면에서 입력을 보내면 갱신된 상태와 이유코드 표시 | `test_ui.py` (브라우저 6개) |

## 한계

- 화면 시험은 Chromium 한 종류에서만 확인했다. 사용성 평가는 범위 밖이다.
- Jenkins 에이전트에는 `playwright install chromium`이 필요하다(Jenkinsfile에 단계 추가).
