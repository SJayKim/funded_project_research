"""나라장터 용역 입찰공고 (data.go.kr 15129394). 브라우저 UA 필수.

마감일 bidClseDt (YYYY-MM-DD HH:MM:SS). 고유키 bidNtceNo.
조회구간 inqryBgnDt/inqryEndDt(YYYYMMDDHHMM) 필수 → 최근 lookback_days.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from .base import Adapter, RawNotice, SourceError, build_url, check_api_code, http_get_json
from .retry import (
    CONSECUTIVE_FAILURE_LIMIT, REQUEST_ERRORS, RequestTimeLimit, SourceRequests,
    request_error_kind, transient,
)
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
        # The API counts both boundary dates in its seven-day limit.
        bgn = (self.now - timedelta(days=self.lookback_days - 1)).strftime("%Y%m%d") + "0000"
        end = self.now.strftime("%Y%m%d%H%M")
        out = self.begin()
        requests = SourceRequests(self.source)
        missing_kind = ""
        consecutive_failures = 0
        for page in range(1, self.max_pages + 1):
            url = build_url(BASE, self.service_key,
                            {"pageNo": page, "numOfRows": self.num_rows, "inqryDiv": 1,
                             "inqryBgnDt": bgn, "inqryEndDt": end, "type": "json"})
            try:
                response = requests.fetch("list", f"page={page}", http_get_json, url).get("response", {})
            except REQUEST_ERRORS as error:
                if not isinstance(error, RequestTimeLimit) and not transient(error):
                    raise
                missing_kind = request_error_kind(error)
                consecutive_failures += 1
                if isinstance(error, RequestTimeLimit) or consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                    break
                continue
            consecutive_failures = 0
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
        if missing_kind:
            self.collection_state = "partial" if out else "failed"
            self.collection_error = f"list_{missing_kind}"
        return out
