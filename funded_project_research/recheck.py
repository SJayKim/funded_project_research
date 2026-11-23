"""공식 상세의 구조화된 신청기간 재확인. 기본 dry-run, --apply만 DB에 반영한다."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from .adapters.base import http_get
from .extract import html_to_text
from .normalize import NoticeRecord, content_basis, normalize_text, parse_deadline, kstartup_archive_url
from .status import KST, as_kst, instant, notice_state, utc_now
from .store import Store

KNOWN_KEYS = ("bizinfo:PBLN_000000000105965", "kstartup:179430", "kstartup:175817")
RECHECK_HOURS = 24
RETRY_HOURS = 6
CONDITIONAL_PERIOD = re.compile(
    r"(?:예산\s*소진\s*(?:시\s*)?까지|(?:모집|접수)\s*(?:완료|마감)\s*시(?:까지)?"
    r"|상시\s*(?:접수|모집|신청)|선착순\s*(?:접수|모집|마감)?)"
)
ATTACHMENT_PERIOD = re.compile(
    r"(?:(?:첨부|첨부\s*파일|별첨|붙임)\s*(?:파일|공고문|공고)?|공고문)\s*(?:을\s*)?(?:참조|참고|확인)"
)
VARIABLE_PERIOD = re.compile(r"(?:세부\s*사업|차수|접수\s*방법)\s*별\s*상이")
NONFIXED_PERIOD_REASONS = {
    "period_conditional": "conditional",
    "period_attachment": "manual_review",
    "period_varies": "manual_review",
}


class PeriodError(ValueError):
    def __init__(self, reason: str, evidence: str = ""):
        super().__init__(reason)
        self.evidence = evidence


def select_candidates(records: dict, attempts: dict, now: datetime, limit: int) -> tuple[list, int]:
    """임박/기술 공고 3/4, 나머지 1/4. 실패 시각도 저장해 같은 앞부분의 독점을 막는다."""
    now = as_kst(now)
    priority, other = [], []
    for rec in records.values():
        if rec.source not in ("bizinfo", "kstartup"):
            continue
        closed = notice_state(rec, now, require_fresh=False) == "closed"
        if closed and rec.key not in KNOWN_KEYS:
            continue
        verified = instant(rec.verified_at) if rec.verification_status == "confirmed" and rec.verified_deadline == rec.deadline else None
        interval = timedelta(days=7) if closed else timedelta(hours=RECHECK_HOURS)
        if verified and timedelta(0) <= now - verified < interval:
            continue
        attempted = instant(attempts.get(rec.key, {}).get("checked_at", ""))
        if attempted and timedelta(0) <= now - attempted < timedelta(hours=RETRY_HOURS):
            continue
        deadline = instant(rec.deadline, end=True)
        urgent = rec.is_tech == "1" or rec.verification_status == "conflict" or (
            deadline and now <= deadline <= now + timedelta(days=14))
        (priority if urgent else other).append(rec)
    def order(rec):
        return (attempts.get(rec.key, {}).get("checked_at", ""), rec.verified_at or "",
                rec.deadline or "9999", rec.key)
    priority.sort(key=order)
    other.sort(key=order)
    quota = max(1, limit * 3 // 4)
    chosen = priority[:quota] + other[:limit - min(quota, len(priority))]
    selected = {r.key for r in chosen}
    chosen += [r for r in priority + other if r.key not in selected][:limit - len(chosen)]
    return chosen, len(priority) + len(other)


def _period_date(value: str) -> str:
    localized = re.match(
        r"^(\d{4})(?:\s*[./-]\s*|\s*년\s*)(\d{1,2})(?:\s*[./-]\s*|\s*월\s*)"
        r"(\d{1,2})(?:일|\.)?(?=$|[ T])", value,
    )
    if localized:
        year, month, day = map(int, localized.groups())
        value = f"{year:04d}-{month:02d}-{day:02d}" + value[localized.end():]
    return parse_deadline(value)


def _fixed_period(value: str) -> tuple[str, str]:
    normalized = re.sub(r"\s*\([월화수목금토일](?:요일)?\)\s*", " ", value)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    parts = re.split(r"\s*[~～∼]\s*|\s+[-–—]\s+|\s*부터\s*", normalized)
    if len(parts) == 2:
        start = _period_date(parts[0].strip())
        end = _period_date(parts[1].removesuffix("까지").strip())
        begin, close = instant(start), instant(end, end=True)
        if begin and close and begin < close:
            return start, end
    raise PeriodError("period_invalid", value)


def application_period(source: str, html: str) -> tuple[str, str, str]:
    """위치가 명확한 필드만 읽는다. 본문·추천 공고의 임의 날짜는 사용하지 않는다."""
    html = re.sub(r"<!--.*?-->|<script\b[^>]*>.*?</script\s*>", "", html, flags=re.S | re.I)
    if source == "kstartup":
        chunks = re.findall(r'<p\b[^>]*\sid=["\'](?:aplyPeriod|rcptPeriod)["\'][^>]*>(.*?)</p>', html, re.S | re.I)
    elif source == "bizinfo":
        chunks = re.findall(r'<span\b[^>]*\sclass=["\']s_title["\'][^>]*>\s*신청기간\s*</span>\s*<div\b[^>]*\sclass=["\']txt["\'][^>]*>(.*?)</div>', html, re.S)
    else:
        raise ValueError("unsupported_source")
    values = [normalize_text(re.sub(r'<[^>]+>', ' ', chunk)) for chunk in chunks]
    values = [value for value in values if value not in ("", "-", "–", "—")]
    if not values:
        raise PeriodError("period_missing")

    conditional = [value for value in values if CONDITIONAL_PERIOD.fullmatch(value)]
    attachment = [value for value in values if ATTACHMENT_PERIOD.fullmatch(value)]
    variable = [value for value in values if VARIABLE_PERIOD.fullmatch(value)]
    if conditional or attachment or variable:
        evidence = " / ".join(dict.fromkeys(values))
        if len(conditional) == len(values) and len({re.sub(r"\s+", "", v) for v in values}) == 1:
            raise PeriodError("period_conditional", evidence)
        if len(attachment) == len(values):
            raise PeriodError("period_attachment", evidence)
        if len(variable) == len(values):
            raise PeriodError("period_varies", evidence)
        raise PeriodError("period_conflict", evidence)

    periods = [(*_fixed_period(value), value) for value in values]
    # K-Startup 상단은 시작 시각을 생략할 수 있다. 종료값은 일치해야 한다.
    if (len({(end[:10], instant(end, end=True)) for _, end, _ in periods}) != 1
            or len({start[:10] for start, _, _ in periods}) != 1
            or len({instant(start) for start, _, _ in periods if len(start) > 10}) > 1):
        raise PeriodError("period_conflict", " / ".join(dict.fromkeys(values)))
    return max(periods, key=lambda p: (len(p[0]), len(p[1])))


def check_notice(rec: NoticeRecord, raw: bytes, checked_at: str) -> dict:
    html = raw.decode("utf-8", "replace")
    start, end, evidence = application_period(rec.source, html)
    return {"key": rec.key, "url": rec.url, "checked_at": checked_at,
            "content_hash": hashlib.sha256(evidence.encode()).hexdigest(),
            "old_deadline": rec.deadline, "new_deadline": end,
            "starts_at": start, "evidence": evidence,
            "extraction_matches": all(not getattr(rec, f) or getattr(rec, f) in html_to_text(html)
                                      for f in ("funding_amount", "eligibility", "required_docs", "key_dates"))}


def apply_check(store: Store, rec: NoticeRecord, result: dict) -> None:
    """대상 필드만 갱신한다. first_seen/last_seen/alerts/ID는 보존한다."""
    if result["url"] == kstartup_archive_url(rec):
        rec.url = result["url"]
    rec.deadline, rec.starts_at = result["new_deadline"], result["starts_at"]
    rec.verified_at = result["checked_at"]
    rec.verified_deadline = rec.deadline
    rec.verification_status = "confirmed"
    rec.period_condition = ""
    basis = content_basis(rec)
    extraction_status = rec.extraction_status
    extraction_basis = rec.extraction_basis
    if extraction_status:
        if result["extraction_matches"] and extraction_status in ("ok", "stale"):
            extraction_status, extraction_basis = "ok", basis
        else:
            extraction_status, extraction_basis = "stale", ""
    with store.conn:
        store.conn.execute("""UPDATE notices SET url=?, deadline=?, starts_at=?, verified_at=?,
            verified_deadline=?, verification_status='confirmed', period_condition='', summary_basis='',
            extraction_status=?, extraction_basis=? WHERE key=?""",
            (rec.url, rec.deadline, rec.starts_at, rec.verified_at, rec.deadline,
             extraction_status, extraction_basis, rec.key))
        store.conn.execute("""INSERT OR IGNORE INTO verifications
            (key, checked_at, url, content_hash, old_deadline, new_deadline, evidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            tuple(result[k] for k in ("key", "checked_at", "url", "content_hash", "old_deadline", "new_deadline", "evidence")))


def allowed_url(rec: NoticeRecord) -> bool:
    url = urlparse(rec.url)
    expected = {"bizinfo": ("www.bizinfo.go.kr", "pblancId"),
                "kstartup": ("www.k-startup.go.kr", "pbancSn")}.get(rec.source)
    return bool(expected and url.scheme == "https" and url.hostname == expected[0]
                and url.username is None and url.password is None and url.port in (None, 443)
                and parse_qs(url.query).get(expected[1]) == [rec.source_id])


def _report_url(rec: NoticeRecord) -> str:
    """원문을 찾는 데 필요한 파라미터만 보고서에 남긴다."""
    url = urlparse(rec.url)
    query = {"pblancId": rec.source_id} if rec.source == "bizinfo" else {"pbancSn": rec.source_id, "schM": "view"}
    return url._replace(query=urlencode(query), fragment="").geturl()


def recheck(db: Path, limit: int = 100, apply: bool = False, keys: list[str] | None = None,
            now: datetime | None = None) -> dict:
    if not 1 <= limit <= 100:
        raise ValueError("invalid_limit")
    if not db.is_file():
        raise ValueError("database_missing")
    # dry-run은 사본의 메모리 DB에서만 스키마를 이행한다.
    if apply:
        store = Store(str(db))
    else:
        store = Store(":memory:")
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            conn.backup(store.conn)
        store._init_schema()
    try:
        records = store.load()
        now = as_kst(now or datetime.now(KST))
        if keys:
            candidates = [records[k] for k in dict.fromkeys(keys) if k in records]
            due_count = len(candidates)
            candidates = candidates[:limit]
        else:
            attempts = {r["key"]: dict(r) for r in store.conn.execute("SELECT * FROM recheck_attempts")}
            candidates, due_count = select_candidates(records, attempts, now, limit)
        results = []
        started_at = utc_now()
        for rec in candidates:
            official_url = ""
            try:
                if not allowed_url(rec):
                    raise ValueError("untrusted_url")
                official_url = _report_url(rec)
                raw = http_get(rec.url, timeout=10)
                try:
                    result = check_notice(rec, raw, utc_now())
                except PeriodError as error:
                    archive_url = kstartup_archive_url(rec)
                    if str(error) != "period_missing" or not archive_url:
                        raise
                    archived = replace(rec, url=archive_url)
                    official_url = _report_url(archived)
                    raw = http_get(archive_url, timeout=10)
                    result = check_notice(archived, raw, utc_now())
                result["url"] = official_url
                if apply:
                    apply_check(store, rec, result)
                results.append({**result, "result": "confirmed"})
            except Exception as exc:
                # 실패 원문/URL 예외에 포함된 민감값은 출력하지 않는다.
                known_errors = {"untrusted_url", "unsupported_source"}
                reason = (str(exc) if isinstance(exc, PeriodError) or
                          isinstance(exc, ValueError) and str(exc) in known_errors else type(exc).__name__)
                checked_at = utc_now()
                item = {"key": rec.key, "result": "unconfirmed", "reason": reason, "checked_at": checked_at}
                if official_url:
                    item["url"] = official_url
                if isinstance(exc, PeriodError) and exc.evidence:
                    item["evidence"] = exc.evidence[:500]
                if reason in NONFIXED_PERIOD_REASONS:
                    item["old_deadline"] = rec.deadline
                results.append(item)
            if apply:
                item = results[-1]
                with store.conn:
                    if item.get("reason") == "period_conflict":
                        store.conn.execute("UPDATE notices SET verification_status='conflict', period_condition='' WHERE key=?",
                                           (rec.key,))
                    elif status := NONFIXED_PERIOD_REASONS.get(item.get("reason")):
                        store.conn.execute("""UPDATE notices SET verification_status=?, period_condition=?,
                            verified_at=?, verified_deadline='',
                            deadline_raw=COALESCE(NULLIF(deadline_raw,''), deadline), deadline='', starts_at='' WHERE key=?""",
                            (status, item["evidence"], item["checked_at"], rec.key))
                    store.conn.execute("INSERT OR REPLACE INTO recheck_attempts VALUES (?,?,?,?)",
                                       (rec.key, item["checked_at"], item["result"], item.get("reason", "")))
        return {"mode": "apply" if apply else "dry-run", "started_at": started_at,
                "checked_at": utc_now(), "selected": len(candidates), "due_count": due_count,
                "remaining_candidates": due_count - len(candidates), "results": results}
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("gov_notices.db"))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--key", action="append", dest="keys")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error("--limit은 1~100")
    result = recheck(args.db, args.limit, args.apply, args.keys)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
