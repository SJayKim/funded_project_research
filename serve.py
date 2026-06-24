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

DB_PATH = os.environ.get("GOV_DB", "gov_notices.db")
PORT = int(os.environ.get("PORT", "8000"))

PAGE = """<!DOCTYPE html>
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
  :focus-visible { outline: 2px solid #0a58ca; outline-offset: 1px; }
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
  <strong id="total"></strong>건을 <strong>5개 공식 기관</strong>에서 매일 수집 · 마지막 갱신 <strong id="updated"></strong>
  <div class="dist" id="dist"></div>
  <div class="caveat">기관 원문이 갱신·마감 변경될 수 있으니 신청 전 원문을 확인하세요.</div>
</div>
<div class="controls">
  <input id="q" type="search" placeholder="제목·요약·기관 검색" aria-label="검색">
  <select id="cat" aria-label="카테고리 필터"></select>
  <select id="view" aria-label="보기">
    <option value="all" selected>전체 보기</option>
    <option value="soon">마감임박(D-7)</option>
    <option value="new">신규</option>
  </select>
  <span id="count" aria-live="polite"></span>
</div>
<table>
  <thead><tr>
    <th scope="col">출처</th><th scope="col">공고</th><th scope="col">소관부처</th>
    <th scope="col" class="sortable" id="th-deadline">마감 ▲▼</th>
    <th scope="col">상태</th><th scope="col">원문</th>
  </tr></thead>
  <tbody id="rows"></tbody>
</table>
<script>
const DATA = __DATA__;
const SRC = { kstartup: 'K-Startup', bizinfo: '기업마당', msit: '과기정통부', nara: '나라장터', iris: 'IRIS' };
// 참조일: 최신 수집 시각(배너 갱신일 + D-day/신규 배지 기준)
const refDate = DATA.reduce((m, d) => (d.last_seen > m ? d.last_seen : m), '').slice(0, 10);
function diffDays(fromYmd, toYmd) {
  if (!fromYmd || !toYmd) return null;
  return Math.round((new Date(toYmd + 'T00:00:00') - new Date(fromYmd + 'T00:00:00')) / 86400000);
}
// 신뢰 배너 채우기: 정확 건수 + 출처별 분포 + 갱신일
document.getElementById('total').textContent = DATA.length.toLocaleString();
document.getElementById('updated').textContent = refDate;
const distCount = {};
for (const d of DATA) distCount[d.source] = (distCount[d.source] || 0) + 1;
document.getElementById('dist').textContent = Object.keys(SRC)
  .filter(s => distCount[s])
  .map(s => SRC[s] + ' ' + distCount[s].toLocaleString() + '건')
  .join(' · ');

const cats = Array.from(new Set(DATA.map(d => d.category).filter(Boolean))).sort();
const sel = document.getElementById('cat');
sel.innerHTML = '<option value="__TECH__" selected>기술 전체</option>'
  + '<option value="__ALL__">전체</option>'
  + cats.map(c => '<option value="' + c + '">' + c + '</option>').join('');
const viewSel = document.getElementById('view');
let sortAsc = false;
// 마감 D-day: refDate 기준 남은 일수. 음수=마감(과거), 빈값=null.
function ddayInfo(d) {
  const days = diffDays(refDate, (d.deadline || '').slice(0, 10));
  if (days === null) return { days: null };
  return { days };
}
function isNew(d) {
  const age = diffDays((d.first_seen || '').slice(0, 10), refDate);
  return age !== null && age >= 0 && age <= 2;
}
function render() {
  const q = document.getElementById('q').value.trim().toLowerCase();
  const cat = sel.value;
  const view = viewSel.value;
  const rows = DATA.filter(d => {
    if (cat === '__TECH__') { if (d.is_tech !== '1') return false; }
    else if (cat !== '__ALL__') { if (d.category !== cat) return false; }
    if (view === 'soon') { const dd = ddayInfo(d).days; if (dd === null || dd < 0 || dd > 7) return false; }
    else if (view === 'new') { if (!isNew(d)) return false; }
    if (q) {
      const hay = (d.title + ' ' + d.summary + ' ' + d.agency).toLowerCase();
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
    const tr = document.createElement('tr');

    // 출처 배지
    const tdSrc = document.createElement('td');
    tdSrc.dataset.label = '출처';
    const srcBadge = document.createElement('span');
    srcBadge.className = 'badge src';
    srcBadge.textContent = SRC[d.source] || d.source;
    tdSrc.appendChild(srcBadge);
    tr.appendChild(tdSrc);

    // 공고: 제목(굵게) + NEW 배지 + 요약(보조행)
    const tdTitle = document.createElement('td');
    tdTitle.className = 'notitle';
    const titleSpan = document.createElement('span');
    titleSpan.className = 'title';
    titleSpan.textContent = d.title || '';
    tdTitle.appendChild(titleSpan);
    if (isNew(d)) {
      const nb = document.createElement('span');
      nb.className = 'badge new'; nb.textContent = 'NEW';
      tdTitle.appendChild(nb);
    }
    if (d.summary) {
      const sm = document.createElement('div');
      sm.className = 'summary'; sm.textContent = d.summary;
      tdTitle.appendChild(sm);
    }
    tr.appendChild(tdTitle);

    // 소관부처
    const tdAgency = document.createElement('td');
    tdAgency.dataset.label = '소관부처';
    tdAgency.textContent = d.agency || '';
    tr.appendChild(tdAgency);

    // 마감: D-day 배지 + 날짜, 빈값은 대시(KRDS 빈셀 규칙)
    const tdDl = document.createElement('td');
    tdDl.dataset.label = '마감';
    const dd = ddayInfo(d).days;
    if (dd === null) {
      tdDl.textContent = '—';
    } else {
      const dday = document.createElement('span');
      dday.className = 'dday';
      if (dd < 0) { dday.classList.add('past'); dday.textContent = '마감'; }
      else if (dd === 0) { dday.classList.add('urgent'); dday.textContent = 'D-day'; }
      else if (dd <= 7) { dday.classList.add('urgent'); dday.textContent = 'D-' + dd; }
      else { dday.textContent = 'D-' + dd; }
      tdDl.appendChild(dday);
      tdDl.appendChild(document.createTextNode(' ' + d.deadline.slice(0, 10)));
    }
    tr.appendChild(tdDl);

    // 상태 칩: Y→접수중, N→마감, 그 외엔 과거 마감일만 마감(추측 안 함)
    const tdStatus = document.createElement('td');
    tdStatus.dataset.label = '상태';
    let chipText = '', chipCls = '';
    if (d.status === 'Y') { chipText = '접수중'; chipCls = 'open'; }
    else if (d.status === 'N') { chipText = '마감'; chipCls = 'closed'; }
    else if (dd !== null && dd < 0) { chipText = '마감'; chipCls = 'closed'; }
    if (chipText) {
      const chip = document.createElement('span');
      chip.className = 'chip ' + chipCls; chip.textContent = chipText;
      tdStatus.appendChild(chip);
    }
    tr.appendChild(tdStatus);

    // 원문 바로가기
    const tdUrl = document.createElement('td');
    tdUrl.dataset.label = '원문';
    if (d.url) {
      const a = document.createElement('a');
      a.href = d.url; a.textContent = '바로가기 ↗'; a.target = '_blank'; a.rel = 'noopener';
      tdUrl.appendChild(a);
    }
    tr.appendChild(tdUrl);

    tb.appendChild(tr);
  }
  document.getElementById('count').textContent = rows.length.toLocaleString() + '건';
}
document.getElementById('q').addEventListener('input', render);
sel.addEventListener('change', render);
viewSel.addEventListener('change', render);
document.getElementById('th-deadline').addEventListener('click', () => { sortAsc = !sortAsc; render(); });
render();
</script>
</body>
</html>
"""


def fetch_notices(db_path: str) -> list[dict]:
    """notices 전건을 last_seen 내림차순으로. NULL→"" 보정."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM notices ORDER BY last_seen DESC").fetchall()
    finally:
        conn.close()
    return [{k: (row[k] or "") for k in row.keys()} for row in rows]


def render_page(notices: list[dict]) -> str:
    # ensure_ascii=False로 한글 그대로, </ → <\/ 치환해 임베드 스크립트 조기종료 방지.
    data = json.dumps(notices, ensure_ascii=False).replace("</", "<\\/")
    return PAGE.replace("__DATA__", data)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        html = render_page(fetch_notices(DB_PATH)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)


def main() -> None:
    # --build <path>: HTTP 서버 대신 정적 HTML 1장을 파일로 써서 종료(Pages 배포용).
    if "--build" in sys.argv:
        out = sys.argv[sys.argv.index("--build") + 1]
        html = render_page(fetch_notices(DB_PATH))
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
