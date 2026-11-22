"""과기정통부 R&D 공고 (data.go.kr 15074634). XML 고정, 브라우저 UA 필수.

마감일 필드 없음(pressDt 게시일만) → 신규 알림만. 고유키는 viewUrl의 nttSeqNo.
"""
from __future__ import annotations

import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from math import ceil
from time import monotonic
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET

from .base import Adapter, RawNotice, SourceError, build_url, check_api_code, http_get

BASE = "https://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList"
COLLECT_BUDGET_SECONDS = 12 * 60
MAX_RECOVERY_PAGES = 12


class _PageError(SourceError):
    """페이지 단위로 재시도할 수 있는 오류."""


def _item_to_dict(item: ET.Element) -> dict:
    d: dict = {}
    files = []
    for child in item:
        if child.tag == "files":
            for f in child.findall("file"):
                files.append({c.tag: (c.text or "") for c in f})
        else:
            d[child.tag] = child.text or ""
    d["files"] = files
    return d


def _notice_id(row: dict) -> str:
    url = row["viewUrl"]
    match = re.search(r"nttSeqNo=(\d+)", url)
    return match.group(1) if match else url


class MsitAdapter(Adapter):
    source = "msit"

    def __init__(self, service_key: str | None = None, num_rows: int = 100, max_pages: int = 500):
        self.service_key = service_key or os.environ["SERVICE_KEY"]
        self.num_rows = num_rows
        self.max_pages = max_pages

    def _fetch_page(self, page: int) -> tuple[list[dict], int | None]:
        url = build_url(BASE, self.service_key, {"pageNo": page, "numOfRows": self.num_rows})
        try:
            root = ET.fromstring(http_get(url))
        except ET.ParseError:
            raise _PageError("schema") from None
        except HTTPError as error:
            if 500 <= error.code < 600:
                raise _PageError(f"http_{error.code}") from None
            raise SourceError(f"http_{error.code}") from None

        if root.tag == "OpenAPI_ServiceResponse":
            code = (root.findtext(".//returnReasonCode") or "").strip()
            reason = f"provider_{code}" if re.fullmatch(r"[0-9]{2}", code) else "provider_error"
            # 04 (HTTP_ERROR) can affect one upstream page while adjacent pages work.
            if code == "04":
                raise _PageError(reason)
            raise SourceError(reason)

        if root.tag != "response":
            raise _PageError("schema")
        check_api_code(root.findtext("./header/resultCode"))
        body = root.find("body")
        if body is None:
            raise _PageError("schema")
        total_text = (body.findtext(".//totalCount") or "").strip()
        total = int(total_text) if total_text.isdecimal() else None
        if body.find(".//items") is None and total != 0:
            raise _PageError("schema")
        page_text = body.findtext(".//pageNo")
        if page_text is not None and page_text.strip() != str(page):
            raise _PageError("page_number_mismatch")
        rows = [_item_to_dict(item) for item in body.findall(".//items/item")]
        if any(not row.get("viewUrl") for row in rows):
            raise _PageError("schema")
        return rows, total

    def collect(self) -> list[RawNotice]:
        out = self.begin()
        deadline = monotonic() + COLLECT_BUDGET_SECONDS
        if self.max_pages < 1:
            self.capped()
            return out

        try:
            first, expected = self._fetch_page(1)
        except (_PageError, URLError, TimeoutError):
            # Page one establishes the bounds for subsequent requests.
            try:
                first, expected = self._fetch_page(1)
            except SourceError as error:
                raise SourceError(f"page_1_{error}") from None
        except SourceError as error:
            raise SourceError(f"page_1_{error}") from None
        if not first:
            self.add_page(first, "viewUrl")
            self.check_total(expected)
            return out

        page_size = len(first)  # The provider caps the requested size at ten rows.
        expected_pages = max(1, ceil(expected / page_size)) if expected is not None else None
        last_page = min(self.max_pages, expected_pages or self.max_pages)
        pages = {1: first}
        missing: dict[int, str] = {}
        stop_reason = ""

        def accept(page: int, result: tuple[list[dict], int | None]) -> bool:
            rows, total = result
            if expected is not None:
                if total is not None and total != expected:
                    raise _PageError("total_changed")
                expected_size = min(page_size, expected - (page - 1) * page_size)
                if len(rows) != expected_size:
                    raise _PageError("page_count_mismatch")
            pages[page] = rows
            return bool(rows)

        # Keep two requests in flight and collect later pages even after a page-local error.
        with ThreadPoolExecutor(max_workers=2) as pool:
            reached_end = expected_pages == 1
            source_error = False
            for start in range(2, last_page + 1, 2):
                if monotonic() >= deadline:
                    stop_reason = "time_limit"
                    break
                batch = range(start, min(start + 2, last_page + 1))
                results = [(page, pool.submit(self._fetch_page, page)) for page in batch]
                for page, future in results:
                    try:
                        reached_end = not accept(page, future.result()) or reached_end
                    except _PageError as error:
                        missing[page] = str(error)
                    except (URLError, TimeoutError):
                        missing[page] = "network"
                    except SourceError as error:
                        missing[page] = str(error)
                        source_error = True
                if reached_end or source_error:
                    break

            if not stop_reason and not source_error and not reached_end:
                if expected_pages is None or expected_pages > self.max_pages:
                    stop_reason = "page_limit"

            if missing and not source_error:
                known_ids = {_notice_id(row) for rows in pages.values() for row in rows}
                for page in list(missing)[:MAX_RECOVERY_PAGES]:
                    if monotonic() >= deadline:
                        stop_reason = "time_limit"
                        break
                    try:
                        result = self._fetch_page(page)
                        recovered_ids = {_notice_id(row) for row in result[0]}
                        if len(recovered_ids) != len(result[0]) or recovered_ids & known_ids:
                            raise _PageError("duplicate_notices")
                        accept(page, result)
                    except _PageError as error:
                        missing[page] = str(error)
                    except (URLError, TimeoutError):
                        missing[page] = "network"
                    except SourceError as error:
                        missing[page] = str(error)
                        break
                    else:
                        first_reason = missing.pop(page)
                        known_ids.update(recovered_ids)
                        print(f"[info] MsitAdapter: page {page} recovered ({first_reason})", file=sys.stderr)

        seen = set()
        for page, rows in sorted(pages.items()):
            unique = []
            for row in rows:
                notice_id = _notice_id(row)
                if notice_id in seen:
                    missing[page] = "duplicate_notices"
                    continue
                seen.add(notice_id)
                unique.append(row)
            self.add_page(unique, "viewUrl")

        self.check_total(expected)
        reasons = [f"page_{page}_{reason}" for page, reason in sorted(missing.items())]
        if stop_reason:
            reasons.append(stop_reason)
        if reasons:
            self.collection_state = "partial"
            self.collection_error = ", ".join(reasons)
        return out
