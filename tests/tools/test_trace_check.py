"""SWR 양방향 추적성 검증기 테스트."""
from tools.trace_check import check_traceability, main, parse_swr

TABLE = """\
| SWR ID | 상위 요구 | ASIL | 구분 | 요구사항 | 수용기준 | 검증 |
|---|---|---|---|---|---|---|
| SWR-001 | OEM-A, OEM-B | QM | 도출 | x | y | 단위 |
| SWR-002 | OEM-B | QM | 제안 | x | y | 단위 |
| SWR-003 | - | - | 결번 | x | - | - |
"""


def test_parse_reads_id_parents_and_kind():
    rows = parse_swr(TABLE)
    assert rows == [
        {"id": "SWR-001", "parents": ["OEM-A", "OEM-B"], "kind": "도출", "verification": "단위"},
        {"id": "SWR-002", "parents": ["OEM-B"], "kind": "제안", "verification": "단위"},
        {"id": "SWR-003", "parents": [], "kind": "결번", "verification": "-"},
    ]


def test_parse_ignores_non_swr_lines():
    assert parse_swr("| 인터페이스 | 관련 SWR |\n| OEM-IF-001 | SWR-001 |\n") == []


def test_no_errors_when_fully_traced():
    rows = parse_swr(TABLE)
    assert check_traceability(["OEM-A", "OEM-B"], rows) == []


def test_reports_oem_requirement_without_swr():
    errors = check_traceability(["OEM-A", "OEM-B", "OEM-C"], parse_swr(TABLE))
    assert errors == ["상위 요구 OEM-C 를 구현하는 SWR이 없습니다"]


def test_reports_swr_without_parent_except_reserved():
    rows = [{"id": "SWR-009", "parents": [], "kind": "도출"}]
    assert check_traceability([], rows) == ["SWR-009 의 상위 요구가 없습니다"]


def test_reports_unknown_parent_and_duplicate_id():
    rows = [
        {"id": "SWR-001", "parents": ["OEM-Z"], "kind": "도출"},
        {"id": "SWR-001", "parents": ["OEM-A"], "kind": "도출"},
    ]
    errors = check_traceability(["OEM-A"], rows)
    assert "SWR-001 의 상위 요구 OEM-Z 는 사양서에 없습니다" in errors
    assert "SWR ID 중복: SWR-001" in errors


def test_main_exit_codes(tmp_path):
    swr = tmp_path / "swr.md"
    swr.write_text(TABLE, encoding="utf-8")
    oem = tmp_path / "oem.txt"
    oem.write_text("OEM-A\nOEM-B\n", encoding="utf-8")
    assert main([str(swr), str(oem)]) == 0
    oem.write_text("OEM-A\nOEM-B\nOEM-C\n", encoding="utf-8")
    assert main([str(swr), str(oem)]) == 1
