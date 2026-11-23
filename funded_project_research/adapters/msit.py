"""과기정통부 R&D 공고 (data.go.kr 15074634). XML에서 HTTP_ERROR가 나면 JSON 사용.

마감일 필드 없음(pressDt 게시일만) → 신규 알림만. 고유키는 viewUrl의 nttSeqNo.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from math import ceil
from time import monotonic
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET

from .retry import transient
from .base import Adapter, RawNotice, SourceError, build_url, check_api_code, http_get

BASE = "https://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList"
COLLECT_BUDGET_SECONDS = 12 * 60
MAX_RECOVERY_PAGES = 12
PROVIDER_HTTP_ERROR = "provider_04"


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


def _json_objects(values, label: str) -> list[dict]:
    if values is None or values == "":
        return []
    if not isinstance(values, list):
        raise _PageError("json_schema")
    objects = []
    for wrapper in values:
        obj = wrapper.get(label) if isinstance(wrapper, dict) else None
        if not isinstance(obj, dict):
            raise _PageError("json_schema")
        objects.append(obj)
    return objects


def _json_text_fields(fields: dict) -> dict:
    if any(value is not None and not isinstance(value, (str, int, float, bool)) for value in fields.values()):
        raise _PageError("json_schema")
    return {key: str(value) if value is not None else "" for key, value in fields.items()}


def _json_page(raw: bytes, page: int, page_size: int) -> tuple[list[dict], int]:
    # The provider represents response, items and files as lists of wrapped objects.
    try:
        parts = json.loads(raw)["response"]
        header, = [part["header"] for part in parts if "header" in part]
        body, = [part["body"] for part in parts if "body" in part]
        code = str(header["resultCode"])
        total = str(body["totalCount"])
        actual_page = str(body["pageNo"])
        actual_size = str(body["numOfRows"])
        items = body["items"]
    except (KeyError, TypeError, ValueError):
        raise _PageError("json_schema") from None

    check_api_code(code)
    if actual_page != str(page):
        raise _PageError("page_number_mismatch")
    if actual_size != str(page_size):
        raise _PageError("page_size_mismatch")
    if not re.fullmatch(r"[0-9]{1,10}", total):
        raise _PageError("json_schema")

    rows = []
    for item in _json_objects(items, "item"):
        files = _json_objects(item.get("files"), "file")
        row = _json_text_fields({key: value for key, value in item.items() if key != "files"})
        row["files"] = [_json_text_fields(file) for file in files]
        if not isinstance(item.get("viewUrl"), str) or not _notice_id(row).isdecimal():
            raise _PageError("json_schema")
        rows.append(row)
    return rows, int(total)


class MsitAdapter(Adapter):
    source = "msit"

    def __init__(self, service_key: str | None = None, num_rows: int = 100, max_pages: int = 500):
        self.service_key = service_key or os.environ["SERVICE_KEY"]
        self.num_rows = num_rows
        self.max_pages = max_pages

    def _fetch_page(self, page: int, *, json_page_size: int | None = None) -> tuple[list[dict], int | None]:
        params = {"pageNo": page, "numOfRows": self.num_rows}
        if json_page_size is not None:
            params.update(numOfRows=json_page_size, returnType="json")
        url = build_url(BASE, self.service_key, params)
        try:
            raw = http_get(url)
        except HTTPError as error:
            if 500 <= error.code < 600:
                raise _PageError(f"http_{error.code}") from None
            raise SourceError(f"http_{error.code}") from None

        if json_page_size is not None and not raw.lstrip().startswith(b"<"):
            return _json_page(raw, page, json_page_size)
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            raise _PageError("schema") from None
        if root.tag == "OpenAPI_ServiceResponse":
            code = (root.findtext(".//returnReasonCode") or "").strip()
            reason = f"provider_{code}" if re.fullmatch(r"[0-9]{2}", code) else "provider_error"
            # 04 (HTTP_ERROR) can affect one upstream page while adjacent pages work.
            if reason == PROVIDER_HTTP_ERROR:
                raise _PageError(reason)
            raise SourceError(reason)

        if json_page_size is not None:
            raise _PageError("expected_json")
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
        json_page_size = None

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
                results = [(page, pool.submit(self._fetch_page, page, json_page_size=json_page_size))
                           for page in batch]
                for page, future in results:
                    try:
                        reached_end = not accept(page, future.result()) or reached_end
                    except _PageError as error:
                        missing[page] = str(error)
                        # Multiple later XML pages can fail with the same provider error.
                        # Use the verified offset and total for subsequent JSON requests.
                        if json_page_size is None and expected is not None and missing[page] == PROVIDER_HTTP_ERROR:
                            json_page_size = page_size
                            print(f"[info] MsitAdapter: using JSON after page {page} ({PROVIDER_HTTP_ERROR})",
                                  file=sys.stderr)
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
                    first_reason = missing[page]
                    try:
                        for attempt in range(3):
                            try:
                                result = self._fetch_page(page, json_page_size=json_page_size)
                                break
                            except (URLError, TimeoutError) as error:
                                delay = 2 ** attempt
                                if not transient(error) or attempt == 2 or monotonic() + delay + 30 >= deadline:
                                    raise
                                time.sleep(delay)
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
                        del missing[page]
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
