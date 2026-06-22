"""증분 diff + 마감 임박 계산.

신규: 직전 스냅샷에 없던 key
수정: 감시 필드(접수마감·신청상태·첨부) 변화
임박: 마감 D-7/D-3/D-1 (마감일 있는 소스만)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from normalize import WATCH_FIELDS, NoticeRecord, deadline_date

IMMINENT_THRESHOLDS = (7, 3, 1)


@dataclass
class FieldChange:
    field: str
    old: str
    new: str


@dataclass
class Modified:
    record: NoticeRecord
    changes: list[FieldChange]


def find_new(previous: dict[str, NoticeRecord], current: list[NoticeRecord]) -> list[NoticeRecord]:
    return [r for r in current if r.key not in previous]


def find_modified(
    previous: dict[str, NoticeRecord], current: list[NoticeRecord]
) -> list[Modified]:
    out: list[Modified] = []
    for r in current:
        prev = previous.get(r.key)
        if prev is None:
            continue
        changes = [
            FieldChange(f, getattr(prev, f), getattr(r, f))
            for f in WATCH_FIELDS
            if getattr(prev, f) != getattr(r, f)
        ]
        if changes:
            out.append(Modified(r, changes))
    return out


def days_left(rec: NoticeRecord, today: date) -> int | None:
    d = deadline_date(rec)
    if d is None:
        return None
    return (d - today).days


def find_imminent(current: list[NoticeRecord], today: date) -> list[tuple[NoticeRecord, int]]:
    """(record, threshold) 리스트. threshold는 7/3/1 중 도달한 값."""
    out: list[tuple[NoticeRecord, int]] = []
    for r in current:
        dl = days_left(r, today)
        if dl is None:
            continue
        if dl in IMMINENT_THRESHOLDS:
            out.append((r, dl))
    return out
