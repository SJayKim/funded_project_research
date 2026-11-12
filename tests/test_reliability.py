import json
from pathlib import Path
import subprocess
import unittest
import hashlib
import io
import sqlite3
import tempfile
from contextlib import closing, redirect_stderr
from datetime import datetime
from unittest.mock import patch

from funded_project_research.normalize import NoticeRecord, parse_deadline
from funded_project_research.status import notice_state
from funded_project_research.store import Store
from funded_project_research import collect, serve, summarize, recheck
from funded_project_research.adapters.base import SourceError
from funded_project_research.adapters.kstartup import KStartupAdapter

ROOT = Path(__file__).resolve().parents[1]


class TestNoticeState(unittest.TestCase):
    def test_shared_python_and_browser_cases(self):
        cases = json.loads((ROOT / "tests/fixtures/notice_states.json").read_text())
        for case in cases:
            with self.subTest(case["name"]):
                self.assertEqual(notice_state(case["record"], datetime.fromisoformat(case["now"])),
                                 case["state"])
        js = """
const fs = require('fs');
const {noticeState} = require('./funded_project_research/status.js');
const cases = JSON.parse(fs.readFileSync('./tests/fixtures/notice_states.json'));
console.log(JSON.stringify(cases.map(c => noticeState(c.record, new Date(c.now)))));
"""
        result = subprocess.run(["node", "-e", js], cwd=ROOT, text=True,
                                capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout), [c["state"] for c in cases])

    def test_real_calendar_and_timezone_normalization(self):
        for value in ["20260230", "2026-02-29", "2026-11-12 25:61", "2026-13-01"]:
            with self.subTest(value):
                self.assertEqual(parse_deadline(value), "")
        self.assertEqual(parse_deadline("2028.02.29"), "2028-02-29")
        self.assertEqual(parse_deadline("2026-11-12T15:00:00Z"), "2026-11-13 00:00:00")

    def test_closed_and_future_not_imminent(self):
        from funded_project_research.diff import find_imminent
        from datetime import date
        rows = [NoticeRecord("x", "1", "t", "u", deadline="2026-11-19", status="N"),
                NoticeRecord("x", "2", "t", "u", deadline="2026-11-19", starts_at="2026-11-15")]
        self.assertEqual(find_imminent(rows, date(2026, 11, 12)), [])


class TestCollectionHealth(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def test_partial_page_keeps_received_rows_and_records_failure(self):
        adapter = KStartupAdapter(service_key="fixture", max_pages=3)
        with patch("funded_project_research.adapters.kstartup.http_get_json", side_effect=[
            {"data": [{"pbanc_sn": 1}]}, TimeoutError("network")
        ]), patch.object(collect, "ADAPTERS", [lambda: adapter]):
            rows = collect.collect_all(self.store)
        self.assertEqual([r.raw["pbanc_sn"] for r in rows], [1])
        health = self.store.source_health()[0]
        self.assertEqual((health["state"], health["count"], health["pages"]), ("partial", 1, 1))

    def test_error_payload_is_not_empty_success(self):
        adapter = KStartupAdapter(service_key="fixture")
        with patch("funded_project_research.adapters.kstartup.http_get_json", return_value={"code": 401}), \
             patch.object(collect, "ADAPTERS", [lambda: adapter]):
            self.assertEqual(collect.collect_all(self.store), [])
        self.assertEqual(self.store.source_health()[0]["state"], "failed")

    def test_valid_empty_and_cap_and_repeated_page(self):
        for responses, limit, state, count in [
            ([{"data": []}], 1, "empty", 0),
            ([{"data": [], "totalCount": 10}], 1, "partial", 0),
            ([{"data": [{"pbanc_sn": 1}]}], 1, "partial", 1),
            ([{"data": [{"pbanc_sn": 1}]}, {"data": [{"pbanc_sn": 1}]}], 3, "partial", 1),
        ]:
            with self.subTest(state=state, count=count):
                adapter = KStartupAdapter(service_key="fixture", max_pages=limit)
                with patch("funded_project_research.adapters.kstartup.http_get_json", side_effect=responses), \
                     patch.object(collect, "ADAPTERS", [lambda: adapter]):
                    collect.collect_all(self.store)
                h = self.store.source_health()[0]
                self.assertEqual((h["state"], h["count"]), (state, count))

    def test_other_sources_reject_business_errors(self):
        from funded_project_research.adapters.nara import NaraAdapter
        from funded_project_research.adapters.msit import MsitAdapter
        from funded_project_research.adapters.bizinfo import BizinfoAdapter
        samples = [
            (NaraAdapter(service_key="fixture"), "nara.http_get_json", {"response": {"header": {"resultCode": "30"}, "body": {"items": []}}}),
            (MsitAdapter(service_key="fixture"), "msit.http_get", b'<response><header><resultCode>30</resultCode></header><body/></response>'),
            (BizinfoAdapter(crtfc_key="fixture"), "bizinfo.http_get_json", {"jsonArray": [], "resultCode": "30"}),
        ]
        for adapter, target, payload in samples:
            with self.subTest(source=adapter.source), patch("funded_project_research.adapters." + target, return_value=payload):
                with self.assertRaises(SourceError):
                    adapter.collect()

    def test_tls_keeps_certificate_and_hostname_verification(self):
        import ssl
        from funded_project_research.adapters import base
        with patch.object(base.urllib.request, "urlopen") as opened:
            opened.return_value.__enter__.return_value.read.return_value = b"test"
            base.http_get("https://www.bizinfo.go.kr/test")
            context = opened.call_args.kwargs["context"]
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            base.http_post("https://www.iris.go.kr/test", {})
            context = opened.call_args.kwargs["context"]
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_failure_does_not_advance_last_success_or_expose_url(self):
        from urllib.error import HTTPError
        class Broken:
            source = "kstartup"
            def collect(self):
                raise HTTPError("https://example.invalid?serviceKey=fixture-secret", 500, "bad", {}, None)
        self.store.record_source("kstartup", "success", "old", "old", 2, 1, "")
        out = io.StringIO()
        with patch.object(collect, "ADAPTERS", [Broken]), redirect_stderr(out):
            collect.collect_all(self.store)
        self.assertEqual(self.store.source_health()[0]["last_success"], "old")
        self.assertNotIn("fixture-secret", out.getvalue())
        self.assertEqual(self.store.source_health()[0]["error_kind"], "http_500")

    def test_all_failed_main_exits_nonzero_and_persists_health(self):
        class Broken:
            source = "kstartup"
            def collect(self):
                raise TimeoutError()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "db.sqlite"
            with patch.object(collect, "ADAPTERS", [Broken]), \
                 patch.object(collect, "Store", lambda: Store(str(db))), \
                 patch.object(collect, "enrich", return_value={"enriched": 0, "dropped": 0}), \
                 patch("sys.argv", ["collect", "--no-notify"]):
                with self.assertRaises(SystemExit) as exc:
                    collect.main()
                self.assertEqual(exc.exception.code, 2)
            with closing(sqlite3.connect(db)) as conn:
                self.assertEqual(conn.execute("SELECT state FROM source_health").fetchone()[0], "failed")


class TestDerivedInformation(unittest.TestCase):
    def test_changed_deadline_invalidates_summary_and_excerpt(self):
        from funded_project_research.normalize import content_basis
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(str(Path(tmp) / "data.db"))
            self.addCleanup(store.close)
            old = NoticeRecord("kstartup", "1", "AI 모집", "u", deadline="2026-11-08",
                               summary="11월 8일 마감", key_dates="11월 8일", extraction_status="ok")
            old.summary_basis = old.extraction_basis = content_basis(old)
            store.upsert(old, "2026-11-01T00:00:00")
            store.commit()
            new = NoticeRecord("kstartup", "1", "AI 모집", "u", deadline="2026-11-30")
            collect.run(store, [new], datetime.fromisoformat("2026-11-12T00:00:00Z"), send=False)
            loaded = store.load()[old.key]
            self.assertNotIn("11월 8일", loaded.summary)
            self.assertEqual(loaded.extraction_status, "stale")
            self.assertEqual(loaded.key_dates, "11월 8일")  # 근거 원본은 보존, 화면에서 제외

    def test_neutral_fallback_does_not_invent_funding_or_always_open(self):
        rec = NoticeRecord("nara", "1", "AI 용역", "u")
        text = summarize._fallback(rec)
        self.assertIn("용역 입찰", text)
        self.assertIn("미확인", text)
        self.assertNotIn("지원사업", text)
        self.assertNotIn("상시", text)

    def test_extraction_does_not_refresh_notice_observation(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        rec = NoticeRecord("kstartup", "1", "AI 모집", "u", is_tech="1",
                           source_checked_at="2026-11-01T00:00:00Z")
        store.upsert(rec, "2026-11-01T00:00:00Z")
        rec.key_dates, rec.extraction_status = "원문", "ok"
        store.update_extraction(rec)
        row = store.conn.execute("SELECT first_seen,last_seen,source_checked_at FROM notices").fetchone()
        self.assertEqual(tuple(row), ("2026-11-01T00:00:00Z",) * 3)


class TestOfficialRecheck(unittest.TestCase):
    BIZ = '<span class="s_title">신청기간</span><div class="txt">2025.03.10 ~ 2025.04.09</div>'
    CAMP = '<p id="rcptPeriod">2026-09-28 ~ 2026-11-06 23:59</p><p id="aplyPeriod">2026.09.28(월) 00:00 ~ 2026.11.06(금) 23:59 까지</p>'

    def test_only_structured_period_is_accepted_and_conflicts_rejected(self):
        self.assertEqual(recheck.application_period("bizinfo", self.BIZ)[:2], ("2025-03-10", "2025-04-09"))
        self.assertEqual(recheck.application_period("kstartup", self.CAMP)[:2], ("2026-09-28 00:00", "2026-11-06 23:59"))
        for text in ['<p>추천 공고 2025.03.10 ~ 2025.04.09</p>', self.CAMP.replace('2026-11-06', '2026-11-15')]:
            with self.assertRaises(ValueError):
                recheck.application_period("kstartup", text)

    def test_dry_run_and_repeat_apply_preserve_records_and_alerts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "gov.db"
            store = Store(str(db))
            rec = NoticeRecord("bizinfo", "PBLN_1", "HFSP", "https://www.bizinfo.go.kr/test?pblancId=PBLN_1", deadline="2029-04-09")
            store.upsert(rec, "2026-06-30T00:00:00")
            store.mark_alert(rec.key, "new")
            store.commit(); store.close()
            before = hashlib.sha256(db.read_bytes()).hexdigest()
            with patch.object(recheck, "http_get", return_value=self.BIZ.encode()):
                result = recheck.recheck(db, keys=[rec.key])
                self.assertEqual(result["results"][0]["new_deadline"], "2025-04-09")
                self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(), before)
                recheck.recheck(db, keys=[rec.key], apply=True)
                recheck.recheck(db, keys=[rec.key], apply=True)
            with closing(sqlite3.connect(db)) as conn:
                self.assertEqual(conn.execute("SELECT key,deadline,first_seen,last_seen FROM notices").fetchone(),
                                 (rec.key, "2025-04-09", "2026-06-30T00:00:00", "2026-06-30T00:00:00"))
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM verifications").fetchone()[0], 1)
                self.assertEqual(conn.execute("SELECT * FROM alerts").fetchall(), [(rec.key, "new")])

    def test_untrusted_host_and_wrong_id_are_rejected(self):
        for url in ["https://evil.invalid/?pbancSn=1", "https://www.k-startup.go.kr/?pbancSn=2", "http://www.k-startup.go.kr/?pbancSn=1"]:
            self.assertFalse(recheck.allowed_url(NoticeRecord("kstartup", "1", "t", url)))

    def test_old_excerpt_stays_archived_when_official_dates_change(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        rec = NoticeRecord("kstartup", "1", "t", "u", deadline="2026-11-15",
                           key_dates="2026.11.15", extraction_status="ok")
        store.upsert(rec, "2026-10-26")
        result = recheck.check_notice(rec, self.CAMP.encode(), "2026-11-12T00:00:00Z")
        recheck.apply_check(store, rec, result)
        loaded = store.load()[rec.key]
        self.assertEqual(loaded.extraction_status, "stale")
        self.assertEqual(loaded.key_dates, "2026.11.15")

    def test_old_closed_flag_is_not_reopened_by_period_alone(self):
        store = Store(":memory:")
        self.addCleanup(store.close)
        rec = NoticeRecord("kstartup", "1", "t", "u", deadline="2026-11-15", status="N")
        store.upsert(rec, "2026-10-26")
        result = recheck.check_notice(rec, self.CAMP.encode(), "2026-11-01T00:00:00Z")
        recheck.apply_check(store, rec, result)
        self.assertEqual(store.load()[rec.key].status, "N")
