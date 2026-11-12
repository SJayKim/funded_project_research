"""공개 점검 기록의 신선도와 배포 결과를 확인한다. DB·알림 이력은 변경하지 않는다."""
import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlsplit, urlunsplit, urlencode
from urllib.request import Request, urlopen

from funded_project_research.status import KST, as_kst, instant


def validate_report(report: dict, now: datetime, expected: dict | None = None) -> None:
    if not isinstance(report, dict):
        raise ValueError("periodic_check_missing_or_overdue")
    checked = instant(report.get("checked_at", ""))
    if (not report.get("run_id") or report.get("status") not in ("ok", "attention")
            or not checked or not timedelta(0) <= as_kst(now) - checked <= timedelta(hours=8)):
        raise ValueError("periodic_check_missing_or_overdue")
    if expected is not None and report != expected:
        raise ValueError("published_report_mismatch")


def fetch(url: str, limit: int) -> bytes:
    parts = urlsplit(url)
    query = urlencode({"reliability_check": time.time_ns()})
    url = urlunsplit(parts._replace(query=parts.query + ("&" if parts.query else "") + query))
    with urlopen(Request(url, headers={"Cache-Control": "no-cache"}), timeout=20) as response:
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError("published_response_too_large")
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="공개 reliability.json URL")
    parser.add_argument("--expected", type=Path)
    parser.add_argument("--html", type=Path)
    args = parser.parse_args()
    expected = json.loads(args.expected.read_text()) if args.expected else None
    expected_hash = hashlib.sha256(args.html.read_bytes()).digest() if args.html else None
    reason = "unknown"
    for attempt in range(4):
        try:
            report = json.loads(fetch(args.url, 2_000_000))
            validate_report(report, datetime.now(KST), expected)
            if expected_hash:
                html_url = args.url.rsplit("/", 1)[0] + "/"
                if hashlib.sha256(fetch(html_url, 100_000_000)).digest() != expected_hash:
                    raise ValueError("published_html_mismatch")
            print(f"공개 점검 기록 확인: {report['checked_at']} · 데이터 판정 {report['status']}")
            return 0
        except Exception as exc:
            reason = str(exc) if type(exc) is ValueError else type(exc).__name__
            if attempt < 3:
                time.sleep(5)
    print(f"공개 점검 감시 실패: {reason}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
