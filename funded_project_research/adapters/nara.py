"""나라장터 용역 입찰공고 (data.go.kr 15129394). 브라우저 UA 필수.

마감일 bidClseDt (YYYY-MM-DD HH:MM:SS). 고유키 bidNtceNo.
조회구간 inqryBgnDt/inqryEndDt(YYYYMMDDHHMM) 필수 → 최근 lookback_days.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from .base import Adapter, RawNotice, SourceError, build_url, check_api_code, http_get_json
from ..status import KST

BASE = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc"


class NaraAdapter(Adapter):
    source = "nara"

    def __init__(
        self,
        service_key: str | None = None,
        num_rows: int = 100,
        max_pages: int = 50,
        lookback_days: int = 7,
        now: datetime | None = None,
    ):
        self.service_key = service_key or os.environ["SERVICE_KEY"]
        self.num_rows = num_rows
        self.max_pages = max_pages
        self.lookback_days = lookback_days
        self.now = now or datetime.now(KST)

    def collect(self) -> list[RawNotice]:
        bgn = (self.now - timedelta(days=self.lookback_days)).strftime("%Y%m%d") + "0000"
        end = self.now.strftime("%Y%m%d%H%M")
        out = self.begin()
        for page in range(1, self.max_pages + 1):
            url = build_url(BASE, self.service_key,
                            {"pageNo": page, "numOfRows": self.num_rows, "inqryDiv": 1,
                             "inqryBgnDt": bgn, "inqryEndDt": end, "type": "json"})
            response = http_get_json(url).get("response", {})
            check_api_code(response.get("header", {}).get("resultCode"))
            body = response.get("body", {})
            if "items" not in body:
                raise SourceError("schema")
            items = body["items"]
            if items == "" and str(body.get("totalCount")) == "0":
                items = []
            self.add_page(items, "bidNtceNo")
            if not items:
                self.check_total(body.get("totalCount"))
                break
        else:
            self.capped()
        return out
