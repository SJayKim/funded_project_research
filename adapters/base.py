"""공통 어댑터 계약. API/스크래퍼 어댑터가 동일하게 따른다."""
from __future__ import annotations

import json
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
# CERTIFICATE_VERIFY_FAILED를 낸다(curl은 관대해 통과). 이 화이트리스트
# 호스트에 한해서만 TLS 검증을 완화하고, 그 외 모든 호스트는 정상 검증한다.
# (사용자 명시 승인 2026-06-22)
_TLS_RELAXED_HOSTS = frozenset({
    "nidapi.k-startup.go.kr",
    "apis.data.go.kr",
    "api.odcloud.kr",
    "www.iris.go.kr",
})


def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    context = None
    if urlparse(url).hostname in _TLS_RELAXED_HOSTS:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
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
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
        return resp.read()


def build_url(base: str, service_key: str, params: dict) -> str:
    """serviceKey는 그대로 붙인다(.env 키가 이미 URL 인코딩됨 → 이중 인코딩 금지).
    나머지 파라미터만 urlencode."""
    return f"{base}?serviceKey={service_key}&{urlencode(params)}"


class Adapter(ABC):
    """모든 어댑터는 collect()로 RawNotice 리스트를 반환한다."""

    source: str

    @abstractmethod
    def collect(self) -> list[RawNotice]:
        ...
