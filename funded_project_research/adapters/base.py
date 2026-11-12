"""공통 어댑터 계약. API/스크래퍼 어댑터가 동일하게 따른다."""
from __future__ import annotations

import json
import hashlib
import ssl
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

# data.go.kr(apis.data.go.kr) 계열은 브라우저 UA 헤더가 없으면 WAF가 400으로 차단한다.
# (실측 2026-06-22) → 모든 HTTP 호출 기본 UA.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# IRIS(www.iris.go.kr) WAF는 풀 브라우저 헤더 세트가 없으면 빈 템플릿 셸(행 0)을
# 반환한다. 쿠키·JS는 불필요(실측 2026-06-22). 이 헤더만 주면 서버렌더 행이 그대로 옴.
BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
}


@dataclass
class RawNotice:
    """어댑터가 수집한 소스별 원시 레코드 1건."""

    source: str       # 소스 식별자 (kstartup / bizinfo / msit / nara)
    raw: dict         # 소스 원본 필드 그대로


# 정부 데이터 호스트 일부는 인증서에 AKI 확장이 없어 OpenSSL 3.x가
# CERTIFICATE_VERIFY_FAILED를 낸다. 이 목록은 strict 확장 검사만 완화한다.
# 인증서 체인·서명·유효기간·호스트 이름 검증은 모든 호스트에서 유지한다.
# (사용자 명시 승인 2026-06-22)
_TLS_RELAXED_HOSTS = frozenset({
    "nidapi.k-startup.go.kr",
    "apis.data.go.kr",
    "api.odcloud.kr",     # now-unused: bizinfo 라이브 전환 후 odcloud 미사용(삭제는 별도 확인 후)
    "www.iris.go.kr",
    "www.k-startup.go.kr",   # 상세페이지 fetch(enrich) — AKI 누락, 실측 2026-06-26
    "www.bizinfo.go.kr",     # 상세페이지 fetch(enrich) — AKI 누락, 실측 2026-06-26
})


def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    context = None
    if urlparse(url).hostname in _TLS_RELAXED_HOSTS:
        context = ssl.create_default_context()
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
        return resp.read()


def http_get_json(url: str, timeout: int = 30) -> dict:
    return json.loads(http_get(url, timeout).decode("utf-8"))


def http_post(url: str, fields: dict, timeout: int = 30) -> bytes:
    """폼 POST(application/x-www-form-urlencoded) + 브라우저 헤더 세트.
    IRIS WAF는 이 헤더가 없으면 빈 셸을 반환한다(쿠키 불필요)."""
    headers = {"User-Agent": USER_AGENT, **BROWSER_HEADERS,
               "Content-Type": "application/x-www-form-urlencoded"}
    req = urllib.request.Request(url, data=urlencode(fields).encode("utf-8"),
                                 headers=headers)
    context = None
    if urlparse(url).hostname in _TLS_RELAXED_HOSTS:
        context = ssl.create_default_context()
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
        return resp.read()


def build_url(base: str, service_key: str, params: dict) -> str:
    """serviceKey는 그대로 붙인다(.env 키가 이미 URL 인코딩됨 → 이중 인코딩 금지).
    나머지 파라미터만 urlencode."""
    return f"{base}?serviceKey={service_key}&{urlencode(params)}"


class Adapter(ABC):
    """모든 어댑터는 collect()로 RawNotice 리스트를 반환한다."""

    source: str
    collection_state = "success"
    collection_error = ""
    page_count = 0

    def begin(self) -> list[RawNotice]:
        self.records = []
        self.page_hashes = set()
        self.page_count = 0
        self.collection_state = "success"
        self.collection_error = ""
        return self.records

    def add_page(self, items, id_field: str) -> None:
        if not isinstance(items, list) or any(not isinstance(r, dict) or not r.get(id_field) for r in items):
            raise SourceError("schema")
        self.page_count += 1
        if not items:
            return
        fingerprint = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()
        if fingerprint in self.page_hashes:
            raise SourceError("repeated_page")
        self.page_hashes.add(fingerprint)
        self.records.extend(RawNotice(self.source, r) for r in items)

    def capped(self) -> None:
        self.collection_state = "partial"
        self.collection_error = "page_limit"

    def check_total(self, expected) -> None:
        if expected is not None and str(expected).isdigit() and len(self.records) != int(expected):
            self.collection_state = "partial"
            self.collection_error = "count_mismatch"

    @abstractmethod
    def collect(self) -> list[RawNotice]:
        ...


class SourceError(ValueError):
    """공개 로그에는 응답 전문이나 인증값 대신 정해진 오류 종류만 남긴다."""


def check_api_code(code) -> None:
    if code is not None and str(code) not in ("00", "0", "NORMAL_SERVICE"):
        raise SourceError("api_error")
