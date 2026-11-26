"""주석률 품질 게이트 테스트 (cloc --json --by-file 출력 기준)."""
import json

import pytest
from tools.quality_gate import comment_ratio, main


def _cloc(files: dict[str, tuple[int, int]]) -> dict:
    """파일별 (주석, 코드) 라인 수로 cloc JSON 구조를 만든다."""
    data: dict = {"header": {"cloc_version": "2.0"}, "SUM": {"comment": 999, "code": 999}}
    for path, (comment, code) in files.items():
        data[path] = {"blank": 5, "comment": comment, "code": code}
    return data


def test_ratio_is_comment_over_comment_plus_code_in_percent():
    data = _cloc({"src/a.py": (2, 8)})
    assert comment_ratio(data, ["src/"]) == 20.0


def test_ratio_sums_all_matching_files_and_ignores_header_and_sum():
    data = _cloc({"src/a.py": (1, 9), "src/b.py": (3, 7)})
    assert comment_ratio(data, ["src/"]) == 20.0


def test_ratio_excludes_files_outside_prefixes():
    data = _cloc({"src/a.py": (1, 3), "tests/t.py": (0, 100)})
    assert comment_ratio(data, ["src/"]) == 25.0


def test_ratio_raises_when_no_lines_match():
    with pytest.raises(ValueError, match="대상 파일"):
        comment_ratio(_cloc({"tests/t.py": (1, 1)}), ["src/"])


@pytest.mark.parametrize(
    ("comment", "code", "expected_exit"),
    [(2, 8, 0), (21, 79, 0), (19, 81, 1), (1, 9, 1)],
)
def test_main_passes_at_threshold_and_fails_below(tmp_path, comment, code, expected_exit):
    report = tmp_path / "cloc.json"
    report.write_text(json.dumps(_cloc({"src/a.py": (comment, code)})), encoding="utf-8")
    assert main([str(report), "--min", "20", "--prefix", "src/"]) == expected_exit


def test_ratio_matches_windows_style_backslash_paths():
    data = _cloc({r"src\childlock\a.py": (2, 8), r"tests\t.py": (0, 100)})
    assert comment_ratio(data, ["src/"]) == 20.0
