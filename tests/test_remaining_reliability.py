import contextlib
import io
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

from funded_project_research.adapters.nara import NaraAdapter
from funded_project_research.adapters.iris import IrisAdapter, LIST_URL
from funded_project_research.adapters.msit import MsitAdapter
from test_source_retries import nara_page, iris_page, IRIS_DETAIL
from test_msit_recovery import _page_xml, _page_number


class TestDeferredRecovery(unittest.TestCase):
    def setUp(self):
        for target in ('time.sleep',):
            p = patch(target)
            p.start()
            self.addCleanup(p.stop)
        p = contextlib.redirect_stderr(io.StringIO())
        p.__enter__()
        self.addCleanup(p.__exit__, None, None, None)

    def test_nara_recovers_failed_page_after_later_pages(self):
        calls = []
        def fetch(url, **kwargs):
            page = int(parse_qs(urlparse(url).query)['pageNo'][0])
            calls.append(page)
            if page == 2 and calls.count(2) <= 2:
                raise TimeoutError()
            return nara_page(*([str(page)] if page <= 3 else []), total=3)
        a = NaraAdapter(service_key='fixture')
        with patch('funded_project_research.adapters.nara.http_get_json', side_effect=fetch):
            rows = a.collect()
        self.assertEqual({r.raw['bidNtceNo'] for r in rows}, {'1', '2', '3'})
        self.assertEqual(a.collection_state, 'success')
        self.assertGreater(calls.index(3), calls.index(2))
        self.assertEqual(calls[-1], 2)

    def test_nara_recovery_rejects_duplicate_or_changed_total(self):
        for recovered, reason in ((nara_page('1', total=3), 'duplicate_notices'),
                                  (nara_page('2', total=4), 'total_changed')):
            with self.subTest(reason=reason):
                a = NaraAdapter(service_key='fixture')
                with patch('funded_project_research.adapters.nara.http_get_json', side_effect=[
                    nara_page('1', total=3), TimeoutError(), TimeoutError(),
                    nara_page('3', total=3), nara_page(total=3), recovered,
                ]):
                    a.collect()
                self.assertEqual((a.collection_state, a.collection_error), ("partial", "list_" + reason))
                self.assertEqual(len(a.records), 2)

    def test_recovery_respects_exhausted_retry_and_time_budgets(self):
        from funded_project_research.adapters.base import SourceError
        from funded_project_research.adapters.retry import SourceRequests, RequestTimeLimit
        from unittest.mock import Mock
        requests = SourceRequests('fixture')
        fetch = Mock()
        requests.retries_left = 0
        with self.assertRaisesRegex(SourceError, 'retry_limit'):
            requests.recover('list', 'page=2', fetch, 'fixture')
        requests.retries_left = 1
        requests.deadline = 0
        with self.assertRaises(RequestTimeLimit):
            requests.recover('list', 'page=2', fetch, 'fixture')
        fetch.assert_not_called()

    def test_iris_recovers_temporary_detail_failure_after_other_details(self):
        calls = []
        def fetch(url, fields, **kwargs):
            if url == LIST_URL:
                return iris_page('1', '2')
            notice = fields['ancmId']
            calls.append(notice)
            if notice == '1' and calls.count('1') <= 2:
                raise TimeoutError()
            return IRIS_DETAIL
        a = IrisAdapter(interval=0)
        with patch('funded_project_research.adapters.iris.http_post', side_effect=fetch):
            rows = a.collect()
        self.assertTrue(all('attachments' in r.raw for r in rows))
        self.assertEqual(a.collection_state, 'success')
        self.assertEqual(calls, ['1', '1', '2', '1'])

    def test_msit_recovery_retries_transient_failure_within_bound(self):
        calls = []
        def fetch(url, **kwargs):
            page = _page_number(url)
            calls.append(page)
            if page == 2 and calls.count(2) <= 2:
                raise URLError('temporary')
            return _page_xml(page, 3)
        a = MsitAdapter(service_key='fixture')
        with patch('funded_project_research.adapters.msit.http_get', side_effect=fetch):
            rows = a.collect()
        self.assertEqual(len(rows), 3)
        self.assertEqual(a.collection_state, 'success')
        self.assertEqual(calls.count(2), 3)

class TestKStartupFullCollection(unittest.TestCase):
    def test_default_collects_beyond_old_fifty_page_limit(self):
        from funded_project_research.adapters.kstartup import KStartupAdapter
        def fetch(url, **kwargs):
            page = int(parse_qs(urlparse(url).query)['page'][0])
            return {'data': [{'pbanc_sn': str(page)}] if page <= 51 else [], 'totalCount': 51}
        a = KStartupAdapter(service_key='fixture', per_page=1)
        with patch('funded_project_research.adapters.kstartup.http_get_json', side_effect=fetch):
            rows = a.collect()
        self.assertEqual(len(rows), 51)
        self.assertEqual(a.collection_state, 'success')

    def test_explicit_page_limit_still_reports_partial(self):
        from funded_project_research.adapters.kstartup import KStartupAdapter
        a = KStartupAdapter(service_key='fixture', max_pages=2)
        with patch('funded_project_research.adapters.kstartup.http_get_json', side_effect=[
            {'data': [{'pbanc_sn': '1'}], 'totalCount': 3},
            {'data': [{'pbanc_sn': '2'}], 'totalCount': 3},
        ]):
            a.collect()
        self.assertEqual((a.collection_state, a.collection_error), ('partial', 'page_limit'))
