"""단위 시험 추적성 검증기 시험: 모든 SWR이 단위 시험 표식을 가져야 한다."""
from tools.unit_trace import collect_swr_marks, main, unit_gaps


def test_collects_marks_from_pytestmark_list():
    source = (
        "import pytest\n"
        'pytestmark = [pytest.mark.swr("SWR-001"), pytest.mark.swr("SWR-002")]\n'
    )
    assert collect_swr_marks(source) == {"SWR-001", "SWR-002"}


def test_collects_single_mark_and_multiple_arguments():
    source = 'import pytest\npytestmark = pytest.mark.swr("SWR-003", "SWR-004")\n'
    assert collect_swr_marks(source) == {"SWR-003", "SWR-004"}


def test_ignores_other_marks_and_files_without_marks():
    source = "import pytest\npytestmark = [pytest.mark.slow, pytest.mark.parametrize('a', [1])]\n"
    assert collect_swr_marks(source) == set()
    assert collect_swr_marks("x = 1\n") == set()


def _row(swr_id, kind="도출", verification="단위, 시스템"):
    return {"id": swr_id, "parents": ["OEM-A"], "kind": kind, "verification": verification}


def test_no_gap_when_every_unit_verified_swr_is_marked():
    rows = [_row("SWR-001"), _row("SWR-002")]
    assert unit_gaps(rows, {"SWR-001", "SWR-002"}) == []


def test_reports_unit_verified_swr_without_unit_test():
    rows = [_row("SWR-001"), _row("SWR-002")]
    assert unit_gaps(rows, {"SWR-001"}) == ["SWR-002 의 단위 시험이 없습니다"]


def test_skips_reserved_and_non_unit_swr():
    rows = [
        _row("SWR-019", kind="결번", verification="-"),
        _row("SWR-014", verification="통합, 시스템"),
    ]
    assert unit_gaps(rows, set()) == []


def test_reports_mark_for_unknown_swr():
    assert unit_gaps([_row("SWR-001")], {"SWR-001", "SWR-099"}) == [
        "시험이 존재하지 않는 SWR-099 를 참조합니다"
    ]


def test_main_exit_codes(tmp_path):
    swr = tmp_path / "swr.md"
    swr.write_text(
        "| SWR-001 | OEM-A | QM | 도출 | x | y | 단위 |\n", encoding="utf-8"
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_a.py").write_text(
        'import pytest\npytestmark = pytest.mark.swr("SWR-001")\n', encoding="utf-8"
    )
    assert main([str(swr), str(tests_dir)]) == 0
    (tests_dir / "test_a.py").write_text("x = 1\n", encoding="utf-8")
    assert main([str(swr), str(tests_dir)]) == 1
