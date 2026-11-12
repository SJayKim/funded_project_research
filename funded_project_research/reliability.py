"""매 실행의 데이터·출처·원문 점검 결과를 기록한다. 메일과 LLM은 호출하지 않는다."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from dataclasses import fields
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
import uuid
from urllib.parse import urlparse

from .normalize import NoticeRecord, content_basis
from .status import KST, as_kst, instant, notice_state
from .store import Store

SOURCES = ("kstartup", "bizinfo", "msit", "nara", "iris")
MAX_CHECK_AGE_HOURS = 8


def latest_report(db: Path) -> dict | None:
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='reliability_checks'").fetchone():
            return None
        row = conn.execute("SELECT report_json FROM reliability_checks ORDER BY checked_at DESC, rowid DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None


def build_report(db: Path, recheck: dict | None, now: datetime | None = None) -> dict:
    now = as_kst(now or datetime.now(KST))
    if not isinstance(recheck, dict):
        recheck = None
    issues, counts = [], Counter(total=0)
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        if conn.execute("PRAGMA integrity_check").fetchall()[0][0] != "ok":
            raise ValueError("database_integrity")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        health = [dict(r) for r in conn.execute("SELECT * FROM source_health ORDER BY source")] if "source_health" in tables else []
        for source in SOURCES:
            h = next((r for r in health if r["source"] == source), None)
            checked = instant(h["completed_at"]) if h else None
            if not checked or not timedelta(0) <= now - checked <= timedelta(hours=MAX_CHECK_AGE_HOURS):
                issues.append({"code": "source_check_overdue", "source": source})
            if not h or h["state"] not in ("success", "empty"):
                issues.append({"code": "source_unhealthy", "source": source,
                               "state": h["state"] if h else "unknown",
                               "reason": h["error_kind"] if h else "no_record"})
        for row in conn.execute("SELECT * FROM notices"):
            d = dict(row)
            rec = NoticeRecord(**{f.name: d.get(f.name) or "" for f in fields(NoticeRecord)})
            state = notice_state(rec, now)
            counts["total"] += 1
            counts[state] += 1
            if d["key"] != rec.key or not rec.source_id:
                counts["invalid_identity"] += 1
            if rec.verification_status == "confirmed" and rec.verified_deadline != rec.deadline:
                counts["verification_mismatch"] += 1
            for value in (rec.source_checked_at, rec.verified_at):
                if value and (instant(value) is None or instant(value) > now + timedelta(minutes=5)):
                    counts["invalid_check_time"] += 1
            basis = content_basis(rec)
            if rec.summary and rec.summary_basis != basis:
                counts["hidden_summary"] += 1
            if rec.extraction_status and rec.extraction_basis != basis:
                counts["hidden_extraction"] += 1
            if state == "closed":
                continue
            counts["active"] += 1
            if not rec.url:
                counts["active_missing_url"] += 1
            else:
                try:
                    url = urlparse(rec.url)
                    valid = url.scheme in ("http", "https") and bool(url.hostname)
                except ValueError:
                    valid = False
                if not valid:
                    counts["invalid_url"] += 1
            if not rec.deadline:
                counts["active_missing_deadline"] += 1
            if rec.source not in ("bizinfo", "kstartup"):
                counts["unsupported_official_period"] += 1
                continue
            counts["supported_active"] += 1
            verified, end = instant(rec.verified_at), instant(rec.deadline, end=True)
            fresh = (rec.verification_status == "confirmed" and rec.verified_deadline == rec.deadline
                     and verified and timedelta(0) <= now - verified < timedelta(hours=24))
            if fresh:
                counts["official_fresh"] += 1
            elif end and now <= end <= now + timedelta(days=14):
                counts["near_deadline_unverified"] += 1
        counts["alerts"] = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
    if not counts["total"]:
        issues.append({"code": "empty_snapshot"})
    for code in ("invalid_identity", "verification_mismatch", "invalid_check_time", "conflict", "invalid_url", "near_deadline_unverified"):
        if counts[code]:
            issues.append({"code": code, "count": counts[code]})
    checked = instant((recheck or {}).get("checked_at", ""))
    results = (recheck or {}).get("results", [])
    selected = (recheck or {}).get("selected", -1)
    valid_recheck = (checked and timedelta(0) <= now - checked <= timedelta(hours=1)
                     and isinstance(results, list) and len(results) == selected
                     and all(isinstance(r, dict) and r.get("key") and r.get("result") in ("confirmed", "unconfirmed")
                             and (r["result"] != "confirmed" or {"old_deadline", "new_deadline"} <= r.keys()) for r in results)
                     and len({r.get("key") for r in results}) == len(results)
                     and (selected > 0 or (recheck or {}).get("due_count") == 0))
    if not valid_recheck:
        issues.append({"code": "recheck_missing_or_invalid"})
        results = []
    failures = sum(r["result"] != "confirmed" for r in results)
    if failures:
        issues.append({"code": "official_unconfirmed", "count": failures})
    run_id = os.environ.get("GITHUB_RUN_ID", "local-" + uuid.uuid4().hex) + ":" + os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    return {"run_id": run_id, "checked_at": now.isoformat(timespec="seconds"),
            "status": "attention" if issues else "ok", "max_age_hours": MAX_CHECK_AGE_HOURS,
            "counts": dict(counts), "sources": health, "issues": issues,
            "official": {"selected": len(results), "confirmed": len(results) - failures,
                         "unconfirmed": failures, "remaining": (recheck or {}).get("remaining_candidates", 0),
                         "changed": sum(r["result"] == "confirmed" and r["old_deadline"] != r["new_deadline"] for r in results)}}


def record_report(db: Path, report: dict) -> None:
    store = Store(str(db))
    try:
        with store.conn:
            store.conn.execute("INSERT OR REPLACE INTO reliability_checks VALUES (?,?,?)",
                               (report["run_id"], report["checked_at"], json.dumps(report, ensure_ascii=False)))
    finally:
        store.close()


def markdown_report(report: dict) -> str:
    lines = ["## 정부과제 자동 신뢰성 점검", "",
             f"판정: {report['status']} · 완료 시각: {report['checked_at']}",
             f"공고 {report['counts']['total']:,}건 · 원문 확인 {report['official']['confirmed']}건 / {report['official']['selected']}건", "",
             "| 검사 항목 | 출처/건수 |", "|---|---|"]
    lines += [f"| {r['code']} | {r.get('source', r.get('count', ''))} |" for r in report["issues"]]
    if not report["issues"]:
        lines.append("| 설정된 자동 검사 통과 | 전체 공고의 의미 정확성을 보증하지 않음 |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("gov_notices.db"))
    parser.add_argument("--recheck-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    try:
        recheck = json.loads(args.recheck_report.read_text())
    except (OSError, ValueError):
        recheck = None
    report = build_report(args.db, recheck)
    if args.record:
        record_report(args.db, report)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(markdown_report(report))
    print(f"자동 점검: {report['status']} · {len(report['issues'])}개 항목 · 원문 {report['official']['confirmed']}건 확인")
    return 2 if report["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
