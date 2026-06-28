"""과기정통부 R&D 공고 (data.go.kr 15074634). XML 고정, 브라우저 UA 필수.

마감일 필드 없음(pressDt 게시일만) → 신규 알림만. 고유키는 viewUrl의 nttSeqNo.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET

from .base import Adapter, RawNotice, build_url, http_get

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

    def __init__(self, service_key: str | None = None, num_rows: int = 100, max_pages: int = 50):
        self.service_key = service_key or os.environ["SERVICE_KEY"]
        self.num_rows = num_rows
        self.max_pages = max_pages

    def collect(self) -> list[RawNotice]:
        out: list[RawNotice] = []
        for page in range(1, self.max_pages + 1):
            url = build_url(BASE, self.service_key,
                            {"pageNo": page, "numOfRows": self.num_rows})
            root = ET.fromstring(http_get(url).decode("utf-8"))
            items = root.findall(".//item")
            if not items:
                break
            out += [RawNotice(self.source, _item_to_dict(it)) for it in items]
        return out
