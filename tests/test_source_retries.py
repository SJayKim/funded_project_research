import contextlib
import io
import ssl
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from funded_project_research import collect
from funded_project_research.adapters.iris import IrisAdapter, LIST_URL, VIEW_URL
from funded_project_research.adapters.nara import NaraAdapter
from funded_project_research.adapters.retry import RequestTimeLimit, SourceRequests
from funded_project_research.normalize import NoticeRecord
from funded_project_research.store import Store


def nara_page(*notice_ids, total):
    return {"response": {"header": {"resultCode": "00"}, "body": {
        "items": [{"bidNtceNo": notice_id} for notice_id in notice_ids],
        "totalCount": total,
    }}}


def iris_page(*notice_ids, page=1, pages=1):
    heading = f'<span class="current_page"><strong>{page}</strong>/{pages}</span>'
    rows = [
        '<span class="inst_title">기관</span>'
        f'<a onclick="f_bsnsAncmListForm_view(\'{notice_id}\',\'2026\',\'S1\',\'1\',\'1\',\'2026/11/03\',\'2026/11/16\')">'
        f'공고 {notice_id}</a><span class="period">2026/11/03 ~ 2026/11/16</span>'
        for notice_id in notice_ids
    ]
    return (heading + "".join(rows)).encode()


IRIS_DETAIL = '<em>공고번호</em><span>2026-1</span>'.encode()


class TestSourceRetries(unittest.TestCase):
    def setUp(self):
        get = patch("funded_project_research.adapters.iris.http_get", side_effect=TimeoutError())
        get.start()
        self.addCleanup(get.stop)
        sleep = patch("funded_project_research.adapters.retry.time.sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)
        self.log = io.StringIO()
        errors = contextlib.redirect_stderr(self.log)
        errors.__enter__()
        self.addCleanup(errors.__exit__, None, None, None)

    def test_nara_retries_same_page_with_delay_without_logging_request_url(self):
        with patch("funded_project_research.adapters.nara.http_get_json", side_effect=[
            URLError("url with serviceKey=private-test-value"), nara_page("A", total=1), nara_page(total=1)
        ]) as fetch:
            adapter = NaraAdapter(service_key="private-test-value")
            self.assertEqual([r.raw["bidNtceNo"] for r in adapter.collect()], ["A"])
        calls = [parse_qs(urlparse(call.args[0]).query)["pageNo"][0] for call in fetch.call_args_list]
        self.assertEqual(calls, ["1", "1", "2"])
        self.sleep.assert_called_once_with(SourceRequests.RETRY_DELAY)
        self.assertEqual(adapter.collection_state, "success")
        self.assertIn("nara list page=1 at=", self.log.getvalue())
        self.assertIn("attempt=1 retry_scheduled kind=network", self.log.getvalue())
        self.assertIn("attempt=2 recovered", self.log.getvalue())
        self.assertNotIn("private-test-value", self.log.getvalue())

    def test_nara_preserves_data_before_and_after_unresolved_page(self):
        with patch("funded_project_research.adapters.nara.http_get_json", side_effect=[
            nara_page("A", total=3), TimeoutError(), TimeoutError(),
            nara_page("C", total=3), nara_page(total=3), TimeoutError(), TimeoutError(),
        ]):
            adapter = NaraAdapter(service_key="stub")
            self.assertEqual([r.raw["bidNtceNo"] for r in adapter.collect()], ["A", "C"])
        self.assertEqual((adapter.collection_state, adapter.collection_error), ("partial", "list_timeout"))
        self.assertIn("nara list page=2", self.log.getvalue())
        self.assertIn("attempt=2 request_failed kind=timeout", self.log.getvalue())

    def test_nara_bounds_consecutive_failures_and_keeps_first_page(self):
        with patch("funded_project_research.adapters.nara.http_get_json", side_effect=[
            nara_page("A", total=5), *[TimeoutError() for _ in range(6)],
        ]) as fetch:
            adapter = NaraAdapter(service_key="stub")
            self.assertEqual([r.raw["bidNtceNo"] for r in adapter.collect()], ["A"])
        self.assertEqual(adapter.collection_state, "partial")
        self.assertEqual(fetch.call_count, 7)

    def test_nara_access_denial_stops_after_single_request(self):
        error = HTTPError("https://example.test/?serviceKey=private-test-value", 403, "denied", {}, None)
        with patch("funded_project_research.adapters.nara.http_get_json", side_effect=error) as fetch:
            with self.assertRaises(HTTPError):
                NaraAdapter(service_key="private-test-value").collect()
        fetch.assert_called_once()
        self.sleep.assert_not_called()
        self.assertIn("request_failed kind=http_403", self.log.getvalue())
        self.assertNotIn("private-test-value", self.log.getvalue())

    def test_retry_budget_is_shared_and_stops_at_deadline(self):
        with patch("funded_project_research.adapters.retry.time.monotonic", return_value=0) as now:
            requests = SourceRequests("nara")
            for page in range(1, SourceRequests.MAX_RETRIES + 1):
                with patch("funded_project_research.adapters.nara.http_get_json",
                           side_effect=[TimeoutError(), {}]) as fetch:
                    requests.fetch("list", f"page={page}", fetch, "fixture")
                    self.assertEqual(fetch.call_count, 2)
            with patch("funded_project_research.adapters.nara.http_get_json",
                       side_effect=TimeoutError()) as fetch:
                with self.assertRaises(TimeoutError):
                    requests.fetch("list", "page=9", fetch, "fixture")
                fetch.assert_called_once()
                now.return_value = SourceRequests.SOURCE_SECONDS
                fetch.reset_mock()
                with self.assertRaises(RequestTimeLimit):
                    requests.fetch("list", "page=10", fetch, "fixture")
                fetch.assert_not_called()

    def test_certificate_error_is_not_retried(self):
        error = URLError(ssl.SSLCertVerificationError("fixture"))
        with patch("funded_project_research.adapters.nara.http_get_json", side_effect=error) as fetch:
            with self.assertRaises(URLError):
                NaraAdapter(service_key="stub").collect()
        fetch.assert_called_once()
        self.assertIn("request_failed kind=tls", self.log.getvalue())

    def test_iris_rechecks_same_list_page_and_preserves_later_rows(self):
        with patch("funded_project_research.adapters.iris.http_post", side_effect=[
            iris_page("1", pages=3), ConnectionResetError(), ConnectionResetError(),
            iris_page("3", page=3, pages=3),
        ]) as fetch:
            adapter = IrisAdapter(detail=False)
            self.assertEqual([r.raw["ancmId"] for r in adapter.collect()], ["1", "3"])
        self.assertEqual([call.args[1]["pageIndex"] for call in fetch.call_args_list], [1, 2, 2, 3])
        self.assertEqual((adapter.collection_state, adapter.collection_error), ("partial", "list_network"))
        self.assertIn("iris list page=2", self.log.getvalue())

    def test_iris_retries_eligible_detail_and_continues_past_unavailable_detail(self):
        failure = HTTPError(VIEW_URL, 404, "missing", {}, None)
        with patch("funded_project_research.adapters.iris.http_post", side_effect=[
            iris_page("1", "2"), TimeoutError(), IRIS_DETAIL, failure,
        ]) as fetch:
            adapter = IrisAdapter(interval=0)
            rows = adapter.collect()
        self.assertEqual([(row.raw["ancmId"], "attachments" in row.raw) for row in rows],
                         [("1", True), ("2", False)])
        calls = [(call.args[0], call.args[1].get("ancmId")) for call in fetch.call_args_list]
        self.assertEqual(calls, [(LIST_URL, None), (VIEW_URL, "1"), (VIEW_URL, "1"), (VIEW_URL, "2")])
        self.assertEqual((adapter.collection_state, adapter.collection_error), ("partial", "detail_http_404"))
        self.assertIn("iris detail notice=1", self.log.getvalue())
        self.assertIn("attempt=2 recovered", self.log.getvalue())

    def test_iris_distinguishes_detail_variants_and_reports_wrapped_timeout(self):
        variants = iris_page("19508", "19508").replace(b"'S1','1','1'", b"'S1','2','1'", 1)
        error = URLError(TimeoutError("fixture"))
        with patch("funded_project_research.adapters.iris.http_post", side_effect=[
            variants, error, error, IRIS_DETAIL, error, error,
        ]) as fetch:
            adapter = IrisAdapter(interval=0)
            rows = adapter.collect()
        sequence_calls = [call.args[1]["bsnsAncmSn"] for call in fetch.call_args_list[1:]]
        self.assertEqual(sequence_calls, ["2", "2", "1", "2", "2"])
        self.assertEqual(["attachments" in row.raw for row in rows], [False, True])
        self.assertEqual((adapter.collection_state, adapter.collection_error), ("partial", "detail_timeout"))
        self.assertIn("iris detail notice=19508 sequence=2 at=", self.log.getvalue())
        self.assertIn("attempt=2 request_failed kind=timeout", self.log.getvalue())

    def test_unavailable_iris_detail_preserves_attachment_during_real_collection_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "test.db")
            data = Store(db)
            for notice_id in ["1", "2"]:
                old = NoticeRecord("iris", notice_id, f"공고 {notice_id}", "https://example.test",
                                   deadline="2026-11-16", attachments=f"old-{notice_id}.pdf")
                data.upsert(old, "2026-11-21T10:00:00Z")
            data.commit()
            data.close()
            with (patch.object(collect, "Store", side_effect=lambda: Store(db)),
                  patch.object(collect, "ADAPTERS", [IrisAdapter]),
                  patch.object(collect, "enrich", return_value={"skipped_no_key": True}),
                  patch.object(collect.sys, "argv", ["collect", "--no-notify"]),
                  patch("funded_project_research.adapters.iris.http_post", side_effect=[
                      iris_page("1", "2"), TimeoutError(), TimeoutError(), IRIS_DETAIL, TimeoutError(), TimeoutError(),
                  ]), contextlib.redirect_stdout(io.StringIO())):
                with self.assertRaises(SystemExit) as exit_code:
                    collect.main()
                self.assertEqual(exit_code.exception.code, 2)
            data = Store(db)
            try:
                records = data.load()
                self.assertEqual(records["iris:1"].attachments, "old-1.pdf")
                self.assertEqual(records["iris:2"].attachments, "")
                self.assertFalse(data.alert_sent("iris:1", "modified"))
                self.assertTrue(data.alert_sent("iris:2", "modified"))
                self.assertEqual(data.source_health()[0]["state"], "partial")
            finally:
                data.close()
