"""로컬 대시보드: DB를 표로 본다(검색·카테고리 필터·마감 정렬, 전부 클라이언트 JS).

127.0.0.1 전용. 서버는 요청당 DB 1회 조회 후 JSON 임베드 → 자체완결 HTML 반환.
DB 없으면 안내 출력 후 종료.
"""
from __future__ import annotations

import http.server
import json
import os
import sqlite3
import sys
from pathlib import Path
from dataclasses import fields

from .normalize import NoticeRecord, content_basis
from .store import NEW_COLUMNS

DB_PATH = os.environ.get("GOV_DB", "gov_notices.db")
PORT = int(os.environ.get("PORT", "8000"))

PAGE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>정부과제 대시보드</title>
<style>
  body { font-family: -apple-system, "Malgun Gothic", sans-serif; margin: 1.5rem; color: #222; }
  h1 { font-size: 1.3rem; margin-bottom: .25rem; }
  /* 신뢰 배너: 출처·갱신일·분포·한계 고지 */
  .banner { background: #f0f5fb; border: 1px solid #cfe0f2; border-radius: .4rem;
    padding: .6rem .8rem; font-size: .9rem; line-height: 1.5; }
  .banner .dist { color: #444; margin-top: .2rem; }
  .banner .caveat { color: #7a5a00; margin-top: .3rem; font-size: .85rem; }
  .controls { margin: 1rem 0; display: flex; gap: .75rem; flex-wrap: wrap; align-items: center; }
  input, select { padding: .4rem .5rem; font-size: .95rem; }
  #count { color: #666; font-size: .9rem; }
  .controls label { font-size: .9rem; color: #444; display: inline-flex; align-items: center; gap: .3rem; }
  .controls input[type=checkbox] { padding: 0; }
  table { border-collapse: collapse; width: 100%; font-size: .9rem; }
  th, td { border: 1px solid #ddd; padding: .5rem; text-align: left; vertical-align: top; }
  th { background: #f5f5f5; }
  th.sortable { cursor: pointer; user-select: none; }
  tr:nth-child(even) { background: #fafafa; }
  a { color: #0a58ca; }
  .title { font-weight: 600; }
  .summary { color: #666; font-size: .82rem; margin-top: .2rem; }
  /* 배지/칩: 색은 장식, 라벨 텍스트가 의미를 전달(color-only 금지, KRDS style_02) */
  .badge { display: inline-block; padding: .1rem .4rem; border-radius: .25rem;
    font-size: .75rem; font-weight: 600; white-space: nowrap; }
  .src { background: #e8eef7; color: #1b4d8a; }
  .new { background: #0a7d33; color: #fff; margin-left: .4rem; }
  .dday { font-weight: 700; }
  .dday.soon { color: #b00020; }
  .dday.urgent { color: #fff; background: #b00020; padding: .05rem .35rem; border-radius: .25rem; }
  .dday.past { color: #888; }
  .chip { display: inline-block; padding: .1rem .4rem; border-radius: 999px;
    font-size: .75rem; font-weight: 600; white-space: nowrap; }
  .chip.open { background: #e3f4e8; color: #0a7d33; }
  .chip.closed { background: #eee; color: #666; }
  .chip.na { background: #f3f3f3; color: #999; }
  .spec { background: #efe8f7; color: #5a3a8a; margin-left: .4rem; }
  .meta { color: #555; font-size: .8rem; margin-top: .2rem; }
  /* 추출 발췌: 원문 인용(단정 금지). 인용임을 좌측 보더로 시각화 */
  .excerpt { color: #444; font-size: .8rem; margin-top: .15rem;
    border-left: 2px solid #cfe0f2; padding-left: .4rem; }
  .excerpt b { color: #1b4d8a; font-weight: 600; }
  mark { background: #fff3a3; color: inherit; padding: 0 .1rem; }
  #empty { color: #666; padding: 1rem 0; }
  :focus-visible { outline: 2px solid #0a58ca; outline-offset: 1px; }
  /* 뷰 토글: 데스크톱에서도 카드 레이아웃 선택(모바일은 항상 카드) */
  table.cards, table.cards thead, table.cards tbody, table.cards th, table.cards td, table.cards tr { display: block; }
  table.cards thead { position: absolute; left: -9999px; }
  table.cards tbody { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: .6rem; }
  table.cards tr { border: 1px solid #ddd; border-radius: .4rem; padding: .4rem .5rem; }
  table.cards tr:nth-child(even) { background: #fff; }
  table.cards td { border: none; padding: .2rem 0; }
  table.cards td[data-label]::before { content: attr(data-label) ": "; font-weight: 600; color: #888; }
  table.cards td.notitle::before { content: ""; }
  /* 모바일: 테이블 → 카드 reflow(KRDS 모바일 표 수직 재배치) */
  @media (max-width: 700px) {
    body { margin: .8rem; }
    table, thead, tbody, th, td, tr { display: block; }
    thead { position: absolute; left: -9999px; }
    tr { border: 1px solid #ddd; border-radius: .4rem; margin-bottom: .6rem; padding: .4rem .5rem; }
    tr:nth-child(even) { background: #fff; }
    td { border: none; padding: .2rem 0; }
    td[data-label]::before { content: attr(data-label) ": "; font-weight: 600; color: #888; }
    td.notitle::before { content: ""; }
  }
</style>
</head>
<body>
<h1>정부과제 대시보드</h1>
<div class="banner" role="note">
  누적 <strong id="total"></strong>건 · 확인된 마감 전 <strong id="openTotal"></strong>건 · 한국 기준일 <strong id="updated"></strong>
  <div class="dist" id="dist"></div>
  <div class="caveat">목록에는 용역 입찰·교육·행사도 포함됩니다. 미확인 또는 확인 후 48시간이 지난 공고는 신청 가능 여부를 다시 확인해야 합니다. 신청 전 원문과 첨부를 확인하세요.</div>
  <details><summary>출처별 수집 상태</summary><div id="sourceHealth"></div></details>
</div>
<div class="controls">
  <input id="q" type="search" placeholder="제목·요약·기관 검색" aria-label="검색">
  <select id="cat" aria-label="카테고리 필터"></select>
  <select id="view" aria-label="보기">
    <option value="all" selected>전체 보기</option>
    <option value="soon">마감임박(D-7)</option>
    <option value="new">새로 수집</option>
  </select>
  <select id="layout" aria-label="레이아웃">
    <option value="table" selected>테이블</option>
    <option value="cards">카드</option>
  </select>
  <label><input id="hideClosed" type="checkbox" checked> 마감 지난 공고 숨기기</label>
  <label><input id="confirmedOnly" type="checkbox"> 확인된 마감 전만</label>
  <span id="count" aria-live="polite"></span>
</div>
<table>
  <thead><tr>
    <th scope="col">출처</th><th scope="col">공고</th><th scope="col">기관</th>
    <th scope="col" class="sortable" id="th-deadline">마감 ▲▼</th>
    <th scope="col">상태</th><th scope="col">원문</th>
  </tr></thead>
  <tbody id="rows"></tbody>
</table>
<div id="empty" role="status" hidden>검색 결과가 없습니다. 검색어나 필터를 바꿔보세요.</div>
<script>
const DATA = __DATA__;
const HEALTH = __HEALTH__;
__STATUS_JS__
const SRC = { kstartup: 'K-Startup', bizinfo: '기업마당', msit: '과기정통부', nara: '나라장터', iris: 'IRIS' };
function diffDays(fromYmd, toYmd) {
  const from = instant(fromYmd), to = instant(toYmd);
  return from === null || to === null ? null : Math.round((to - from) / 86400000);
}
// 검색 하이라이트: q(소문자) 매칭 부분만 <mark>로, 나머지는 textContent(XSS 안전)
function hl(parent, text, q) {
  text = text || '';
  if (!q) { parent.appendChild(document.createTextNode(text)); return; }
  const lower = text.toLowerCase();
  let i = 0, idx;
  while ((idx = lower.indexOf(q, i)) !== -1) {
    if (idx > i) parent.appendChild(document.createTextNode(text.slice(i, idx)));
    const m = document.createElement('mark');
    m.textContent = text.slice(idx, idx + q.length);
    parent.appendChild(m);
    i = idx + q.length;
  }
  if (i < text.length) parent.appendChild(document.createTextNode(text.slice(i)));
}
// 신뢰 배너 채우기: 정확 건수 + 출처별 분포 + 갱신일
document.getElementById('total').textContent = DATA.length.toLocaleString();
const distCount = {};
for (const d of DATA) distCount[d.source] = (distCount[d.source] || 0) + 1;
document.getElementById('dist').textContent = Object.keys(SRC)
  .filter(s => distCount[s])
  .map(s => SRC[s] + ' ' + distCount[s].toLocaleString() + '건')
  .join(' · ');
const healthLabels = {success: '수집 완료', empty: '정상 응답 0건', partial: '부분 수집', failed: '수집 실패'};
function displayTime(value, legacy = false) {
  if (!value) return '기록 없음';
  const date = new Date(legacy && !/[Z+-]\d*:?\d*$/.test(value.slice(10)) ? value + 'Z' : value);
  return Number.isNaN(date.getTime()) ? '시각 미확인' : date.toLocaleString('ko-KR', {timeZone: 'Asia/Seoul'});
}
function renderHealth(now) {
  const el = document.getElementById('sourceHealth'); el.textContent = '';
  for (const [source, name] of Object.entries(SRC)) {
    const h = HEALTH.find(x => x.source === source);
    const p = document.createElement('p');
    if (h) {
      const checked = instant(h.completed_at);
      const old = checked === null || now.getTime() - checked > 48 * 3600000;
      p.textContent = name + ': ' + (healthLabels[h.state] || '상태 미확인') + (old ? ' · 갱신 지연' : '')
        + ' · 최근 시도 ' + displayTime(h.completed_at) + ' · ' + h.count + '건'
        + ' · 마지막 완전 수집 ' + displayTime(h.last_success);
    } else {
      const seen = DATA.filter(d => d.source === source).reduce((m, d) => d.last_seen > m ? d.last_seen : m, '');
      p.textContent = name + ': 수집 상태 미확인 · 누적 ' + (distCount[source] || 0) + '건'
        + ' · 과거 저장 기록 ' + displayTime(seen, true);
    }
    el.appendChild(p);
  }
}

const cats = Array.from(new Set(DATA.map(d => d.category).filter(Boolean))).sort();
const sel = document.getElementById('cat');
sel.innerHTML = '<option value="__TECH__" selected>기술 전체</option>'
  + '<option value="__ALL__">전체</option>'
  + cats.map(c => '<option value="' + c + '">' + c + '</option>').join('');
const viewSel = document.getElementById('view');
let sortAsc = true;
let refreshTimer;
// 마감 D-day는 현재 한국 날짜 기준. 수집 시각과 분리한다.
function ddayInfo(d) {
  const days = instant(d.deadline) === null ? null : diffDays(kstDay(), (d.deadline || '').slice(0, 10));
  if (days === null) return { days: null };
  return { days };
}
function isNew(d) {
  const seen = d.first_seen || '';
  const parsed = new Date(seen && !/[Z+-]\d*:?\d*$/.test(seen.slice(10)) ? seen + 'Z' : seen);
  const age = Number.isNaN(parsed.getTime()) ? null : diffDays(kstDay(parsed), kstDay());
  return age !== null && age >= 0 && age <= 2;
}
function render() {
  const now = new Date();
  let nextRefresh = instant(kstDay(now), true);
  for (const d of DATA) {
    for (const boundary of [instant(d.deadline, true), instant(d.starts_at),
      ...[d.source_checked_at, d.verified_at].map(v => { const t = instant(v); return t === null ? null : t + 48 * 3600000; })]) {
      if (boundary !== null && boundary >= now.getTime()) nextRefresh = Math.min(nextRefresh, boundary + 50);
    }
  }
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(render, Math.max(50, Math.min(60000, nextRefresh - now.getTime())));
  const states = new Map(DATA.map(d => [d.key || d, noticeState(d, now)]));
  document.getElementById('openTotal').textContent = [...states.values()].filter(s => s === 'open').length.toLocaleString();
  document.getElementById('updated').textContent = kstDay(now);
  renderHealth(now);
  const q = document.getElementById('q').value.trim().toLowerCase();
  const cat = sel.value;
  const view = viewSel.value;
  const hideClosed = document.getElementById('hideClosed').checked;
  const confirmedOnly = document.getElementById('confirmedOnly').checked;
  const rows = DATA.filter(d => {
    const state = states.get(d.key || d);
    if (cat === '__TECH__') { if (d.is_tech !== '1') return false; }
    else if (cat !== '__ALL__') { if (d.category !== cat) return false; }
    if (view === 'soon') { const dd = ddayInfo(d).days; if (state !== 'open' || dd === null || dd < 0 || dd > 7) return false; }
    else if (view === 'new') { if (!isNew(d)) return false; }
    // 마감 숨김(기본 ON): 마감일 있고 지난 공고만 제외. 마감일 없는 건(days===null)은 통과.
    if (hideClosed && state === 'closed') return false;
    if (confirmedOnly && state !== 'open') return false;
    if (q) {
      const hay = (d.title + ' ' + (d.summary_current ? d.summary : '') + ' ' + d.agency + ' ' + d.target + ' ' + d.specialized_agency).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  // 마감임박 뷰는 임박순(오름차순), 그 외는 정렬 토글(기본 먼 마감 먼저)
  const asc = view === 'soon' ? true : sortAsc;
  rows.sort((a, b) => {
    const x = a.deadline || '', y = b.deadline || '';
    if (x === y) return 0;
    if (!x) return 1; if (!y) return -1;
    return asc ? (x < y ? -1 : 1) : (x < y ? 1 : -1);
  });
  const tb = document.getElementById('rows');
  tb.textContent = '';
  for (const d of rows) {
    const state = states.get(d.key || d);
    const tr = document.createElement('tr');

    // 출처 배지
    const tdSrc = document.createElement('td');
    tdSrc.dataset.label = '출처';
    const srcBadge = document.createElement('span');
    srcBadge.className = 'badge src';
    srcBadge.textContent = d.source === 'nara' ? '나라장터 · 용역 입찰' : SRC[d.source] || d.source;
    tdSrc.appendChild(srcBadge);
    tr.appendChild(tdSrc);

    // 공고: 제목(굵게) + NEW 배지 + 요약(보조행)
    const tdTitle = document.createElement('td');
    tdTitle.className = 'notitle';
    const titleSpan = document.createElement('span');
    titleSpan.className = 'title';
    hl(titleSpan, d.title, q);
    tdTitle.appendChild(titleSpan);
    if (isNew(d)) {
      const nb = document.createElement('span');
      nb.className = 'badge new'; nb.textContent = '새로 수집';
      tdTitle.appendChild(nb);
    }
    // 전문/전담기관 배지(보유 출처만)
    if (d.specialized_agency) {
      const sb = document.createElement('span');
      sb.className = 'badge spec'; sb.textContent = d.specialized_agency;
      tdTitle.appendChild(sb);
    }
    // 신청자격(target, kstartup만 보유) 메타라인
    if (d.target) {
      const tg = document.createElement('div');
      tg.className = 'meta';
      tg.appendChild(document.createTextNode('신청자격: '));
      hl(tg, d.target, q);
      tdTitle.appendChild(tg);
    }
    if (d.summary && d.summary_current) {
      const sm = document.createElement('div');
      sm.className = 'summary';
      hl(sm, d.summary, q);
      tdTitle.appendChild(sm);
    }
    // Approach A 추출 4필드: 원문 발췌만 표시(단정 금지). status=ok일 때만.
    if (d.extraction_status === 'ok' && d.extraction_current) {
      const EX = [['funding_amount', '지원금액'], ['eligibility', '신청자격'],
                  ['required_docs', '제출서류'], ['key_dates', '주요일정']];
      for (const [f, label] of EX) {
        if (!d[f]) continue;
        const ex = document.createElement('div');
        ex.className = 'excerpt';
        const b = document.createElement('b');
        b.textContent = label + ' 발췌: ';
        ex.appendChild(b);
        hl(ex, d[f], q);
        tdTitle.appendChild(ex);
      }
    }
    tr.appendChild(tdTitle);

    // 소관부처
    const tdAgency = document.createElement('td');
    tdAgency.dataset.label = '기관';
    hl(tdAgency, d.agency, q);
    tr.appendChild(tdAgency);

    // 마감: D-day 배지 + 날짜, 빈값은 대시(KRDS 빈셀 규칙)
    const tdDl = document.createElement('td');
    tdDl.dataset.label = '마감';
    const dd = ddayInfo(d).days;
    if (dd === null) {
      tdDl.textContent = '마감 미확인';
    } else {
      const dday = document.createElement('span');
      dday.className = 'dday';
      if (state === 'closed') { dday.classList.add('past'); dday.textContent = '마감'; }
      else if (state !== 'open') { dday.textContent = '저장된 마감'; }
      else if (dd === 0) { dday.classList.add('urgent'); dday.textContent = 'D-day'; }
      else if (dd <= 7) { dday.classList.add('urgent'); dday.textContent = 'D-' + dd; }
      else { dday.textContent = 'D-' + dd; }
      tdDl.appendChild(dday);
      tdDl.appendChild(document.createTextNode(' ' + d.deadline + (d.deadline.length > 10 ? ' KST' : '')));
    }
    tr.appendChild(tdDl);

    // 상태 칩: 출처가 준 접수상태만 표시. Y→접수중, N→마감, 안 주면 미제공 명시(추측 안 함)
    const tdStatus = document.createElement('td');
    tdStatus.dataset.label = '상태';
    let chipText, chipCls;
    if (state === 'open') { chipText = '확인된 마감 전'; chipCls = 'open'; }
    else if (state === 'closed') { chipText = '마감'; chipCls = 'closed'; }
    else { chipText = {scheduled: '접수 전', conflict: '정보 충돌', unknown: '확인 필요'}[state]; chipCls = 'na'; }
    const chip = document.createElement('span');
    chip.className = 'chip ' + chipCls; chip.textContent = chipText;
    if (chipCls === 'na') chip.title = '원문에서 접수기간을 확인하세요. 미확인·오래된 정보는 진행중으로 집계하지 않습니다.';
    tdStatus.appendChild(chip);
    const checked = document.createElement('div'); checked.className = 'meta';
    checked.textContent = d.verified_at ? '원문 확인 ' + displayTime(d.verified_at)
      : d.source_checked_at ? '목록 확인 ' + displayTime(d.source_checked_at) : '확인 기록 없음';
    tdStatus.appendChild(checked);
    tr.appendChild(tdStatus);

    // 원문 바로가기
    const tdUrl = document.createElement('td');
    tdUrl.dataset.label = '원문';
    if (d.url) {
      const a = document.createElement('a');
      a.href = d.url; a.textContent = '바로가기 ↗'; a.target = '_blank'; a.rel = 'noopener';
      tdUrl.appendChild(a);
    } else { tdUrl.textContent = '원문 링크 없음'; }
    tr.appendChild(tdUrl);

    tb.appendChild(tr);
  }
  document.getElementById('count').textContent = rows.length.toLocaleString() + '건';
  document.getElementById('empty').hidden = rows.length !== 0;
}
document.getElementById('q').addEventListener('input', render);
sel.addEventListener('change', render);
viewSel.addEventListener('change', render);
document.getElementById('hideClosed').addEventListener('change', render);
document.getElementById('confirmedOnly').addEventListener('change', render);
// 레이아웃 토글: 재렌더 없이 table에 cards 클래스만 토글(모바일은 CSS가 항상 카드)
const layoutSel = document.getElementById('layout');
const tableEl = document.querySelector('table');
layoutSel.addEventListener('change', () => {
  tableEl.classList.toggle('cards', layoutSel.value === 'cards');
});
document.getElementById('th-deadline').addEventListener('click', () => { sortAsc = !sortAsc; render(); });
render();
document.addEventListener('visibilitychange', () => { if (!document.hidden) render(); });
</script>
</body>
</html>
"""
PAGE = PAGE.replace("__STATUS_JS__", Path(__file__).with_name("status.js").read_text(encoding="utf-8"))


def fetch_notices(db_path: str) -> list[dict]:
    """notices 전건을 last_seen 내림차순으로. NULL→"" 보정."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM notices ORDER BY last_seen DESC").fetchall()
    finally:
        conn.close()
    return [{k: (row[k] or "") for k in row.keys()} for row in rows]


def fetch_health(db_path: str) -> list[dict]:
    conn = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='source_health'").fetchone():
            return []
        return [dict(r) for r in conn.execute("SELECT * FROM source_health ORDER BY source")]
    finally:
        conn.close()


def render_page(notices: list[dict], health: list[dict] | None = None) -> str:
    notices = [dict(d) for d in notices]
    for d in notices:
        rec = NoticeRecord(**{f.name: d.get(f.name, "") for f in fields(NoticeRecord)})
        basis = content_basis(rec)
        d["summary_current"] = bool(rec.summary_basis and rec.summary_basis == basis)
        d["extraction_current"] = bool(rec.extraction_basis and rec.extraction_basis == basis)
        # 기본값뿐인 이행 필드와 화면에서 쓰지 않는 해시는 HTML 전송에서 제외한다.
        for key in NEW_COLUMNS:
            if not d.get(key) or key in ("summary_basis", "extraction_basis"):
                d.pop(key, None)
    # ensure_ascii=False로 한글 그대로, </ → <\/ 치환해 임베드 스크립트 조기종료 방지.
    data = json.dumps(notices, ensure_ascii=False).replace("</", "<\\/")
    health_json = json.dumps(health or [], ensure_ascii=False).replace("</", "<\\/")
    return PAGE.replace("__HEALTH__", health_json).replace("__DATA__", data)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        html = render_page(fetch_notices(DB_PATH), fetch_health(DB_PATH)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)


def main() -> None:
    # --build <path>: HTTP 서버 대신 정적 HTML 1장을 파일로 써서 종료(Pages 배포용).
    if "--build" in sys.argv:
        out = sys.argv[sys.argv.index("--build") + 1]
        html = render_page(fetch_notices(DB_PATH), fetch_health(DB_PATH))
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"wrote {out} ({len(html)} bytes)")
        return
    if not os.path.exists(DB_PATH):
        print(f"DB 없음: {DB_PATH}\n"
              f"(CI DB 보려면: git show origin/data:gov_notices.db > gov_notices.db)")
        sys.exit(1)
    print(f"http://127.0.0.1:{PORT}  (Ctrl+C 종료)")
    http.server.HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
