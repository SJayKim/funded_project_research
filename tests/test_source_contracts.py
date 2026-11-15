import unittest
import json
from threading import Barrier
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from funded_project_research.adapters.iris import IrisAdapter, parse_rows
from funded_project_research.adapters.nara import NaraAdapter
from funded_project_research.adapters.msit import MsitAdapter
from funded_project_research.status import KST
from funded_project_research.normalize import NoticeRecord
from funded_project_research.store import Store


class TestSourceContracts(unittest.TestCase):
    ROW = '''<span class="inst_title">기관</span>
    <a onclick="f_bsnsAncmListForm_view('024439','2026','S1','1','1','2026/11/03','2026/11/16')">공고</a>
    <span class="period">2026/11/03 ~ 2026/11/16</span>'''

    def test_iris_ignores_jsrender_template_and_does_not_fetch_its_detail(self):
        template = self.ROW.replace('024439', '{{:ancmId}}')
        html = ('<span class="current_page"><strong>1</strong>/1</span>' + self.ROW
                + '<script id="listTemplate" type="text/x-jsrender">' + template + '</script>')
        self.assertEqual([r['ancmId'] for r in parse_rows(html)], ['024439'])
        with patch('funded_project_research.adapters.iris.http_post',
                   side_effect=[html.encode(), '<em>공고번호</em><span>2026-1</span>'.encode()]) as fetch:
            rows = IrisAdapter(interval=0).collect()
        self.assertEqual(len(rows), 1)
        self.assertEqual(fetch.call_count, 2)

    def test_nara_default_query_covers_seven_calendar_dates(self):
        now = datetime(2026, 11, 15, 12, 30, tzinfo=KST)
        def response(url):
            query = parse_qs(urlparse(url).query)
            begin = datetime.strptime(query['inqryBgnDt'][0], '%Y%m%d%H%M')
            end = datetime.strptime(query['inqryEndDt'][0], '%Y%m%d%H%M')
            self.assertEqual((end.date() - begin.date()).days + 1, 7)
            self.assertEqual(begin.hour, 0)
            return {'response': {'header': {'resultCode': '00'},
                                 'body': {'items': [], 'totalCount': 0}}}
        with patch('funded_project_research.adapters.nara.http_get_json', side_effect=response):
            self.assertEqual(NaraAdapter(service_key='fixture', now=now).collect(), [])

    def test_iris_retries_connection_failure_once(self):
        html = '<span class="current_page"><strong>1</strong>/1</span>' + self.ROW
        with patch('funded_project_research.adapters.iris.http_post',
                   side_effect=[TimeoutError(), html.encode()]):
            self.assertEqual(len(IrisAdapter(detail=False).collect()), 1)
        with patch('funded_project_research.adapters.iris.http_post', side_effect=TimeoutError()) as fetch:
            with self.assertRaises(TimeoutError):
                IrisAdapter(detail=False).collect()
            self.assertEqual(fetch.call_count, 2)

    def test_msit_reads_past_fifty_pages_with_server_capped_page_size(self):
        def response(url):
            page = int(parse_qs(urlparse(url).query)['pageNo'][0])
            items = ''.join(f'<item><viewUrl>https://example.test/{i}</viewUrl></item>'
                            for i in range((page - 1) * 10, min(page * 10, 503)))
            return (f'<response><header><resultCode>00</resultCode></header><body>'
                    f'<items>{items}</items><totalCount>503</totalCount>'
                    f'<numOfRows>10</numOfRows></body></response>').encode()
        with patch('funded_project_research.adapters.msit.http_get', side_effect=response) as fetch:
            adapter = MsitAdapter(service_key='fixture')
            self.assertEqual(len(adapter.collect()), 503)
            self.assertEqual(adapter.collection_state, 'success')
            self.assertEqual(fetch.call_count, 51)

    def test_msit_recovers_one_timeout_but_keeps_persistent_failure_visible(self):
        page = (b'<response><body><items><item><viewUrl>https://example.test/1</viewUrl>'
                b'</item></items><totalCount>1</totalCount></body></response>')
        with patch('funded_project_research.adapters.msit.http_get', side_effect=[TimeoutError(), page]):
            self.assertEqual(len(MsitAdapter(service_key='fixture').collect()), 1)
        with patch('funded_project_research.adapters.msit.http_get', side_effect=TimeoutError()) as fetch:
            with self.assertRaises(TimeoutError):
                MsitAdapter(service_key='fixture').collect()
            self.assertEqual(fetch.call_count, 2)

    def test_msit_parallel_pages_keep_order_and_respect_explicit_cap(self):
        ready = Barrier(2)
        def response(url):
            page = int(parse_qs(urlparse(url).query)['pageNo'][0])
            if page > 1:
                ready.wait(timeout=3)
            return (f'<response><body><items><item><viewUrl>https://example.test/{page}</viewUrl>'
                    f'</item></items><totalCount>10</totalCount></body></response>').encode()
        with patch('funded_project_research.adapters.msit.http_get', side_effect=response) as fetch:
            adapter = MsitAdapter(service_key='fixture', max_pages=3)
            rows = adapter.collect()
            self.assertEqual([r.raw['viewUrl'] for r in rows],
                             [f'https://example.test/{i}' for i in range(1, 4)])
            self.assertEqual(fetch.call_count, 3)
            self.assertEqual((adapter.collection_state, adapter.collection_error), ('partial', 'page_limit'))

    def test_existing_iris_template_is_archived_without_losing_real_notices_or_alerts(self):
        store = Store(':memory:')
        self.addCleanup(store.close)
        fake = NoticeRecord('iris', '{{:ancmId}}', '{{:ancmTl}}', 'https://www.iris.go.kr/template')
        real = NoticeRecord('iris', '024439', '실제 공고', 'https://www.iris.go.kr/real')
        for row in (fake, real):
            store.upsert(row, '2026-11-15T00:00:00Z')
            store.mark_alert(row.key, 'new')
        store.commit()
        before = dict(store.conn.execute('SELECT * FROM notices WHERE key=?', (fake.key,)).fetchone())
        store._init_schema()
        store._init_schema()
        self.assertEqual(set(store.load()), {real.key})
        archived = store.conn.execute('SELECT record_json FROM quarantined_notices WHERE key=?', (fake.key,)).fetchall()
        self.assertEqual([json.loads(r[0]) for r in archived], [before])
        self.assertTrue(store.alert_sent(fake.key, 'new'))
        self.assertTrue(store.alert_sent(real.key, 'new'))


if __name__ == '__main__':
    unittest.main()
