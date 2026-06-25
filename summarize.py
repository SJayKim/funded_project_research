"""신규∩기술 공고 LLM 요약(Claude API, stdlib urllib). 키 없으면 규칙 fallback.

adapters/base.py의 urllib+ssl 패턴과 일관 — anthropic SDK 안 씀.
Opus 4.8 요청 계약: temperature/top_p/top_k/budget_tokens는 전부 제거됨(보내면 400).
그래서 body엔 model·max_tokens·system·messages만 넣는다.
"""
from __future__ import annotations

import os

import anthropic_client
from normalize import NoticeRecord

# 빈 문자열 secret(미설정 GH Actions)도 기본값으로 떨어지게 or 사용.
MODEL = os.environ.get("ANTHROPIC_MODEL") or "claude-opus-4-8"
SYSTEM = "당신은 정부 R&D·지원사업 공고를 한국 기업 담당자에게 1~2문장으로 요약하는 비서다. 핵심 지원내용과 대상만, 군더더기 없이."


def _prompt(rec: NoticeRecord) -> str:
    return (
        "다음 정부과제 공고를 1~2문장으로 요약하라.\n"
        f"공고명: {rec.title}\n"
        f"소관부처: {rec.agency}\n"
        f"신청대상: {rec.target or '미상'}\n"
        f"접수마감: {rec.deadline or '상시/미상'}"
    )


def _fallback(rec: NoticeRecord) -> str:
    cat = rec.category or "기술"
    return f"{rec.agency} {cat} 분야 지원사업 (마감 {rec.deadline or '상시'})"


def _anthropic_message(prompt: str, api_key: str) -> str:
    data = anthropic_client.post_message({
        "model": MODEL,
        "max_tokens": 200,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }, api_key)
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    ).strip()


def summarize(records: list[NoticeRecord]) -> dict[str, str]:
    """key -> 요약. API 키 없으면 전건 fallback(네트워크 호출 0). 건별 실패도 fallback."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    out: dict[str, str] = {}
    for rec in records:
        if not api_key:
            out[rec.key] = _fallback(rec)
            continue
        try:
            out[rec.key] = _anthropic_message(_prompt(rec), api_key) or _fallback(rec)
        except Exception:
            out[rec.key] = _fallback(rec)
    return out
