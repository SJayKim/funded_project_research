"""기업마당 라이브 OpenAPI (bizinfoApi.do). crtfcKey 인증, JSON.

신청기간 reqstBeginEndDe는 "시작 ~ 종료" 범위 문자열 — 종료일을 마감으로 정규화.
공고 ID pblancId(PBLN_*)는 구 정적 스냅샷 URL의 pblancId와 동일 → DB key 보존.
"""
from __future__ import annotations

import os
import time
from urllib.parse import urlencode

from .base import Adapter, RawNotice, http_get_json

BASE = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"

# crtfcKey rate limit 미공개 — 페이지 간 courtesy delay 유지.
PAGE_DELAY_SEC = 0.8


class BizinfoAdapter(Adapter):
    source = "bizinfo"

    def __init__(self, crtfc_key: str | None = None, per_page: int = 100, max_pages: int = 50):
        self.crtfc_key = crtfc_key or os.environ["BIZINFO_CRTFC_KEY"]
        self.per_page = per_page
        self.max_pages = max_pages

    def collect(self) -> list[RawNotice]:
        out: list[RawNotice] = []
        for page in range(1, self.max_pages + 1):
            if page > 1:
                time.sleep(PAGE_DELAY_SEC)
            url = f"{BASE}?{urlencode({'crtfcKey': self.crtfc_key, 'dataType': 'json', 'pageUnit': self.per_page, 'pageIndex': page})}"
            items = http_get_json(url).get("jsonArray") or []
            if not items:
                break
            out += [RawNotice(self.source, r) for r in items]
        return out
