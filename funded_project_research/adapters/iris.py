"""IRIS 범부처통합연구지원 R&D 공고 스크래퍼. POST + 브라우저 헤더 게이트.

목록 POST /retrieveBsnsAncmListView.do (pageIndex 순회, 11행/페이지, 서버렌더 HTML).
상세 POST /retrieveBsnsAncmView.do 로 공고번호·첨부 보강.
주의: retrieveBsnsAncmBtinSituListView.do(JSON 기대)는 항상 HTML → 사용 금지(함정).
파싱은 stdlib 정규식(행 구조 규칙적, 의존성 추가 안 함). (실측 2026-06-22)
"""
from __future__ import annotations

import re
import time

from .base import Adapter, RawNotice, http_post

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
        first = http_post(LIST_URL, {"pageIndex": 1}).decode("utf-8")
        m = _TOTAL_PAGES.search(first)
        total = min(int(m.group(1)), self.max_pages) if m else 1

        rows = parse_rows(first)
        for page in range(2, total + 1):
            html = http_post(LIST_URL, {"pageIndex": page}).decode("utf-8")
            rows += parse_rows(html)

        if self.detail:
            for r in rows:
                html = http_post(VIEW_URL, {
                    "ancmId": r["ancmId"], "bsnsYy": r["bsnsYy"],
                    "bsnsYyDetail": r["bsnsYy"], "sorgnBsnsCd": r["sorgnBsnsCd"],
                    "bsnsAncmSn": r["bsnsAncmSn"],
                }).decode("utf-8")
                r.update(parse_detail(html))
                time.sleep(self.interval)  # courteous: 상세 ~103 POST/실행 rate-limit 보호

        return [RawNotice(self.source, r) for r in rows]
