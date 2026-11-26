# 중간 JSON 스키마 (build_xlsx.py 입력)

```json
{
  "meta": {"project": "", "version": "", "asil": "B", "env": "HIL", "basis_doc": ""},
  "columns": null,
  "test_basis": [
    {"id": "REQ-001", "title": "", "text": "", "type": "functional|nonfunctional", "asil": "B"}
  ],
  "analysis": [
    {"basis_id": "REQ-001", "parameter": "속도", "technique": "BVA|EP|n/a",
     "item": "경계 max (200km/h)", "value": "200", "note": "n/a이면 사유", "tc_id": "TC-F-003"}
  ],
  "testcases": [
    {"id": "TC-F-001", "basis_ids": ["REQ-001"], "category": "functional|nonfunctional",
     "title": "", "purpose": "", "precondition": "",
     "inputs": "속도=200 km/h (CAN 0x123 byte0=0xC8)",
     "steps": ["1. ...", "2. ..."],
     "expected": "10 ms 이내 경고등 ON",
     "techniques": ["경계값분석", "동치 클래스", "페어와이즈(PICT)", "WoW 검증"],
     "suggested": false, "asil": "B", "priority": "H|M|L", "env": "HIL"}
  ],
  "pict": [{"name": "", "model": "Param: a, b", "output": "tsv text", "order": 2}],
  "open_issues": ["질문/가정"]
}
```

- `techniques` 허용값: `경계값분석`, `동치 클래스`, `페어와이즈(PICT)`, `WoW 검증`, `요구사항 분석`, `오류 추정`, `결함 주입`.
- `steps`는 문자열 또는 배열. `suggested: true`는 ID가 `-S`로 끝나야 하며 시트에 "제안" 표시.
- 제안 TC가 어떤 TB에도 연결되지 않으면 `basis_ids: []` 허용(요약에 "베이시스 보완 제안"으로 집계, 커버리지 계산 제외).
- `columns`로 사용자 양식 지정: `[{"key":"id","header":"TC번호"}, ...]` (key는 id, basis, title, purpose, precondition, inputs, steps, expected, techniques, suggested, asil, priority, env, result).
- `analysis.tc_id`는 해당 클래스/경계를 검증하는 TC. 비어 있으면 누락으로 보고(n/a 제외).
