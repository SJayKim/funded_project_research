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
<title>정부과제 대시보드</title>
<style>
  body { font-family: -apple-system, "Malgun Gothic", sans-serif; margin: 1.5rem; color: #222; }
  h1 { font-size: 1.3rem; }
  .controls { margin: 1rem 0; display: flex; gap: .75rem; flex-wrap: wrap; align-items: center; }
  input, select { padding: .4rem .5rem; font-size: .95rem; }
  #count { color: #666; font-size: .9rem; }
  table { border-collapse: collapse; width: 100%; font-size: .9rem; }
  th, td { border: 1px solid #ddd; padding: .5rem; text-align: left; vertical-align: top; }
  th { background: #f5f5f5; }
  th.sortable { cursor: pointer; user-select: none; }
  td.cat { white-space: nowrap; color: #0a58ca; }
  tr:nth-child(even) { background: #fafafa; }
  a { color: #0a58ca; }
</style>
</head>
<body>
<h1>정부과제 대시보드</h1>
<div class="controls">
  <input id="q" type="search" placeholder="제목·요약·기관 검색">
  <select id="cat"></select>
  <span id="count"></span>
</div>
<table>
  <thead><tr>
    <th>카테고리</th><th>제목</th><th>요약</th><th>소관부처</th>
    <th class="sortable" id="th-deadline">마감일 ▲▼</th><th>링크</th>
  </tr></thead>
  <tbody id="rows"></tbody>
</table>
<script>
const DATA = __DATA__;
const cats = Array.from(new Set(DATA.map(d => d.category).filter(Boolean))).sort();
const sel = document.getElementById('cat');
sel.innerHTML = '<option value="__TECH__" selected>기술 전체</option>'
  + '<option value="__ALL__">전체</option>'
  + cats.map(c => '<option value="' + c + '">' + c + '</option>').join('');
let sortAsc = true;
function render() {
  const q = document.getElementById('q').value.trim().toLowerCase();
  const cat = sel.value;
  const rows = DATA.filter(d => {
    if (cat === '__TECH__') { if (d.is_tech !== '1') return false; }
    else if (cat !== '__ALL__') { if (d.category !== cat) return false; }
    if (q) {
      const hay = (d.title + ' ' + d.summary + ' ' + d.agency).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  rows.sort((a, b) => {
    const x = a.deadline || '', y = b.deadline || '';
    if (x === y) return 0;
    if (!x) return 1; if (!y) return -1;
    return sortAsc ? (x < y ? -1 : 1) : (x < y ? 1 : -1);
  });
  const tb = document.getElementById('rows');
  tb.textContent = '';
  for (const d of rows) {
    const tr = document.createElement('tr');
    const cells = [['cat', d.category], ['', d.title], ['', d.summary], ['', d.agency], ['', d.deadline]];
    for (const [cls, val] of cells) {
      const td = document.createElement('td');
      if (cls) td.className = cls;
      td.textContent = val || '';
      tr.appendChild(td);
    }
    const td = document.createElement('td');
    if (d.url) {
      const a = document.createElement('a');
      a.href = d.url; a.textContent = '바로가기'; a.target = '_blank'; a.rel = 'noopener';
      td.appendChild(a);
    }
    tr.appendChild(td);
    tb.appendChild(tr);
  }
  document.getElementById('count').textContent = rows.length + '건';
}
document.getElementById('q').addEventListener('input', render);
sel.addEventListener('change', render);
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
    if not os.path.exists(DB_PATH):
        print(f"DB 없음: {DB_PATH}\n"
              f"(CI DB 보려면: git show origin/data:gov_notices.db > gov_notices.db)")
        sys.exit(1)
    print(f"http://127.0.0.1:{PORT}  (Ctrl+C 종료)")
    http.server.HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
