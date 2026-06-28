"""기업마당 미러 (data.go.kr odcloud 3034791). 자동승인, JSON.

신청종료일자(한글 키) YYYY-MM-DD. 연간 스냅샷(2025-03)이라 신선도 한계 — 1주차 그대로 포함.
"""
from __future__ import annotations

import os
import time

from .base import Adapter, RawNotice, build_url, http_get_json

BASE = "https://api.odcloud.kr/api/3034791/v1/uddi:fa09d13d-bce8-474e-b214-8008e79ec08f"

# odcloud은 연속 호출을 rate-limit으로 차단한다(실측 2026-06-22: 간격 없이 5페이지째
# code:-999 UNKNOWN 400, 0.6s 간격이면 통과). 페이지 사이 지연으로 적정 호출간격 준수.
PAGE_DELAY_SEC = 0.8


class BizinfoAdapter(Adapter):
    source = "bizinfo"

    def __init__(self, service_key: str | None = None, per_page: int = 100, max_pages: int = 50):
        self.service_key = service_key or os.environ["SERVICE_KEY"]
        self.per_page = per_page
        self.max_pages = max_pages

    def collect(self) -> list[RawNotice]:
        out: list[RawNotice] = []
        for page in range(1, self.max_pages + 1):
            if page > 1:
                time.sleep(PAGE_DELAY_SEC)
            url = build_url(BASE, self.service_key,
                            {"page": page, "perPage": self.per_page, "returnType": "JSON"})
            data = http_get_json(url).get("data") or []
            if not data:
                break
            out += [RawNotice(self.source, r) for r in data]
        return out
