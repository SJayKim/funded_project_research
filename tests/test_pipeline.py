"""1주차 파이프라인 테스트. stdlib unittest, 외부 의존성 없음.

samples/ 실측 fixture 사용(무출처 금지 관례). 한글 JSON은 encoding='utf-8' 필수.
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import classify
import diff
import notify_email
import serve
import summarize
from adapters.base import RawNotice
from adapters.iris import parse_detail, parse_rows
from adapters.msit import _item_to_dict
from dedupe import dedupe, dedupe_within_source, jaccard
from normalize import NoticeRecord, deadline_date, normalize, normalize_text, parse_deadline
from store import Store

SAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")


def _load_json(name):
    with open(os.path.join(SAMPLES, name), encoding="utf-8") as f:
        return json.load(f)


def rec(source="kstartup", sid="1", title="t", url="u", agency="a", deadline="", status="",
        attachments="", target="", category="", summary="", is_tech=""):
    return NoticeRecord(source=source, source_id=sid, title=title, url=url,
                        agency=agency, target=target, deadline=deadline, status=status,
                        attachments=attachments, category=category, summary=summary, is_tech=is_tech)


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


class TestNormalizeText(unittest.TestCase):
    def test_html_entities_decoded(self):  # K-Startup 제목 &apos; 등 정리
        self.assertEqual(normalize_text("It&apos;s AI &amp; R&amp;D 공고"), "It's AI & R&D 공고")
        self.assertEqual(normalize_text("&lt;딥테크&gt; &#39;공고&#39;"), "<딥테크> '공고'")

    def test_nbsp_collapsed(self):  # &nbsp; → 공백 → 단일 공백
        self.assertEqual(normalize_text("AI&nbsp;&nbsp;공고"), "AI 공고")

    def test_empty_and_plain_unchanged(self):
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text(None), "")
        self.assertEqual(normalize_text("  보통 텍스트  "), "보통 텍스트")


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
    def test_new_message_has_required_fields(self):  # acceptance #2 (제목·요약·마감·url)
        r = rec("kstartup", "1", title="딥테크 공고", url="https://k.go.kr/x",
                agency="중기부", deadline="2026-07-08", summary="딥테크 R&D를 지원하는 공고")
        subject, body = notify_email.build_message([r], [], [])
        for token in ("딥테크 공고", "딥테크 R&D를 지원하는 공고", "2026-07-08", "https://k.go.kr/x"):
            self.assertIn(token, body)

    def test_summary_falls_back_to_title(self):  # 요약 없으면 제목 노출
        r = rec("kstartup", "1", title="요약없는공고", url="u", agency="중기부", deadline="2026-07-08")
        _, body = notify_email.build_message([r], [], [])
        self.assertIn("요약없는공고", body)

    def test_empty_returns_none(self):
        self.assertIsNone(notify_email.build_message([], [], []))


class TestRunPipeline(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.sent = []
        self._orig = notify_email.send
        notify_email.send = lambda s, b, transport=None: self.sent.append((s, b))
        # 요약은 결정적 스텁(네트워크/키 의존 제거).
        self._orig_sum = summarize.summarize
        summarize.summarize = lambda recs: {r.key: "요약" for r in recs}

    def tearDown(self):
        notify_email.send = self._orig
        summarize.summarize = self._orig_sum
        self.store.close()

    def test_new_then_recollect_zero(self):  # #1,#2,#3 (메일 tech-only → 제목을 기술로)
        today = date(2026, 6, 22)
        r = rec("kstartup", "178198", title="AI 딥테크 공고", url="u", agency="중기부", deadline="2026-07-08")
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
        r = rec("kstartup", "1", title="AI 솔루션 공고", url="u", agency="a", deadline="2026-06-29")  # D-7
        out1 = run(self.store, [r], today)
        self.assertEqual(out1["imminent"], 1)
        out2 = run(self.store, [r], today)  # 같은 임계 재발송 안 함
        self.assertEqual(out2["imminent"], 0)


class TestClassify(unittest.TestCase):
    def test_ai_category(self):
        cat, tech = classify.classify(rec(title="생성형 AI 기반 업무자동화 R&D"))
        self.assertEqual((cat, tech), ("AI/생성형AI", "1"))

    def test_manufacturing(self):
        cat, tech = classify.classify(rec(title="스마트팩토리 예지보전 실증사업"))
        self.assertEqual((cat, tech), ("제조AI", "1"))

    def test_saas_english_lowercased(self):  # 영문 토큰 .lower() 매칭
        cat, tech = classify.classify(rec(title="SaaS 전환 지원사업"))
        self.assertEqual((cat, tech), ("클라우드/SaaS", "1"))

    def test_non_tech(self):
        self.assertEqual(classify.classify(rec(title="소상공인 경영 컨설팅 지원")), ("기타", "0"))

    def test_declaration_order_deterministic(self):  # AI가 데이터보다 먼저 선언 → 첫 매칭 승
        cat, _ = classify.classify(rec(title="AI 데이터 구축 사업"))
        self.assertEqual(cat, "AI/생성형AI")

    def test_agency_excluded(self):  # 기관명에 기술 키워드 있어도 제목/대상만으로 판정
        cat, tech = classify.classify(rec(title="일반 행정 효율화", agency="인공지능산업진흥원"))
        self.assertEqual((cat, tech), ("기타", "0"))


class TestStoreMigration(unittest.TestCase):
    def test_fresh_has_new_columns(self):
        s = Store(":memory:")
        cols = {row["name"] for row in s.conn.execute("PRAGMA table_info(notices)")}
        self.assertTrue({"category", "summary", "is_tech"} <= cols)
        s.close()

    def test_alter_old_table_and_null_fill(self):  # 구 13컬럼 → ALTER + 멱등 + NULL→""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            conn = sqlite3.connect(path)
            conn.execute(
                "CREATE TABLE notices (key TEXT PRIMARY KEY, source TEXT, source_id TEXT, "
                "title TEXT, url TEXT, agency TEXT, specialized_agency TEXT, target TEXT, "
                "deadline TEXT, status TEXT, attachments TEXT, first_seen TEXT, last_seen TEXT)"
            )
            conn.execute("INSERT INTO notices (key, source, source_id, title) "
                         "VALUES ('kstartup:1','kstartup','1','t')")
            conn.commit()
            conn.close()

            s = Store(path)  # _migrate가 누락 컬럼 추가
            cols = {row["name"] for row in s.conn.execute("PRAGMA table_info(notices)")}
            self.assertTrue({"category", "summary", "is_tech"} <= cols)
            loaded = s.load()
            self.assertEqual(loaded["kstartup:1"].summary, "")   # NULL→""
            self.assertEqual(loaded["kstartup:1"].is_tech, "")
            s.close()

            s2 = Store(path)  # 멱등: 재오픈 에러 없음
            s2.close()
        finally:
            os.unlink(path)


class TestSummaryCaching(unittest.TestCase):
    """collect.run의 요약 게이트(신규∩tech∩미캐시 / 시딩 생략 / 재요약 방지)."""

    def setUp(self):
        self.store = Store(":memory:")
        self.calls = []
        self._orig_sum = summarize.summarize
        summarize.summarize = self._count
        self._orig_send = notify_email.send
        notify_email.send = lambda *a, **k: None

    def _count(self, recs):
        self.calls.append([r.key for r in recs])
        return {r.key: "LLM요약" for r in recs}

    def tearDown(self):
        summarize.summarize = self._orig_sum
        notify_email.send = self._orig_send
        self.store.close()

    def test_only_new_tech_summarized(self):
        from collect import run
        tech = rec("kstartup", "1", title="AI 자동화 R&D")
        nontech = rec("bizinfo", "2", title="전통시장 환경개선 지원")
        run(self.store, [tech, nontech], date(2026, 6, 22))
        self.assertEqual(self.calls[0], ["kstartup:1"])  # 기술 신규만 요약

    def test_no_resummarize_on_recollect(self):
        from collect import run
        today = date(2026, 6, 22)
        run(self.store, [rec("kstartup", "1", title="AI 자동화 R&D")], today)
        self.assertEqual(self.calls[0], ["kstartup:1"])
        run(self.store, [rec("kstartup", "1", title="AI 자동화 R&D")], today)  # 새 객체 재수집
        self.assertEqual(self.calls[1], [])              # 캐시 유지 → 재요약 0건

    def test_no_notify_skips_summary(self):
        from collect import run
        run(self.store, [rec("kstartup", "1", title="AI 자동화 R&D")], date(2026, 6, 22), send=False)
        self.assertEqual(self.calls[0], [])              # 시딩엔 LLM 호출 0건


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._payload


class TestSummarizeRequest(unittest.TestCase):
    """summarize.summarize 자체: 키 없음 fallback / 요청 body 금지 파라미터 부재."""

    def tearDown(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_no_key_fallback_no_network(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        called = []
        orig = summarize.urllib.request.urlopen
        summarize.urllib.request.urlopen = lambda *a, **k: called.append(1)
        try:
            out = summarize.summarize([rec("kstartup", "1", title="AI 공고", agency="중기부")])
        finally:
            summarize.urllib.request.urlopen = orig
        self.assertEqual(called, [])              # 네트워크 호출 0
        self.assertTrue(out["kstartup:1"])        # fallback 문자열 존재

    def test_request_body_has_no_forbidden_params(self):
        captured = {}

        def fake(req, timeout=30):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeResp(json.dumps({"content": [{"type": "text", "text": "요약문"}]}).encode("utf-8"))

        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        orig = summarize.urllib.request.urlopen
        summarize.urllib.request.urlopen = fake
        try:
            out = summarize.summarize([rec("kstartup", "1", title="AI 공고", agency="중기부")])
        finally:
            summarize.urllib.request.urlopen = orig
        body = captured["body"]
        for forbidden in ("temperature", "top_p", "top_k", "budget_tokens"):
            self.assertNotIn(forbidden, body)     # Opus 4.8 계약: 보내면 400
        self.assertEqual(body["model"], summarize.MODEL)
        self.assertIn("max_tokens", body)
        self.assertEqual(out["kstartup:1"], "요약문")


class TestTechFiltering(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.sent = []
        self._orig = notify_email.send
        notify_email.send = lambda s, b, transport=None: self.sent.append((s, b))
        self._orig_sum = summarize.summarize
        summarize.summarize = lambda recs: {r.key: "요약" for r in recs}

    def tearDown(self):
        notify_email.send = self._orig
        summarize.summarize = self._orig_sum
        self.store.close()

    def test_email_tech_only_db_all(self):
        from collect import run
        tech = rec("kstartup", "1", title="AI 자동화 R&D", agency="중기부", deadline="2026-07-08")
        nontech = rec("bizinfo", "2", title="전통시장 환경개선 지원", agency="소진공", deadline="2026-07-08")
        out = run(self.store, [tech, nontech], date(2026, 6, 22))
        self.assertEqual(out["new"], 2)               # DB는 전건
        body = self.sent[-1][1]
        self.assertIn("AI 자동화 R&D", body)            # 메일엔 기술만
        self.assertNotIn("전통시장 환경개선", body)
        loaded = self.store.load()
        self.assertEqual(loaded["kstartup:1"].is_tech, "1")
        self.assertEqual(loaded["bizinfo:2"].is_tech, "0")  # 비기술도 저장


class TestServe(unittest.TestCase):
    def test_fetch_and_render(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            s = Store(path)
            r = rec("kstartup", "1", title="AI 한글 공고", agency="중기부", deadline="2026-07-08",
                    category="AI/생성형AI", is_tech="1", summary="요약 </script> 테스트")
            s.upsert(r, "2026-06-23T00:00:00")
            s.commit()
            s.close()
            notices = serve.fetch_notices(path)
            self.assertEqual(len(notices), 1)
            self.assertEqual(notices[0]["title"], "AI 한글 공고")
            html = serve.render_page(notices)
            self.assertIn("AI 한글 공고", html)        # 한글 임베드
            self.assertIn("<\\/script>", html)         # </ → <\/ 치환
            self.assertIn("기술 전체", html)            # 기본 tech 필터 마커
        finally:
            os.unlink(path)


class TestCollectIsolation(unittest.TestCase):
    def test_one_adapter_failure_isolated(self):  # 한 소스 실패가 전체 수집을 죽이지 않음
        import collect

        class Boom:
            def collect(self):
                raise RuntimeError("source down")

        class Good:
            def collect(self):
                return [RawNotice("kstartup", {"x": 1})]

        orig = collect.ADAPTERS
        collect.ADAPTERS = [Boom, Good]
        try:
            raws = collect.collect_all()
        finally:
            collect.ADAPTERS = orig
        self.assertEqual([r.source for r in raws], ["kstartup"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
