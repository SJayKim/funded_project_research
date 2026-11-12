import hashlib
import io
import json
from contextlib import closing, redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from funded_project_research import recheck, reliability, serve
from funded_project_research.normalize import NoticeRecord
from funded_project_research.store import Store
from scripts import check_published

NOW = datetime.fromisoformat("2026-11-12T09:00:00+00:00")
STAMP = NOW.isoformat(timespec="seconds")


def notice(number, **extra):
    values = dict(source="bizinfo", source_id=f"PBLN_{number}", title=f"공고 {number}",
                  url=f"https://www.bizinfo.go.kr/test?pblancId=PBLN_{number}",
                  deadline="2026-11-20", source_checked_at=STAMP)
    values.update(extra)
    return NoticeRecord(**values)


class TestRotation(unittest.TestCase):
    def test_fresh_api_records_are_independently_rechecked_and_long_tail_gets_a_turn(self):
        records = [notice(i) for i in range(8)] + [notice(i, deadline="2027-01-01") for i in range(8, 12)]
        chosen, due = recheck.select_candidates({r.key: r for r in records}, {}, NOW, 4)
        self.assertEqual(due, 12)
        self.assertEqual(sum(r.deadline == "2026-11-20" for r in chosen), 3)
        self.assertEqual(sum(r.deadline == "2027-01-01" for r in chosen), 1)

    def test_recent_confirmation_and_recent_failed_attempt_are_skipped(self):
        fresh = notice(1, verified_at=STAMP, verified_deadline="2026-11-20", verification_status="confirmed")
        failed, due = notice(2), notice(3)
        chosen, count = recheck.select_candidates({r.key: r for r in (fresh, failed, due)},
                                                {failed.key: {"checked_at": STAMP}}, NOW, 10)
        self.assertEqual([r.key for r in chosen], [due.key])
        self.assertEqual(count, 1)
        later, _ = recheck.select_candidates({fresh.key: fresh}, {}, NOW + timedelta(hours=24), 10)
        self.assertEqual(later, [fresh])

    def test_closed_history_and_unsupported_sources_are_not_the_daily_queue(self):
        closed = notice(1, deadline="2026-10-01")
        unsupported = notice(2, source="iris")
        chosen, count = recheck.select_candidates({r.key: r for r in (closed, unsupported)}, {}, NOW, 10)
        self.assertEqual((chosen, count), ([], 0))

    def test_failed_first_record_does_not_starve_next_run_and_dry_run_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "snapshot.db"
            store = Store(str(db))
            rows = [notice(i) for i in range(3)]
            for r in rows:
                store.upsert(r, "2026-11-01")
            store.commit(); store.close()
            original = hashlib.sha256(db.read_bytes()).hexdigest()
            with patch.object(recheck, "http_get", side_effect=TimeoutError()), patch.object(recheck, "utc_now", return_value=STAMP):
                recheck.recheck(db, limit=1, now=NOW)
                self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), original)
                first = recheck.recheck(db, limit=1, apply=True, now=NOW)
                second = recheck.recheck(db, limit=1, apply=True, now=NOW)
            self.assertNotEqual(first["results"][0]["key"], second["results"][0]["key"])
            with closing(sqlite3.connect(db)) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM recheck_attempts").fetchone()[0], 2)
                self.assertEqual(conn.execute("SELECT DISTINCT last_seen FROM notices").fetchall(), [("2026-11-01",)])

    def test_explicit_keys_override_rotation_and_error_details_do_not_leak(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "snapshot.db"
            store = Store(str(db))
            r = notice(1, verified_at=STAMP, verified_deadline="2026-11-20", verification_status="confirmed")
            store.upsert(r, "old"); store.commit(); store.close()
            with patch.object(recheck, "http_get", side_effect=ValueError("url?serviceKey=fixture-secret")):
                result = recheck.recheck(db, keys=[r.key, r.key], now=NOW)
            self.assertEqual(result["selected"], 1)
            self.assertEqual(result["results"][0]["reason"], "ValueError")
            self.assertNotIn("fixture-secret", json.dumps(result))


class TestReliabilityReport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "snapshot.db"
        self.store = Store(str(self.db))
        self.addCleanup(self.store.close)
        self.rec = notice(1, verified_at=STAMP, verified_deadline="2026-11-20", verification_status="confirmed")
        self.store.upsert(self.rec, "2026-11-01")
        self.store.mark_alert(self.rec.key, "new")
        for source in reliability.SOURCES:
            self.store.record_source(source, "success", STAMP, STAMP, 1, 1, "")
        self.store.commit()
        self.rechecked = {"checked_at": STAMP, "selected": 0, "due_count": 0, "results": [], "remaining_candidates": 0}

    def test_healthy_run_records_history_without_changing_notice_or_alert(self):
        report = reliability.build_report(self.db, self.rechecked, NOW)
        self.assertEqual(report["status"], "ok")
        before = tuple(self.store.conn.execute("SELECT * FROM notices").fetchone())
        reliability.record_report(self.db, report)
        self.assertEqual(reliability.latest_report(self.db), report)
        self.assertEqual(tuple(self.store.conn.execute("SELECT * FROM notices").fetchone()), before)
        self.assertEqual([tuple(r) for r in self.store.conn.execute("SELECT * FROM alerts")], [(self.rec.key, "new")])

    def test_partial_source_failed_official_check_and_unconfirmed_near_deadline_are_visible(self):
        self.store.record_source("iris", "partial", STAMP, STAMP, 20, 2, "detail_failed")
        self.store.upsert(notice(2), "old")
        self.store.commit()
        check = {**self.rechecked, "selected": 1, "due_count": 1,
                 "results": [{"key": self.rec.key, "result": "unconfirmed", "reason": "TimeoutError"}]}
        report = reliability.build_report(self.db, check, NOW)
        codes = {r["code"] for r in report["issues"]}
        self.assertTrue({"source_unhealthy", "official_unconfirmed", "near_deadline_unverified"} <= codes)
        self.assertEqual(report["status"], "attention")

    def test_missing_or_old_recheck_report_cannot_be_success(self):
        for check in (None, [], {}, {**self.rechecked, "checked_at": (NOW - timedelta(hours=2)).isoformat()},
                      {**self.rechecked, "due_count": 1}, {**self.rechecked, "selected": 1}):
            with self.subTest(check=check):
                report = reliability.build_report(self.db, check, NOW)
                self.assertIn("recheck_missing_or_invalid", [r["code"] for r in report["issues"]])

    def test_clock_errors_conflicts_and_bad_links_are_detected(self):
        bad = notice(2, deadline="2026-02-30", source_checked_at="2099-01-01", url="javascript:bad()")
        self.store.upsert(bad, "old"); self.store.commit()
        report = reliability.build_report(self.db, self.rechecked, NOW)
        self.assertTrue({"conflict", "invalid_url", "invalid_check_time"} <= {r["code"] for r in report["issues"]})
        late = reliability.build_report(self.db, self.rechecked, NOW + timedelta(hours=9))
        self.assertEqual(sum(r["code"] == "source_check_overdue" for r in late["issues"]), 5)

    def test_old_schema_has_no_report_and_static_build_publishes_record(self):
        self.assertIsNone(reliability.latest_report(self.db))
        report = reliability.build_report(self.db, self.rechecked, NOW)
        reliability.record_report(self.db, report)
        output = Path(self.temp.name) / "site/index.html"
        with patch.object(serve, "DB_PATH", str(self.db)), patch("sys.argv", ["serve", "--build", str(output)]):
            serve.main()
        self.assertEqual(json.loads(output.with_name("reliability.json").read_text()), report)
        self.assertIn(report["run_id"], output.read_text())

    def test_failed_audit_is_recorded_before_cli_returns_failure(self):
        output = Path(self.temp.name) / "report.json"
        missing = Path(self.temp.name) / "missing-recheck.json"
        with patch("sys.argv", ["audit", "--db", str(self.db), "--recheck-report", str(missing), "--report", str(output), "--record"]), \
             patch.object(reliability, "datetime") as clock, redirect_stdout(io.StringIO()):
            clock.now.return_value = NOW
            self.assertEqual(reliability.main(), 2)
        saved = json.loads(output.read_text())
        self.assertEqual(reliability.latest_report(self.db), saved)
        self.assertEqual(saved["status"], "attention")
        self.assertIn("recheck_missing_or_invalid", [r["code"] for r in saved["issues"]])

    def test_empty_snapshot_is_not_a_successful_zero_check(self):
        self.store.conn.execute("DELETE FROM notices")
        self.store.commit()
        report = reliability.build_report(self.db, self.rechecked, NOW)
        self.assertEqual(report["counts"]["total"], 0)
        self.assertEqual(report["status"], "attention")
        self.assertIn("empty_snapshot", [r["code"] for r in report["issues"]])
        self.assertIn("공고 0건", reliability.markdown_report(report))


class TestPublishedWatch(unittest.TestCase):
    def setUp(self):
        self.report = {"checked_at": STAMP, "run_id": "123:1", "status": "attention"}

    def test_watch_detects_missing_future_stale_or_wrong_deployment(self):
        check_published.validate_report(self.report, NOW)
        for report in (None, {}, {**self.report, "checked_at": "bad"},
                       {**self.report, "checked_at": (NOW + timedelta(minutes=1)).isoformat()},
                       {**self.report, "checked_at": (NOW - timedelta(hours=8, seconds=1)).isoformat()}):
            with self.subTest(report=report), self.assertRaises(ValueError):
                check_published.validate_report(report, NOW)
        with self.assertRaisesRegex(ValueError, "published_report_mismatch"):
            check_published.validate_report(self.report, NOW, {**self.report, "run_id": "456:1"})

    def test_publication_checks_html_and_retries_propagation(self):
        with tempfile.TemporaryDirectory() as tmp:
            expected = Path(tmp) / "reliability.json"
            html = Path(tmp) / "index.html"
            expected.write_text(json.dumps(self.report)); html.write_bytes(b"checked dashboard")
            with patch("sys.argv", ["watch", "--url", "https://example.invalid/reliability.json", "--expected", str(expected), "--html", str(html)]), \
                 patch.object(check_published, "datetime") as clock, \
                 patch.object(check_published, "fetch", side_effect=[b"null", json.dumps(self.report).encode(), html.read_bytes()]), \
                 patch.object(check_published.time, "sleep") as pause, redirect_stdout(io.StringIO()):
                clock.now.return_value = NOW
                self.assertEqual(check_published.main(), 0)
                pause.assert_called_once_with(5)

    def test_publication_mismatch_stays_failed(self):
        with patch("sys.argv", ["watch", "--url", "https://example.invalid/reliability.json"]), \
             patch.object(check_published, "fetch", return_value=b"null"), \
             patch.object(check_published.time, "sleep"), redirect_stdout(io.StringIO()):
            self.assertEqual(check_published.main(), 2)


if __name__ == "__main__":
    unittest.main()
