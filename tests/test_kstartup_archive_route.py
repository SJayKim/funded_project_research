import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from funded_project_research import collect, recheck
from funded_project_research.normalize import NoticeRecord
from funded_project_research.store import Store

ONGOING = 'https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?schM=view&pbancSn=179705'
ARCHIVE = 'https://www.k-startup.go.kr/web/contents/bizpbanc-deadline.do?pbancSn=179705&schM=view'
DETAIL = b'<p id="aplyPeriod">2026-11-01 ~ 2026-11-10 18:00</p>'


class TestKStartupArchiveRoute(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / 'notices.db'
        self.store = Store(str(self.db))
        self.addCleanup(self.store.close)
        self.rec = NoticeRecord(source='kstartup', source_id='179705', title='fixture', url=ONGOING)
        self.store.upsert(self.rec, '2026-11-01')
        self.store.commit()

    def test_empty_ongoing_detail_uses_same_notice_archive_and_preserves_link(self):
        with patch.object(recheck, 'http_get', side_effect=[b'<html>empty detail shell</html>', DETAIL]) as fetch:
            result = recheck.recheck(self.db, keys=[self.rec.key], apply=True)
        self.assertEqual(result['results'][0]['result'], 'confirmed')
        self.assertEqual(result['results'][0]['url'], ARCHIVE)
        self.assertEqual(fetch.call_args_list[1].args[0], ARCHIVE)
        self.assertEqual(self.store.load()[self.rec.key].url, ARCHIVE)
        collect.run(self.store, [self.rec], date(2026, 11, 23), send=False)
        self.assertEqual(self.store.load()[self.rec.key].url, ARCHIVE)

    def test_access_denial_does_not_try_archive(self):
        with patch.object(recheck, 'http_get', side_effect=HTTPError(ONGOING, 403, 'denied', {}, None)) as fetch:
            result = recheck.recheck(self.db, keys=[self.rec.key])
        self.assertEqual(result['results'][0]['reason'], 'HTTPError')
        self.assertEqual(fetch.call_count, 1)

    def test_empty_archive_still_fails_without_changing_source_link(self):
        with patch.object(recheck, 'http_get', return_value=b'<html>empty</html>') as fetch:
            result = recheck.recheck(self.db, keys=[self.rec.key], apply=True)
        self.assertEqual(result['results'][0]['reason'], 'period_missing')
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(self.store.load()[self.rec.key].url, ONGOING)
