import io
import json
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stderr
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from funded_project_research import collect, reliability
from funded_project_research.adapters.msit import MsitAdapter
from funded_project_research.store import Store


TARGET = "funded_project_research.adapters.msit"
PROVIDER_ERROR = (b"<OpenAPI_ServiceResponse><cmmMsgHeader>"
                  b"<returnAuthMsg>HTTP_ERROR</returnAuthMsg><returnReasonCode>04</returnReasonCode>"
                  b"</cmmMsgHeader></OpenAPI_ServiceResponse>")


def _page_number(url):
    return int(parse_qs(urlparse(url).query)["pageNo"][0])


def _page_xml(page, total, notice=None):
    item = (f"<item><viewUrl>https://example.test/{page}?nttSeqNo={notice or page}"
            f"</viewUrl></item>")
    return (f"<response><header><resultCode>00</resultCode></header><body>"
            f"<items>{item}</items><pageNo>{page}</pageNo>"
            f"<totalCount>{total}</totalCount></body></response>").encode()


def _page_json(page, total, notice=None, page_size=1):
    item = {
        "viewUrl": f"https://example.test/{page}?nttSeqNo={notice or page}",
        "subject": "사업공고",
        "pressDt": "2020-01-02",
        "files": [{"file": {"fileName": "공고문.hwpx", "fileUrl": "https://example.test/file"}}],
    }
    return json.dumps({"response": [
        {"header": {"resultCode": "00"}},
        {"body": {"items": [{"item": item}], "pageNo": page,
                  "numOfRows": page_size, "totalCount": total}},
    ]}).encode()


class TestMsitPageRecovery(unittest.TestCase):
    def test_provider_error_keeps_later_pages_and_appears_in_reliability_report(self):
        def fetch(url):
            page = _page_number(url)
            if page == 330:
                return PROVIDER_ERROR
            if parse_qs(urlparse(url).query).get("returnType") == ["json"]:
                return _page_json(page, 334)
            return _page_xml(page, 334)

        adapter = MsitAdapter(service_key="private-test-value")
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Path(temp_dir) / "notices.db"
            store = Store(str(db))
            try:
                with patch(f"{TARGET}.http_get", side_effect=fetch) as get, \
                     patch.object(collect, "ADAPTERS", [lambda: adapter]), \
                     redirect_stderr(io.StringIO()) as log:
                    rows = collect.collect_all(store)
            finally:
                store.close()
            report = reliability.build_report(db, recheck=None)

        attempts = Counter(_page_number(call.args[0]) for call in get.call_args_list)
        self.assertEqual(attempts, {page: 2 if page == 330 else 1 for page in range(1, 335)})
        self.assertEqual(len(rows), 333)
        self.assertTrue(rows[-1].raw["viewUrl"].endswith("=334"))
        self.assertEqual(report["sources"][0]["state"], "partial")
        self.assertEqual(report["sources"][0]["pages"], 333)
        self.assertEqual(report["sources"][0]["error_kind"], "page_330_provider_04")
        self.assertIn("page_330_provider_04", log.getvalue())
        self.assertNotIn("private-test-value", log.getvalue())

    def test_recovery_runs_after_later_pages_and_requires_unique_notice_ids(self):
        for returned_id, state, detail in [(2, "success", ""), (3, "partial", "page_2_duplicate_notices")]:
            with self.subTest(returned_id=returned_id):
                requests = []

                def fetch(url):
                    params = parse_qs(urlparse(url).query)
                    page = int(params["pageNo"][0])
                    requested_format = params.get("returnType", ["xml"])[0]
                    requests.append((page, requested_format))
                    if page == 2:
                        if requested_format == "json":
                            self.assertEqual(params["numOfRows"], ["1"])
                            return _page_json(page, 4, returned_id)
                        return PROVIDER_ERROR
                    if requested_format == "json":
                        return _page_json(page, 4)
                    return _page_xml(page, 4)

                adapter = MsitAdapter(service_key="fixture")
                with patch(f"{TARGET}.http_get", side_effect=fetch), redirect_stderr(io.StringIO()) as log:
                    rows = adapter.collect()

                self.assertEqual(requests[-2:], [(4, "json"), (2, "json")])
                self.assertEqual((adapter.collection_state, adapter.collection_error), (state, detail))
                self.assertEqual([row.raw["viewUrl"].rsplit("=", 1)[-1] for row in rows],
                                 ["1", "2", "3", "4"] if state == "success" else ["1", "3", "4"])
                if state == "success":
                    self.assertIn("page 2 recovered (provider_04)", log.getvalue())
                    self.assertEqual(rows[1].raw["subject"], "사업공고")
                    self.assertEqual(rows[1].raw["pressDt"], "2020-01-02")
                    self.assertEqual(rows[1].raw["files"],
                                     [{"fileName": "공고문.hwpx", "fileUrl": "https://example.test/file"}])

    def test_multiple_later_xml_errors_do_not_exhaust_recovery_slots(self):
        requests = []

        def fetch(url):
            params = parse_qs(urlparse(url).query)
            page = int(params["pageNo"][0])
            requested_format = params.get("returnType", ["xml"])[0]
            requests.append((page, requested_format))
            if requested_format == "json":
                return _page_json(page, 7)
            if page in (2, 4, 5, 6, 7):
                return PROVIDER_ERROR
            return _page_xml(page, 7)

        adapter = MsitAdapter(service_key="fixture")
        with patch(f"{TARGET}.http_get", side_effect=fetch), \
             patch(f"{TARGET}.MAX_RECOVERY_PAGES", 1):
            rows = adapter.collect()

        self.assertCountEqual(requests, [(1, "xml"), (2, "xml"), (3, "xml"),
                                         (4, "json"), (5, "json"), (6, "json"), (7, "json"),
                                         (2, "json")])
        self.assertEqual([row.raw["viewUrl"].rsplit("=", 1)[-1] for row in rows],
                         [str(page) for page in range(1, 8)])
        self.assertEqual((adapter.collection_state, adapter.collection_error), ("success", ""))

    def test_json_fallback_rejects_wrong_page_or_size(self):
        for returned_page, returned_size, reason in [
            (3, 1, "page_number_mismatch"),
            (2, 2, "page_size_mismatch"),
        ]:
            with self.subTest(returned_page=returned_page, returned_size=returned_size):
                def fetch(url):
                    params = parse_qs(urlparse(url).query)
                    page = int(params["pageNo"][0])
                    if page != 2:
                        return _page_xml(page, 3)
                    if params.get("returnType") == ["json"]:
                        return _page_json(returned_page, 3, page_size=returned_size)
                    return PROVIDER_ERROR

                adapter = MsitAdapter(service_key="fixture")
                with patch(f"{TARGET}.http_get", side_effect=fetch) as get:
                    rows = adapter.collect()

                self.assertEqual(get.call_count, 4)
                self.assertEqual(len(rows), 2)
                self.assertEqual(adapter.collection_state, "partial")
                self.assertEqual(adapter.collection_error, f"page_2_{reason}")

    def test_changed_total_and_recovery_request_budget_stay_visible(self):
        def fetch(url):
            page = _page_number(url)
            return _page_xml(page, 5) if page in (2, 3) else _page_xml(page, 4)

        adapter = MsitAdapter(service_key="fixture")
        with patch(f"{TARGET}.http_get", side_effect=fetch) as get, \
             patch(f"{TARGET}.MAX_RECOVERY_PAGES", 1):
            rows = adapter.collect()

        attempts = Counter(_page_number(call.args[0]) for call in get.call_args_list)
        self.assertEqual(attempts, {1: 1, 2: 2, 3: 1, 4: 1})
        self.assertEqual(len(rows), 2)
        self.assertEqual(adapter.collection_state, "partial")
        self.assertEqual(adapter.collection_error, "page_2_total_changed, page_3_total_changed")

    def test_elapsed_budget_stops_requesting_pages(self):
        adapter = MsitAdapter(service_key="fixture")
        with patch(f"{TARGET}.http_get", side_effect=lambda url: _page_xml(_page_number(url), 5)) as get, \
             patch(f"{TARGET}.monotonic", side_effect=[0, 1, 721]):
            rows = adapter.collect()

        self.assertCountEqual([_page_number(call.args[0]) for call in get.call_args_list], [1, 2, 3])
        self.assertEqual(len(rows), 3)
        self.assertEqual((adapter.collection_state, adapter.collection_error), ("partial", "time_limit"))
