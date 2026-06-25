"""extract 프롬프트 회귀 평가셋(EVAL, 설계 이슈6·§4). fixture별 추출→golden 대조.

fixture(JSON, tests/fixtures/extract/*.json):
  {source, id, url, golden{4필드}, expected_status, body}
- 양성(ok): golden 비어있지 않은 필드는 추출돼야(recall) + 추출값↔golden 겹침.
- 음성(no_info): 추출 전부 공란이어야(환각 금지). status도 expected와 일치.

실모델 호출이라 ANTHROPIC_API_KEY 필요. 키 없으면 호출부에서 skip(일반 테스트런은 안 돌림).
스코어링(score)은 모델 없이 결정적 — 단위테스트가 이 함수만 검증.
"""
from __future__ import annotations

import glob
import json
import os

import extract

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "tests", "fixtures", "extract")


def load_fixtures(d: str = FIXTURE_DIR) -> list[dict]:
    out = []
    for p in sorted(glob.glob(os.path.join(d, "*.json"))):
        with open(p, encoding="utf-8") as f:
            out.append(json.load(f))
    return out


def score(fixture: dict, vals: dict, status: str) -> dict:
    """fixture 1건 채점 → {id, passed, reasons}. 모델 무관, 결정적."""
    reasons = []
    if status != fixture["expected_status"]:
        reasons.append(f"status {status} != {fixture['expected_status']}")
    golden = fixture.get("golden", {})
    vals = vals or {}
    if fixture["expected_status"] == "no_info":
        for f in extract.FIELDS:
            if vals.get(f):
                reasons.append(f"{f}: 음성케이스인데 값 추출됨('{vals[f]}')")  # 환각
    else:  # ok
        for f in extract.FIELDS:
            g = golden.get(f, "")
            if not g:
                continue
            v = vals.get(f, "")
            if not v:
                reasons.append(f"{f}: golden 있는데 미추출")
            elif g not in v and v not in g:
                reasons.append(f"{f}: golden 불일치(golden='{g}' vs '{v}')")
    return {"id": f"{fixture['source']}_{fixture['id']}", "passed": not reasons, "reasons": reasons}


def run(fixtures: list[dict], api_key: str) -> list[dict]:
    """fixture 전체에 실모델 추출 파이프라인(extract_verified) 실행 후 채점."""
    results = []
    for fx in fixtures:
        vals, status = extract.extract_verified(fx["body"], api_key)
        results.append(score(fx, vals, status))
    return results


def main() -> int:
    import sys
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("ANTHROPIC_API_KEY 필요(실모델 호출)")
        return 1
    results = run(load_fixtures(), key)
    for r in results:
        print(("PASS" if r["passed"] else "FAIL"), r["id"], "; ".join(r["reasons"]))
    fails = [r for r in results if not r["passed"]]
    print(f"{len(results) - len(fails)}/{len(results)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
