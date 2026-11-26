"""단위 시험 추적성 검증기.

시험 파일의 `pytestmark = pytest.mark.swr("SWR-xxx")` 표식을 읽어,
검증 수준에 "단위"가 있는 모든 SWR이 단위 시험을 가지는지 검사한다.
"""
import argparse
import ast
import sys
from pathlib import Path

from tools.trace_check import RESERVED, parse_swr


def _swr_ids_of(node: ast.expr) -> set[str]:
    """`pytest.mark.swr("SWR-001", ...)` 호출 식에서 SWR ID를 모은다.

    @param node 검사할 식 노드
    @return 호출이 swr 표식이면 문자열 인자 집합, 아니면 빈 집합
    """
    if not isinstance(node, ast.Call):
        return set()
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "swr"):
        return set()
    return {a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)}


def collect_swr_marks(source: str) -> set[str]:
    """시험 파일 소스의 모듈 수준 `pytestmark`에서 SWR ID를 모은다.

    @param source 시험 파일 소스 코드
    @return 선언된 SWR ID 집합
    """
    found: set[str] = set()
    for node in ast.parse(source).body:
        is_marks = isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
        )
        if not is_marks:
            continue
        value = node.value
        items = value.elts if isinstance(value, ast.List | ast.Tuple) else [value]
        for item in items:
            found |= _swr_ids_of(item)
    return found


def unit_gaps(rows: list[dict], marked: set[str]) -> list[str]:
    """단위 시험이 없는 SWR과 존재하지 않는 SWR 참조를 찾는다.

    @param rows parse_swr 결과
    @param marked 시험 표식에 선언된 SWR ID 집합
    @return 오류 메시지 목록 (비어 있으면 통과)
    """
    known = {row["id"] for row in rows}
    errors = [
        f"{row['id']} 의 단위 시험이 없습니다"
        for row in rows
        if row["kind"] != RESERVED and "단위" in row["verification"] and row["id"] not in marked
    ]
    errors.extend(f"시험이 존재하지 않는 {swr} 를 참조합니다" for swr in sorted(marked - known))
    return errors


def main(argv: list[str]) -> int:
    """명령행 진입점. 단위 시험 추적 오류가 없으면 0, 있으면 1을 반환한다.

    @param argv 인자 목록 (SWR markdown 경로, 시험 폴더 경로)
    @return 프로세스 종료 코드
    """
    parser = argparse.ArgumentParser(description="단위 시험 추적성 검증")
    parser.add_argument("swr", help="SWR 명세 markdown")
    parser.add_argument("tests_dir", help="시험 폴더")
    args = parser.parse_args(argv)
    rows = parse_swr(Path(args.swr).read_text(encoding="utf-8"))
    marked: set[str] = set()
    for path in Path(args.tests_dir).rglob("test_*.py"):
        marked |= collect_swr_marks(path.read_text(encoding="utf-8"))
    errors = unit_gaps(rows, marked)
    for error in errors:
        print("오류:", error)
    print(f"SWR {len(rows)}행, 표식된 SWR {len(marked)}건, 오류 {len(errors)}건")
    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
