"""SWR 양방향 추적성 검증기.

SWR 명세(markdown 표)와 OEM 요구사항 ID 목록을 비교해
상위 요구의 누락, 상위 요구가 없는 SWR, 잘못된 참조, 중복 ID를 찾는다.
"""
import argparse
import sys

RESERVED = "결번"


def parse_swr(text: str) -> list[dict]:
    """markdown 표에서 SWR 행을 읽는다.

    @param text SWR 명세 markdown 전문
    @return 각 행의 id, parents, kind 를 담은 딕셔너리 목록
    """
    rows = []
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells[0].startswith("SWR-") or len(cells) < 4:
            continue
        parents = [p.strip() for p in cells[1].split(",") if p.strip() not in ("", "-")]
        rows.append({"id": cells[0], "parents": parents, "kind": cells[3]})
    return rows


def check_traceability(oem_ids: list[str], rows: list[dict]) -> list[str]:
    """양방향 추적성을 검사한다.

    @param oem_ids 사양서의 OEM 요구사항 ID 목록
    @param rows parse_swr 결과
    @return 오류 메시지 목록 (비어 있으면 통과)
    """
    errors = []
    seen: set[str] = set()
    referenced: set[str] = set()
    for row in rows:
        if row["id"] in seen:
            errors.append(f"SWR ID 중복: {row['id']}")
        seen.add(row["id"])
        if row["kind"] == RESERVED:
            continue
        if not row["parents"]:
            errors.append(f"{row['id']} 의 상위 요구가 없습니다")
        for parent in row["parents"]:
            referenced.add(parent)
            if parent not in oem_ids:
                errors.append(f"{row['id']} 의 상위 요구 {parent} 는 사양서에 없습니다")
    missing = [oem for oem in oem_ids if oem not in referenced]
    errors.extend(f"상위 요구 {oem} 를 구현하는 SWR이 없습니다" for oem in missing)
    return errors


def main(argv: list[str]) -> int:
    """명령행 진입점. 추적성 오류가 없으면 0, 있으면 1을 반환한다.

    @param argv 인자 목록 (SWR markdown 경로, OEM ID 목록 파일 경로)
    @return 프로세스 종료 코드
    """
    parser = argparse.ArgumentParser(description="SWR 추적성 검증")
    parser.add_argument("swr", help="SWR 명세 markdown")
    parser.add_argument("oem_ids", help="OEM 요구사항 ID 목록(줄 단위)")
    args = parser.parse_args(argv)
    with open(args.swr, encoding="utf-8") as swr_file:
        rows = parse_swr(swr_file.read())
    with open(args.oem_ids, encoding="utf-8") as oem_file:
        oem_ids = [line.strip() for line in oem_file if line.strip()]
    errors = check_traceability(oem_ids, rows)
    for error in errors:
        print("오류:", error)
    print(f"SWR {len(rows)}행, 상위 요구 {len(oem_ids)}건, 오류 {len(errors)}건")
    return 1 if errors else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
