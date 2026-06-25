"""§11 통합 스키마 매핑 + 기관명/날짜 정규화.

소스별 매핑은 MAPPERS에 등록한다(신규 소스는 매핑만 추가).
1주차 적재 컬럼: 공고명·출처URL·소관부처·전문기관·신청대상·접수마감.
금액은 5개 API 모두 정형 숫자 미노출 → 1주차 제외(spec 블로커 2).
"""
from __future__ import annotations

import html
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
    category: str = ""            # classify 결과(기술분야)
    summary: str = ""             # LLM/규칙 요약(캐시)
    is_tech: str = ""             # "1"/"0" (TEXT, 스키마 일관)
    # Approach A 추출 6필드(전부 TEXT 기본 "", WATCH 제외)
    funding_amount: str = ""      # 지원금액 발췌
    eligibility: str = ""         # 신청자격 발췌
    required_docs: str = ""       # 제출서류 발췌
    key_dates: str = ""           # 주요일정 발췌
    extracted_from: str = ""      # 추출 출처 문서
    extraction_status: str = ""   # ""=미시도 / ok / no_info / failed

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"


def normalize_text(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", html.unescape(str(s))).strip()


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


def _map_iris(r: dict) -> NoticeRecord:
    # 마감일 rcveEndDt는 YYYY/MM/DD → '/'→'-' 치환 후 parse_deadline(공용 무변경).
    ancm = normalize_text(r.get("ancmId"))
    return NoticeRecord(
        source="iris",
        source_id=ancm,
        title=normalize_text(r.get("ancmTl")),
        url=f"https://www.iris.go.kr/contents/retrieveBsnsAncmView.do?ancmId={ancm}",
        agency=normalize_text(r.get("sorgn")),            # 소관부처
        specialized_agency=normalize_text(r.get("spcl")),  # 전담기관
        deadline=parse_deadline((r.get("rcveEndDt") or "").replace("/", "-")),
        attachments=normalize_text(r.get("attachments")),  # 상세 첨부 파일명 ' '.join
    )


MAPPERS = {
    "kstartup": _map_kstartup,
    "bizinfo": _map_bizinfo,
    "msit": _map_msit,
    "nara": _map_nara,
    "iris": _map_iris,
}


def normalize(raw: RawNotice) -> NoticeRecord:
    return MAPPERS[raw.source](raw.raw)
