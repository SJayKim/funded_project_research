"""§11 통합 스키마 매핑 + 기관명/날짜 정규화.

소스별 매핑은 MAPPERS에 등록한다(신규 소스는 매핑만 추가).
1주차 적재 컬럼: 공고명·출처URL·소관부처·전문기관·신청대상·접수마감.
금액은 5개 API 모두 정형 숫자 미노출 → 1주차 제외(spec 블로커 2).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from adapters.base import RawNotice

# diff 감시 필드(접수마감·신청상태·첨부 링크)
WATCH_FIELDS = ("deadline", "status", "attachments")


@dataclass
class NoticeRecord:
    source: str
    source_id: str
    title: str
    url: str
    agency: str = ""              # 소관부처
    specialized_agency: str = ""  # 전문기관
    target: str = ""              # 신청 대상
    deadline: str = ""            # 접수 마감(정규화): "YYYY-MM-DD" 또는 "YYYY-MM-DD HH:MM[:SS]"
    status: str = ""              # 신청상태(watch)
    attachments: str = ""         # 첨부 링크 ' '.join(watch)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"


def normalize_text(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def parse_deadline(value: str | None) -> str:
    """마감일 4포맷을 ISO로 정규화. 값 없으면 ''.

    YYYYMMDD            (K-Startup)       -> YYYY-MM-DD
    YYYY-MM-DD          (기업마당 미러)    -> YYYY-MM-DD
    YYYY-MM-DD HH:MM:SS (나라장터 입찰)    -> 그대로
    YYYY-MM-DD HH:MM    (개방표준 결합)    -> 그대로
    """
    v = (value or "").strip()
    if not v:
        return ""
    if re.fullmatch(r"\d{8}", v):
        return f"{v[0:4]}-{v[4:6]}-{v[6:8]}"
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}(?::\d{2})?))?", v)
    if m:
        return f"{m.group(1)} {m.group(2)}" if m.group(2) else m.group(1)
    return ""


def deadline_date(rec: NoticeRecord) -> date | None:
    """정규화된 deadline의 날짜 부분."""
    if not rec.deadline:
        return None
    try:
        return datetime.strptime(rec.deadline[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _map_kstartup(r: dict) -> NoticeRecord:
    return NoticeRecord(
        source="kstartup",
        source_id=str(r.get("pbanc_sn", "")),
        title=normalize_text(r.get("biz_pbanc_nm")),
        url=normalize_text(r.get("detl_pg_url")),
        agency=normalize_text(r.get("pbanc_ntrp_nm")),
        target=normalize_text(r.get("aply_trgt")),
        deadline=parse_deadline(r.get("pbanc_rcpt_end_dt")),
        status=normalize_text(r.get("rcrt_prgs_yn")),
    )


def _pblanc_id(url: str) -> str:
    m = re.search(r"pblancId=([A-Za-z0-9_]+)", url or "")
    return m.group(1) if m else (url or "")


def _map_bizinfo(r: dict) -> NoticeRecord:
    url = normalize_text(r.get("상세URL"))
    return NoticeRecord(
        source="bizinfo",
        source_id=_pblanc_id(url),
        title=normalize_text(r.get("사업명")),
        url=url,
        agency=normalize_text(r.get("소관기관")),
        specialized_agency=normalize_text(r.get("수행기관")),
        deadline=parse_deadline(r.get("신청종료일자")),
    )


def _ntt_seq(url: str) -> str:
    m = re.search(r"nttSeqNo=(\d+)", url or "")
    return m.group(1) if m else (url or "")


def _map_msit(r: dict) -> NoticeRecord:
    # 과기정통부: 마감일 필드 없음(pressDt 게시일만) → deadline 공란, 신규 알림만.
    url = normalize_text(r.get("viewUrl"))
    files = r.get("files") or []
    attachments = " ".join(normalize_text(f.get("fileUrl")) for f in files if f.get("fileUrl"))
    return NoticeRecord(
        source="msit",
        source_id=_ntt_seq(url),
        title=normalize_text(r.get("subject")),
        url=url,
        agency="과학기술정보통신부",
        specialized_agency=normalize_text(r.get("deptName")),
        attachments=attachments,
    )


def _map_nara(r: dict) -> NoticeRecord:
    return NoticeRecord(
        source="nara",
        source_id=normalize_text(r.get("bidNtceNo")),
        title=normalize_text(r.get("bidNtceNm")),
        url=normalize_text(r.get("ntceSpecDocUrl1")),
        agency=normalize_text(r.get("ntceInsttNm")),
        specialized_agency=normalize_text(r.get("dminsttNm")),
        deadline=parse_deadline(r.get("bidClseDt")),
    )


MAPPERS = {
    "kstartup": _map_kstartup,
    "bizinfo": _map_bizinfo,
    "msit": _map_msit,
    "nara": _map_nara,
}


def normalize(raw: RawNotice) -> NoticeRecord:
    return MAPPERS[raw.source](raw.raw)
