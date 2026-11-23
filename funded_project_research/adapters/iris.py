"""IRIS 범부처통합연구지원 R&D 공고 스크래퍼. POST + 브라우저 헤더 게이트.

목록 POST /retrieveBsnsAncmListView.do (pageIndex 순회, 11행/페이지, 서버렌더 HTML).
상세 POST /retrieveBsnsAncmView.do 로 공고번호·첨부 보강.
주의: retrieveBsnsAncmBtinSituListView.do(JSON 기대)는 항상 HTML → 사용 금지(함정).
파싱은 stdlib 정규식(행 구조 규칙적, 의존성 추가 안 함). (실측 2026-06-22)
"""
from __future__ import annotations

import re
import time
from urllib.error import HTTPError
from urllib.parse import urlencode

from .base import Adapter, RawNotice, SourceError, http_post, http_get
from .retry import (
    CONSECUTIVE_FAILURE_LIMIT, REQUEST_ERRORS, RequestTimeLimit, SourceRequests,
    request_error_kind, transient,
)

BASE = "https://www.iris.go.kr/contents"
LIST_URL = f"{BASE}/retrieveBsnsAncmListView.do"
VIEW_URL = f"{BASE}/retrieveBsnsAncmView.do"

# 한 행(<li>)의 평면 필드. inst_title(소관부처 > 전담기관) → 공고명 onclick 인자 → 접수기간.
_ROW = re.compile(
    r'<span class="inst_title">(?P<inst>[^<]*)</span>.*?'
    r"f_bsnsAncmListForm_view\((?P<args>[^)]*)\).*?>(?P<title>[^<]*)</a>.*?"
    r'<span class="period"[^>]*>(?P<period>[^<]*)</span>',
    re.S,
)
_TOTAL_PAGES = re.compile(r'current_page">[^<]*<strong>\d+</strong>/(\d+)')
_ANCM_NO = re.compile(r"<em>공고번호</em><span>([^<]*)</span>")
# downloadAtchFile('docId','fileId','fileNm','fileSz') — 3번째 인자가 파일명.
_ATCH = re.compile(r"downloadAtchFile\('[^']*','[^']*','([^']*)'")


def parse_rows(html: str) -> list[dict]:
    # The page also embeds a JSRender row template; it is not a notice.
    html = re.sub(r'<script\b[^>]*>.*?</script\s*>', '', html, flags=re.S | re.I)
    rows = []
    for m in _ROW.finditer(html):
        args = [a.strip().strip("'") for a in m.group("args").split(",")]
        # f_bsnsAncmListForm_view(ancmId, bsnsYy, sorgnBsnsCd, bsnsAncmSn, dDay, rcveStrDt, rcveEndDt)
        inst = m.group("inst")
        sorgn, _, spcl = inst.partition(" > ")
        rows.append({
            "ancmId": args[0],
            "bsnsYy": args[1],
            "sorgnBsnsCd": args[2],
            "bsnsAncmSn": args[3],
            "rcveStrDt": args[5] if len(args) > 5 else "",
            "rcveEndDt": args[6] if len(args) > 6 else "",
            "ancmTl": m.group("title"),
            "sorgn": sorgn,
            "spcl": spcl,
        })
    return rows


def parse_detail(html: str) -> dict:
    no = _ANCM_NO.search(html)
    return {
        "ancmNo": no.group(1).strip() if no else "",
        "attachments": " ".join(_ATCH.findall(html)),
    }


class IrisAdapter(Adapter):
    source = "iris"

    def __init__(self, max_pages: int = 15, detail: bool = True, interval: float = 0.5):
        self.max_pages = max_pages
        self.detail = detail
        self.interval = interval

    def collect(self) -> list[RawNotice]:
        out = self.begin()
        requests = SourceRequests(self.source)
        first = self._fetch_list(requests, 1)
        m = _TOTAL_PAGES.search(first)
        rows = parse_rows(first)
        if not m or not rows:
            raise SourceError("unverified_empty_page")
        total = min(int(m.group(1)), self.max_pages)
        self.add_page(rows, "ancmId")
        if int(m.group(1)) > self.max_pages:
            self.capped()
        consecutive_failures = 0
        for page in range(2, total + 1):
            try:
                html = self._fetch_list(requests, page)
            except REQUEST_ERRORS as error:
                if not isinstance(error, RequestTimeLimit) and not transient(error):
                    raise
                self.collection_state = "partial"
                self.collection_error = f"list_{request_error_kind(error)}"
                consecutive_failures += 1
                if isinstance(error, RequestTimeLimit) or consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                    break
                continue
            consecutive_failures = 0
            page_rows = parse_rows(html)
            if not page_rows:
                raise SourceError("unverified_empty_page")
            self.add_page(page_rows, "ancmId")

        if self.detail:
            self._collect_details(requests, out)

        return out

    @staticmethod
    def _fetch_list(requests: SourceRequests, page: int) -> str:
        return requests.fetch("list", f"page={page}", http_post, LIST_URL, {"pageIndex": page}).decode("utf-8")

    def _collect_details(self, requests: SourceRequests, rows: list[RawNotice]) -> None:
        def fetch_detail(fields, timeout):
            started = time.monotonic()
            try:
                raw = http_post(VIEW_URL, fields, timeout=min(timeout, 10))
            except REQUEST_ERRORS as error:
                left = timeout - (time.monotonic() - started)
                if not transient(error) or left <= 0 or requests.retries_left <= 0:
                    raise
                # The public detail link accepts the same identifiers as GET.
                # Share one request deadline; never fall back after access denial.
                requests.retries_left -= 1
                raw = http_get(VIEW_URL + "?" + urlencode(fields), timeout=left)
            html = raw.decode("utf-8")
            detail = parse_detail(html)
            if not any(detail.values()):
                raise SourceError("unverified_empty_detail")
            return detail

        previous_state = (self.collection_state, self.collection_error)
        missing = []
        stopped = False
        consecutive_failures = 0
        for index, rec in enumerate(rows, start=1):
            row = rec.raw
            notice_id = row["ancmId"]
            target = f"notice={notice_id}" if notice_id.isascii() and notice_id.isdecimal() else f"row={index}"
            sequence = row["bsnsAncmSn"]
            if sequence.isascii() and sequence.isdecimal():
                target += f" sequence={sequence}"
            fields = {key: row[key] for key in ("ancmId", "bsnsYy", "sorgnBsnsCd", "bsnsAncmSn")}
            fields["bsnsYyDetail"] = row["bsnsYy"]
            try:
                row.update(requests.fetch("detail", target, fetch_detail, fields))
                consecutive_failures = 0
            except REQUEST_ERRORS as error:
                if transient(error):
                    missing.append((row, target, fields))
                else:
                    stopped = True
                self.collection_state = "partial"
                if self.collection_error in ("", "page_limit"):
                    self.collection_error = f"detail_{request_error_kind(error)}"
                consecutive_failures += 1
                if (isinstance(error, RequestTimeLimit) or consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT
                        or isinstance(error, HTTPError) and error.code in (401, 403, 429)):
                    stopped = True
                    break
            if index < len(rows):
                time.sleep(self.interval)

        if missing and not stopped:
            unresolved = []
            for row, target, fields in missing:
                try:
                    row.update(requests.recover("detail-recovery", target, fetch_detail, fields))
                except REQUEST_ERRORS as error:
                    unresolved.append(error)
                    if isinstance(error, RequestTimeLimit) or not transient(error):
                        break
            if not unresolved:
                self.collection_state, self.collection_error = previous_state
