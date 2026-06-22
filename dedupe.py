"""중복제거. boam79 3단계 차용.

1) 소스내 고유키 {source}:{source_id}
2) cross-source: 정규화 title+agency 정확매칭 → Jaccard≥0.75
"""
from __future__ import annotations

import re

from normalize import NoticeRecord

JACCARD_THRESHOLD = 0.75


def _tokens(rec: NoticeRecord) -> set[str]:
    text = f"{rec.title} {rec.agency}".lower()
    return set(t for t in re.split(r"\W+", text) if t)


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def dedupe_within_source(records: list[NoticeRecord]) -> list[NoticeRecord]:
    """소스내 키 기준 중복 제거(먼저 본 것 유지)."""
    seen: set[str] = set()
    out: list[NoticeRecord] = []
    for r in records:
        if r.key in seen:
            continue
        seen.add(r.key)
        out.append(r)
    return out


def dedupe_cross_source(records: list[NoticeRecord]) -> list[NoticeRecord]:
    """다른 소스 간 동일 공고 제거(정확매칭 또는 Jaccard≥0.75).

    같은 소스 레코드끼리는 비교하지 않는다(소스내 중복은 위에서 처리).
    """
    kept: list[NoticeRecord] = []
    kept_tokens: list[set[str]] = []
    for r in records:
        rt = _tokens(r)
        norm = (r.title.lower().strip(), r.agency.lower().strip())
        dup = False
        for k, kt in zip(kept, kept_tokens):
            if k.source == r.source:
                continue
            if (k.title.lower().strip(), k.agency.lower().strip()) == norm:
                dup = True
                break
            if jaccard(kt, rt) >= JACCARD_THRESHOLD:
                dup = True
                break
        if not dup:
            kept.append(r)
            kept_tokens.append(rt)
    return kept


def dedupe(records: list[NoticeRecord]) -> list[NoticeRecord]:
    return dedupe_cross_source(dedupe_within_source(records))
