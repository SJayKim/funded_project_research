"""K-Startup 사업공고 (data.go.kr 15125364). 자동승인, JSON.

마감일 pbanc_rcpt_end_dt (YYYYMMDD). 고유키 pbanc_sn. UA 불필요(있어도 무해).
"""
from __future__ import annotations

import os

from .base import Adapter, RawNotice, SourceError, build_url, check_api_code, http_get_json

BASE = "https://nidapi.k-startup.go.kr/api/kisedKstartupService/v1/getAnnouncementInformation"


class KStartupAdapter(Adapter):
    source = "kstartup"

    def __init__(self, service_key: str | None = None, per_page: int = 100, max_pages: int = 50):
        self.service_key = service_key or os.environ["SERVICE_KEY"]
        self.per_page = per_page
        self.max_pages = max_pages

    def collect(self) -> list[RawNotice]:
        out = self.begin()
        for page in range(1, self.max_pages + 1):
            url = build_url(BASE, self.service_key,
                            {"page": page, "perPage": self.per_page, "returnType": "json"})
            payload = http_get_json(url)
            if not isinstance(payload, dict) or "data" not in payload:
                raise SourceError("schema")
            check_api_code(payload.get("code"))
            data = payload["data"]
            self.add_page(data, "pbanc_sn")
            if not data:
                self.check_total(payload.get("matchCount", payload.get("totalCount")))
                break
        else:
            self.capped()
        return out
