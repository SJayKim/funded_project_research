"""Anthropic /v1/messages 공용 호출부(stdlib urllib). summarize·extract 공유.

설계 이슈5: body 구성(요약=text, 추출=tools)과 응답 파싱(text-join vs tool_use)은
호출부가 한다. 여기선 POST + json 디코드만 공유한다.
Opus 4.8 계약: temperature/top_p/top_k/budget_tokens는 보내면 400 — body에 넣지 말 것.
"""
from __future__ import annotations

import json
import urllib.request

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


def post_message(body: dict, api_key: str, timeout: int = 30) -> dict:
    """messages API POST → 응답 JSON dict. 파싱은 호출부."""
    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))
