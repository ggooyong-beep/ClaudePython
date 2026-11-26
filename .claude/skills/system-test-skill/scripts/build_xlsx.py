#!/usr/bin/env python3
"""테스트 명세 JSON을 검증하고 xlsx(기능/비기능 시트 분리)로 산출한다.

사용: build_xlsx.py tc.json -o out.xlsx [--allow-gaps]
검증 실패 시 exit 1 (기본: xlsx 미생성). 의존성: openpyxl
"""
import argparse, json, re, sys
from collections import defaultdict

ALLOWED_TECH = {"경계값분석", "동치 클래스", "페어와이즈(PICT)", "WoW 검증",
                "요구사항 분석", "오류 추정", "결함 주입"}
VAGUE = re.compile(r"(적절한|적당한|정상적으로|올바르게|등등|\betc\b|기타|TBD|TBC|\?\?)", re.I)

DEFAULT_COLS = [
    ("id", "테스트 케이스 ID"), ("basis", "테스트 베이시스 ID"), ("title", "제목"),
    ("purpose", "테스트 목적"), ("precondition", "사전조건"), ("inputs", "입력값"),
    ("steps", "절차"), ("expected", "예상 출력값"), ("techniques", "사용한 테스트 기법"),
    ("suggested", "제안 여부"), ("asil", "ASIL"), ("priority", "우선순위"), ("env", "환경"),
    ("result", "실행 결과"),
]


def as_text(v):
    if isinstance(v, list):
        return "\n".join(str(x) for x in v)
    return "" if v is None else str(v)


def validate(d):
    errs, warns = [], []
    tb = {t["id"]: t for t in d.get("test_basis", [])}
    tcs = d.get("testcases", [])
    if not tb:
        errs.append("test_basis 비어 있음")
    ids = [t["id"] for t in tcs]
    for i in {x for x in ids if ids.count(x) > 1}:
        errs.append(f"TC ID 중복: {i}")

    covered = defaultdict(list)
    all_tech = set()
    for t in tcs:
        tid = t["id"]
        sug = bool(t.get("suggested"))
        if sug and not tid.endswith("-S"):
            errs.append(f"{tid}: 제안 TC는 ID가 '-S'로 끝나야 함")
        if not sug and tid.endswith("-S"):
            errs.append(f"{tid}: '-S' ID인데 suggested=false")
        if t.get("category") not in ("functional", "nonfunctional"):
            errs.append(f"{tid}: category 는 functional|nonfunctional")
        for k in ("purpose", "inputs", "steps", "expected"):
            if not as_text(t.get(k)).strip():
                errs.append(f"{tid}: '{k}' 비어 있음 (실행 불가)")
        if not t.get("techniques"):
            errs.append(f"{tid}: techniques 비어 있음")
        for q in t.get("techniques", []):
            all_tech.add(q)
            if q not in ALLOWED_TECH:
                errs.append(f"{tid}: 허용되지 않은 기법명 '{q}'")
        for k in ("inputs", "steps", "expected"):
            m = VAGUE.search(as_text(t.get(k)))
            if m:
                errs.append(f"{tid}: '{k}' 에 모호 표현 '{m.group(0)}' (구체값으로 교체)")
        if not t.get("basis_ids"):
            if sug:
                warns.append(f"{tid}: 베이시스 미연결 제안 TC (요약에 '베이시스 보완 제안'으로 집계)")
            else:
                errs.append(f"{tid}: 고아 TC — basis_ids 없음")
        for b in t.get("basis_ids", []):
            if b not in tb:
                errs.append(f"{tid}: 존재하지 않는 베이시스 ID '{b}'")
            elif not sug:
                covered[b].append(tid)
            else:
                covered.setdefault(b, covered.get(b, []))  # 제안 TC는 커버리지에 불산입

    # 지시된 필수 기법
    for need in ("경계값분석", "동치 클래스"):
        if need not in all_tech:
            errs.append(f"필수 기법 '{need}' 가 어떤 TC에도 없음")
    if not any("WoW 검증" in t.get("techniques", []) for t in tcs):
        errs.append("WoW 검증(엣지) TC 없음")

    # 베이시스 커버리지 (제안 TC 제외 = 사용자 베이시스를 실제로 검증하는 TC 기준)
    for b in tb:
        if not covered.get(b):
            errs.append(f"미커버 베이시스: {b}")

    # 분석표 vs TC
    for a in d.get("analysis", []):
        if a.get("technique") == "n/a":
            if not a.get("note"):
                errs.append(f"analysis {a.get('basis_id')}: n/a 사유(note) 필요")
            continue
        if a.get("basis_id") not in tb:
            errs.append(f"analysis: 존재하지 않는 베이시스 '{a.get('basis_id')}'")
        if a.get("tc_id") not in ids:
            errs.append(f"analysis {a.get('basis_id')}/{a.get('item')}: 검증 TC 없음/미존재({a.get('tc_id')})")

    # 베이시스 유형 vs 시트
    for t in tcs:
        for b in t.get("basis_ids", []):
            if b in tb and tb[b].get("type") != t.get("category") and not t.get("suggested"):
                warns.append(f"{t['id']}: 베이시스 {b} 유형({tb[b].get('type')})과 시트({t.get('category')}) 다름 — 의도 확인")
    return errs, warns, covered, tb


def build(d, covered, tb, out, errs, warns):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    cols = [(c["key"], c["header"]) for c in d["columns"]] if d.get("columns") else DEFAULT_COLS
    wb = Workbook()
    wb.remove(wb.active)
    head_fill = PatternFill("solid", fgColor="1F3864")
    sug_fill = PatternFill("solid", fgColor="FFF2CC")
    wrap = Alignment(wrap_text=True, vertical="top")

    def sheet(name, headers, rows, widths=None, hl=None):
        ws = wb.create_sheet(name)
        ws.append(headers)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = head_fill
            c.alignment = Alignment(wrap_text=True, vertical="center")
        for r in rows:
            ws.append(r)
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = wrap
            if hl and hl(row):
                for c in row:
                    c.fill = sug_fill
        for i, h in enumerate(headers, 1):
            w = (widths or {}).get(h, 22)
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = ws.dimensions
        return ws

    def row_of(t):
        sug = bool(t.get("suggested"))
        vals = {
            "id": t["id"], "basis": ", ".join(t.get("basis_ids", [])) or "(베이시스 보완 제안)",
            "title": ("[제안] " if sug else "") + t.get("title", ""),
            "purpose": t.get("purpose"), "precondition": t.get("precondition"),
            "inputs": t.get("inputs"), "steps": t.get("steps"), "expected": t.get("expected"),
            "techniques": ", ".join(t.get("techniques", [])), "suggested": "제안" if sug else "",
            "asil": t.get("asil", d.get("meta", {}).get("asil", "")), "priority": t.get("priority", ""),
            "env": t.get("env", d.get("meta", {}).get("env", "")), "result": "",
        }
        return [as_text(vals.get(k, t.get(k))) for k, _ in cols]

    sug_idx = next((i for i, (k, _) in enumerate(cols) if k == "suggested"), None)
    hl = (lambda row: row[sug_idx].value == "제안") if sug_idx is not None else None
    widths = {h: (45 if k in ("purpose", "inputs", "steps", "expected") else 22) for k, h in cols}
    for name, cat in (("기능 TC", "functional"), ("비기능 TC", "nonfunctional")):
        sheet(name, [h for _, h in cols], [row_of(t) for t in d["testcases"] if t.get("category") == cat],
              widths, hl)

    # 추적성
    rev = defaultdict(list)
    for t in d["testcases"]:
        for b in t.get("basis_ids", []):
            rev[b].append(t["id"] + ("(제안)" if t.get("suggested") else ""))
    tr = [[b, x.get("title", ""), x.get("type", ""), x.get("asil", ""), ", ".join(rev.get(b, [])),
           len(covered.get(b, [])), "Covered" if covered.get(b) else "NOT COVERED"] for b, x in tb.items()]
    sheet("추적성 매트릭스", ["베이시스 ID", "제목", "유형", "ASIL", "연결 TC", "비제안 TC 수", "상태"], tr)

    if d.get("analysis"):
        sheet("EP-BVA 분석", ["베이시스 ID", "파라미터", "기법", "클래스/경계", "값", "검증 TC", "비고"],
              [[a.get("basis_id"), a.get("parameter"), a.get("technique"), a.get("item"),
                a.get("value"), a.get("tc_id"), a.get("note")] for a in d["analysis"]])

    if d.get("pict"):
        rows = []
        for p in d["pict"]:
            rows.append([p.get("name"), p.get("order", 2), "[모델]", p.get("model")])
            rows.append([p.get("name"), p.get("order", 2), "[출력]", p.get("output")])
        sheet("PICT", ["이름", "order", "구분", "내용 (microsoft/pict)"], rows, {"내용 (microsoft/pict)": 90})

    n_tb = len(tb)
    n_cov = sum(1 for b in tb if covered.get(b))
    tcs = d["testcases"]
    summ = [
        ["프로젝트", d.get("meta", {}).get("project", "")],
        ["베이시스 문서", d.get("meta", {}).get("basis_doc", "")],
        ["베이시스 항목 수", n_tb],
        ["커버된 항목 수 (제안 TC 제외)", n_cov],
        ["베이시스 커버리지", f"{n_cov / n_tb * 100:.1f}%" if n_tb else "n/a"],
        ["TC 총수", len(tcs)],
        ["  기능", sum(t.get("category") == "functional" for t in tcs)],
        ["  비기능", sum(t.get("category") == "nonfunctional" for t in tcs)],
        ["  제안", sum(bool(t.get("suggested")) for t in tcs)],
        ["  WoW 검증", sum("WoW 검증" in t.get("techniques", []) for t in tcs)],
        ["베이시스 보완 제안 TC", sum(1 for t in tcs if t.get("suggested") and not t.get("basis_ids"))],
        ["검증 오류", len(errs)],
    ] + [["미해결 질문/가정", x] for x in d.get("open_issues", [])] + [["경고", w] for w in warns]
    ws = sheet("요약", ["항목", "값"], summ, {"항목": 34, "값": 80})
    wb.move_sheet("요약", offset=-(len(wb.sheetnames) - 1))
    wb.save(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("-o", "--out", default="SystemTestSpec.xlsx")
    ap.add_argument("--allow-gaps", action="store_true", help="검증 실패여도 xlsx 생성(커버리지 100% 주장 불가)")
    a = ap.parse_args()
    with open(a.json, encoding="utf-8") as f:
        d = json.load(f)
    errs, warns, covered, tb = validate(d)
    for e in errs:
        print("ERROR:", e)
    for w in warns:
        print("WARN :", w)
    n_cov = sum(1 for b in tb if covered.get(b))
    print(f"베이시스 커버리지 {n_cov}/{len(tb)}, TC {len(d.get('testcases', []))}개")
    if errs and not a.allow_gaps:
        print("검증 실패 — TC를 수정/추가 후 재실행하세요.")
        sys.exit(1)
    build(d, covered, tb, a.out, errs, warns)
    print("생성:", a.out, "(검증 오류 있음)" if errs else "(검증 통과)")


if __name__ == "__main__":
    main()
