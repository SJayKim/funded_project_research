"""공고 상세HTML 본문 → 4필드 LLM 추출(tool_use 구조화 출력). 설계 Approach A.

이슈2 검증(2026-06-25 실측, Opus 4.8): body에 tools+tool_choice 허용,
stop_reason=tool_use로 단일 tool_use 블록 반환. 응답 파싱은 b["input"] dict.
(2026-06-27 추출 모델을 Sonnet 4.6으로 전환 — tool_choice 강제·tool_use 반환 동일.)
substring 검증은 enrich 단계(별도)에서 — 여기선 LLM 추출 + 상태 판정만.
"""
from __future__ import annotations

import os
import re

from . import anthropic_client
from .normalize import normalize_text

# 추출은 verbatim 충실·지시준수가 중요 → Sonnet(Opus와 Haiku 사이). summarize와 모델 분리.
MODEL = os.environ.get("EXTRACT_MODEL") or "claude-sonnet-4-6"
FIELDS = ("funding_amount", "eligibility", "required_docs", "key_dates")
MAX_BODY_CHARS = 20000  # LLM 입력 크기 상한(설계 §3 크기상한). 초과분 절단.


def html_to_text(raw: bytes | str) -> str:
    """상세 HTML → 본문 텍스트. script/style 본문 제거 → 태그 제거 → 엔티티/공백 정리 → 상한."""
    s = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)  # 스크립트/스타일 텍스트 노이즈 제거
    s = re.sub(r"(?s)<[^>]+>", " ", s)                          # 태그 제거
    return normalize_text(s)[:MAX_BODY_CHARS]                   # html.unescape + 공백 단일화 + 상한

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
            "key_dates": {"type": "string", "description": "접수·신청 기간 한 구절만 원문 그대로 복사. 여러 일정을 합치거나 형식·구분자를 바꾸지 말 것."},
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


def verify(vals: dict[str, str], body: str) -> dict[str, str]:
    """추출값이 원문(body)에 실제로 있는지 substring 검증. 없는 값은 버림(환각 차단, §5)."""
    return {f: (v if v and v in body else "") for f, v in vals.items()}


def extract_verified(body: str, api_key: str) -> tuple[dict[str, str], str]:
    """extract + substring verify + 전부탈락 시 no_info 강등. enrich·EVAL 공용."""
    vals, status = extract(body, api_key)
    vals = verify(vals, body)
    if status == "ok" and not any(vals.values()):
        status = "no_info"
    return vals, status
