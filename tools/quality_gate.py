"""주석률 품질 게이트.

`cloc --json --by-file` 출력에서 대상 파일의 주석률을 계산하고
기준 미만이면 비정상 종료한다.
"""
import argparse
import json
import sys


def comment_ratio(cloc_data: dict, prefixes: list[str]) -> float:
    """대상 파일들의 주석률(%)을 계산한다.

    @param cloc_data `cloc --json --by-file` 결과 딕셔너리
    @param prefixes 측정 대상 경로 접두사 목록
    @return 주석 라인 / (코드 라인 + 주석 라인) * 100
    @raises ValueError 대상 파일의 코드·주석 라인이 없을 때
    """
    comment = 0
    code = 0
    for path, stats in cloc_data.items():
        normalized = path.replace("\\", "/")
        if path in ("header", "SUM") or not normalized.startswith(tuple(prefixes)):
            continue
        comment += stats["comment"]
        code += stats["code"]
    if comment + code == 0:
        raise ValueError(f"측정할 대상 파일이 없습니다: {prefixes}")
    return comment / (comment + code) * 100


def main(argv: list[str]) -> int:
    """명령행 진입점. 주석률이 기준 이상이면 0, 미만이면 1을 반환한다.

    @param argv 인자 목록 (cloc JSON 경로, --min, --prefix)
    @return 프로세스 종료 코드
    """
    parser = argparse.ArgumentParser(description="주석률 품질 게이트")
    parser.add_argument("report", help="cloc --json --by-file 결과 파일")
    parser.add_argument("--min", type=float, default=20.0, help="최소 주석률(%%)")
    parser.add_argument("--prefix", action="append", required=True, help="측정 대상 경로 접두사")
    args = parser.parse_args(argv)
    with open(args.report, encoding="utf-8") as report:
        ratio = comment_ratio(json.load(report), args.prefix)
    print(f"주석률 {ratio:.1f}% (기준 {args.min:.1f}% 이상)")
    return 0 if ratio >= args.min else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
