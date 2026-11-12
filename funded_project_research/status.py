"""한국 시각의 접수 상태. 브라우저 status.js와 공통 fixture로 검증한다."""
from datetime import date, datetime, time, timedelta, timezone

KST = timezone(timedelta(hours=9))
FRESH_HOURS = 48


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def as_kst(now: date | datetime) -> datetime:
    if not isinstance(now, datetime):
        return datetime.combine(now, time.min, KST)
    return now.replace(tzinfo=KST) if now.tzinfo is None else now.astimezone(KST)


def instant(value: str, end: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        if len(value) == 10:
            result = datetime.combine(date.fromisoformat(value), time.min, KST)
            return result + timedelta(days=1) if end else result
        return as_kst(datetime.fromisoformat(value))
    except (ValueError, OverflowError):
        return None


def notice_state(record, now: date | datetime, require_fresh: bool = True) -> str:
    get = record.get if isinstance(record, dict) else lambda k, default="": getattr(record, k, default)
    now = as_kst(now)
    deadline = get("deadline", "")
    start = get("starts_at", "")
    close = instant(deadline, end=True)
    begin = instant(start)
    if get("status") == "N":
        return "closed"
    if (deadline and close is None) or (start and begin is None):
        return "conflict"
    if begin and close and begin >= close:
        return "conflict"
    if get("verification_status") == "conflict":
        return "conflict"
    if close and now >= close:
        return "closed"
    if not close:
        return "unknown"
    if require_fresh:
        checked = instant(get("source_checked_at", ""))
        if get("verification_status") == "confirmed" and get("verified_deadline") == deadline:
            verified = instant(get("verified_at", ""))
            if verified and (checked is None or verified > checked):
                checked = verified
        if checked is None or not timedelta(0) <= now - checked <= timedelta(hours=FRESH_HOURS):
            return "unknown"
    if begin and now < begin:
        return "scheduled"
    return "open"
