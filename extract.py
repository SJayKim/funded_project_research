"""공고 상세HTML 본문 → 4필드 LLM 추출(tool_use 구조화 출력). 설계 Approach A.

이슈2 검증(2026-06-25 실측): Opus 4.8은 body에 tools+tool_choice 허용,
stop_reason=tool_use로 단일 tool_use 블록 반환. 응답 파싱은 b["input"] dict.
substring 검증은 enrich 단계(별도)에서 — 여기선 LLM 추출 + 상태 판정만.
"""
from __future__ import annotations

import os

import anthropic_client
from normalize import normalize_text

MODEL = os.environ.get("ANTHROPIC_MODEL") or "claude-opus-4-8"
FIELDS = ("funding_amount", "eligibility", "required_docs", "key_dates")

SYSTEM = (
    "당신은 정부 R&D·지원사업 공고 본문에서 4필드를 발췌하는 추출기다. "
    "원문에 그대로 있는 표현만 발췌하고, 없는 필드는 빈 문자열로 둔다. 추측·요약·창작 금지."
)
TOOL = {
    "name": "extract_notice",
    "description": "공고 본문에서 지원금액·신청자격·제출서류·주요일정 4필드를 발췌. 없으면 빈 문자열.",
    "input_schema": {
        "type": "object",
        "properties": {
            "funding_amount": {"type": "string", "description": "지원규모·금액 발췌"},
            "eligibility": {"type": "string", "description": "신청자격·지원대상 발췌"},
            "required_docs": {"type": "string", "description": "제출서류 발췌"},
            "key_dates": {"type": "string", "description": "접수기간·주요일정 발췌"},
        },
        "required": list(FIELDS),
    },
}


def extract(body_text: str, api_key: str) -> tuple[dict[str, str], str]:
    """본문 → ({4필드: 발췌}, status). status: ok / no_info / failed.

    예외(네트워크·파싱·tool_use 블록 없음) → ({}, "failed").
    전 필드 공란 → no_info. 하나라도 값 → ok.
    """
    try:
        data = anthropic_client.post_message({
            "model": MODEL,
            "max_tokens": 1024,
            "system": SYSTEM,
            "tools": [TOOL],
            "tool_choice": {"type": "tool", "name": "extract_notice"},
            "messages": [{"role": "user", "content": f"다음 공고 본문에서 4필드를 발췌하라.\n\n{body_text}"}],
        }, api_key)
    except Exception:
        return {}, "failed"

    block = next((b for b in data.get("content", []) if b.get("type") == "tool_use"), None)
    if block is None:
        return {}, "failed"
    raw = block.get("input") or {}
    vals = {f: normalize_text(raw.get(f)) for f in FIELDS}
    if not any(vals.values()):
        return vals, "no_info"
    return vals, "ok"
