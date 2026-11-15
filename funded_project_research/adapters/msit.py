"""과기정통부 R&D 공고 (data.go.kr 15074634). XML 고정, 브라우저 UA 필수.

마감일 필드 없음(pressDt 게시일만) → 신규 알림만. 고유키는 viewUrl의 nttSeqNo.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET

from .base import Adapter, RawNotice, SourceError, build_url, check_api_code, http_get

BASE = "https://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList"


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


class MsitAdapter(Adapter):
    source = "msit"

    def __init__(self, service_key: str | None = None, num_rows: int = 100, max_pages: int = 500):
        self.service_key = service_key or os.environ["SERVICE_KEY"]
        self.num_rows = num_rows
        self.max_pages = max_pages

    def collect(self) -> list[RawNotice]:
        def fetch(page):
            url = build_url(BASE, self.service_key,
                            {"pageNo": page, "numOfRows": self.num_rows})
            try:
                raw = http_get(url)
            except HTTPError:
                raise
            except (URLError, TimeoutError):
                raw = http_get(url)
            return ET.fromstring(raw.decode("utf-8"))

        out = self.begin()
        # The server caps pages at ten rows. Two bounded requests at a time
        # keep a full scan within the workflow budget without flooding the API.
        with ThreadPoolExecutor(max_workers=2) as pool:
            page = 1
            while page <= self.max_pages:
                end = min(page + (1 if page == 1 else 2), self.max_pages + 1)
                for root in pool.map(fetch, range(page, end)):
                    check_api_code(root.findtext(".//resultCode"))
                    if root.find(".//body") is None:
                        raise SourceError("schema")
                    items = root.findall(".//item")
                    self.add_page([_item_to_dict(it) for it in items], "viewUrl")
                    expected = root.findtext(".//totalCount")
                    if not items or expected and expected.isdigit() and len(out) >= int(expected):
                        self.check_total(expected)
                        return out
                page = end
        self.capped()
        return out
