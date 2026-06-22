"""1주차 파이프라인 테스트. stdlib unittest, 외부 의존성 없음.

samples/ 실측 fixture 사용(무출처 금지 관례). 한글 JSON은 encoding='utf-8' 필수.
"""
import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import diff
import notify_email
from adapters.base import RawNotice
from adapters.iris import parse_detail, parse_rows
from adapters.msit import _item_to_dict
from dedupe import dedupe, dedupe_within_source, jaccard
from normalize import NoticeRecord, deadline_date, normalize, parse_deadline
from store import Store

SAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")


def _load_json(name):
    with open(os.path.join(SAMPLES, name), encoding="utf-8") as f:
        return json.load(f)


def rec(source="kstartup", sid="1", title="t", url="u", agency="a", deadline="", status="", attachments=""):
    return NoticeRecord(source=source, source_id=sid, title=title, url=url,
                        agency=agency, deadline=deadline, status=status, attachments=attachments)


class TestDeadlineParse(unittest.TestCase):
    def test_four_formats(self):
        self.assertEqual(parse_deadline("20260708"), "2026-07-08")          # K-Startup
        self.assertEqual(parse_deadline("2026-04-16"), "2026-04-16")        # 기업마당
        self.assertEqual(parse_deadline("2026-06-23 12:00:00"), "2026-06-23 12:00:00")  # 나라장터 입찰
        self.assertEqual(parse_deadline("2026-06-29 10:20"), "2026-06-29 10:20")        # 개방표준 결합

    def test_empty_and_garbage(self):
        self.assertEqual(parse_deadline(""), "")
        self.assertEqual(parse_deadline(None), "")
        self.assertEqual(parse_deadline("미정"), "")


class TestKey(unittest.TestCase):
    def test_key_format(self):
        self.assertEqual(rec("kstartup", "178198").key, "kstartup:178198")


class TestDedupe(unittest.TestCase):
    def test_within_source_zero_dup(self):  # acceptance #3
        a = rec("kstartup", "1")
        out = dedupe_within_source([a, rec("kstartup", "1"), rec("kstartup", "2")])
        self.assertEqual(len(out), 2)

    def test_jaccard(self):
        self.assertAlmostEqual(jaccard({"a", "b", "c", "d"}, {"a", "b", "c", "e"}), 3 / 5)

    def test_cross_source_match(self):  # acceptance #7
        r1 = rec("kstartup", "1", title="AI 창업 지원사업 공고", agency="중기부")
        r2 = rec("iris", "9", title="AI 창업 지원사업 공고", agency="중기부")
        self.assertEqual(len(dedupe([r1, r2])), 1)

    def test_cross_source_distinct_kept(self):
        r1 = rec("kstartup", "1", title="AI 창업 지원사업", agency="중기부")
        r2 = rec("iris", "9", title="해양 안전 실증 사업", agency="해수부")
        self.assertEqual(len(dedupe([r1, r2])), 2)


class TestImminent(unittest.TestCase):
    def test_d_thresholds(self):  # acceptance #4
        today = date(2026, 6, 22)
        d7 = rec(deadline="2026-06-29")
        d3 = rec(deadline="2026-06-25")
        d5 = rec(deadline="2026-06-27")  # 임계 아님
        res = {r.source_id: d for r, d in diff.find_imminent([d7, d3, d5], today)}
        self.assertEqual(diff.days_left(d7, today), 7)
        self.assertIn("1", res)  # 둘 다 source_id 기본 "1" → 마지막 우선; 개수로 검증
        hits = diff.find_imminent([d7, d3, d5], today)
        self.assertEqual(len(hits), 2)

    def test_no_deadline_skipped(self):  # A5 과기정통부
        self.assertIsNone(diff.days_left(rec(deadline=""), date(2026, 6, 22)))
        self.assertEqual(diff.find_imminent([rec(deadline="")], date(2026, 6, 22)), [])


class TestModified(unittest.TestCase):
    def test_watch_field_change(self):  # acceptance #5
        prev = {"kstartup:1": rec("kstartup", "1", deadline="2026-06-29")}
        cur = [rec("kstartup", "1", deadline="2026-07-10")]  # 마감 연장
        mods = diff.find_modified(prev, cur)
        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0].changes[0].field, "deadline")

    def test_no_change(self):
        prev = {"kstartup:1": rec("kstartup", "1", deadline="2026-06-29")}
        self.assertEqual(diff.find_modified(prev, [rec("kstartup", "1", deadline="2026-06-29")]), [])


class TestNormalizeSamples(unittest.TestCase):
    def test_kstartup_sample(self):  # acceptance #6 무출처 0건
        r = normalize(RawNotice("kstartup", _load_json("kstartup_sample.json")["data"][0]))
        self.assertEqual(r.source_id, "178198")
        self.assertTrue(r.title and r.url and r.agency)
        self.assertEqual(r.deadline, "2026-07-08")

    def test_bizinfo_sample(self):
        r = normalize(RawNotice("bizinfo", _load_json("bizinfo_mirror.json")["data"][0]))
        self.assertEqual(r.source_id, "PBLN_000000000106856")
        self.assertEqual(r.deadline, "2025-04-16")
        self.assertTrue(r.url and r.agency)

    def test_nara_sample(self):
        r = normalize(RawNotice("nara", _load_json("nara_servc.json")["response"]["body"]["items"][0]))
        self.assertEqual(r.source_id, "R26BK01577524")
        self.assertEqual(r.deadline, "2026-06-23 12:00:00")
        self.assertTrue(r.title and r.url and r.agency)

    def test_iris_sample(self):  # acceptance #2,#3,#6,#7 — 무출처 0건 + 마감 /→- 정규화
        r = normalize(RawNotice("iris", _load_json("iris_sample.json")["data"][0]))
        self.assertEqual(r.source_id, "022416")
        self.assertTrue(r.title and r.url and r.agency)
        self.assertEqual(r.agency, "과학기술정보통신부")
        self.assertEqual(r.specialized_agency, "한국연구재단")
        self.assertEqual(r.deadline, "2026-06-22")  # 2026/06/22 → 2026-06-22
        self.assertTrue(r.attachments)  # 상세 첨부 보강(#7)

    def test_msit_sample(self):  # 마감일 없음, 첨부 보존
        with open(os.path.join(SAMPLES, "msit_sample.xml"), encoding="utf-8") as f:
            root = ET.fromstring(f.read())
        r = normalize(RawNotice("msit", _item_to_dict(root.find(".//item"))))
        self.assertEqual(r.source_id, "3186787")
        self.assertEqual(r.deadline, "")
        self.assertTrue(r.attachments)
        self.assertTrue(r.url and r.agency)


IRIS_LI = (
    '<ul class="dbody"><li>'
    '<span class="inst_title">과학기술정보통신부 > 한국연구재단</span>'
    '<div class="form-row"><div class="group1"><strong class="title">'
    '<a href="" onclick="f_bsnsAncmListForm_view(\'022416\',\'2026\',\'S050239\',\'2\','
    '\'0\',\'2026/06/11\',\'2026/06/22\'); return false;">2026년 극한부품 시험입증지원사업</a>'
    '</strong></div><div class="group2">'
    '<span class="period" data-title="접수기간">2026/06/11~2026/06/22</span>'
    '</div></div></li></ul>'
)
IRIS_DETAIL = (
    '<li><em>공고번호</em><span>과학기술정보통신부 공고 제2026 - 687호</span></li>'
    '<a onclick="downloadAtchFile(\'D1\',\'F1\',\'[공고문] 재공고.pdf\',\'100\')">x</a>'
)


class TestIrisParse(unittest.TestCase):
    def test_row_parse(self):  # 고정 <li> → dict
        rows = parse_rows(IRIS_LI)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["ancmId"], "022416")
        self.assertEqual(row["sorgn"], "과학기술정보통신부")
        self.assertEqual(row["spcl"], "한국연구재단")
        self.assertEqual(row["rcveEndDt"], "2026/06/22")
        self.assertEqual(row["ancmTl"], "2026년 극한부품 시험입증지원사업")

    def test_detail_parse(self):
        d = parse_detail(IRIS_DETAIL)
        self.assertEqual(d["ancmNo"], "과학기술정보통신부 공고 제2026 - 687호")
        self.assertEqual(d["attachments"], "[공고문] 재공고.pdf")


class TestMessage(unittest.TestCase):
    def test_new_message_has_required_fields(self):  # acceptance #2
        r = rec("kstartup", "1", title="딥테크 공고", url="https://k.go.kr/x",
                agency="중기부", deadline="2026-07-08")
        subject, body = notify_email.build_message([r], [], [])
        for token in ("딥테크 공고", "중기부", "2026-07-08", "https://k.go.kr/x"):
            self.assertIn(token, body)

    def test_empty_returns_none(self):
        self.assertIsNone(notify_email.build_message([], [], []))


class TestRunPipeline(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.sent = []
        self._orig = notify_email.send
        notify_email.send = lambda s, b, transport=None: self.sent.append((s, b))

    def tearDown(self):
        notify_email.send = self._orig
        self.store.close()

    def test_new_then_recollect_zero(self):  # #1,#2,#3
        today = date(2026, 6, 22)
        r = rec("kstartup", "178198", title="딥테크", url="u", agency="중기부", deadline="2026-07-08")
        from collect import run
        out1 = run(self.store, [r], today)
        self.assertEqual(out1["new"], 1)
        self.assertEqual(len(self.sent), 1)
        # 재수집 → 신규 0
        out2 = run(self.store, [r], today)
        self.assertEqual(out2["new"], 0)

    def test_imminent_once(self):  # #4 중복 발송 없음
        from collect import run
        today = date(2026, 6, 22)
        r = rec("kstartup", "1", title="t", url="u", agency="a", deadline="2026-06-29")  # D-7
        out1 = run(self.store, [r], today)
        self.assertEqual(out1["imminent"], 1)
        out2 = run(self.store, [r], today)  # 같은 임계 재발송 안 함
        self.assertEqual(out2["imminent"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
