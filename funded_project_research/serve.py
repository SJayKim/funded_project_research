"""정부과제 검색 대시보드. 검색·필터·상세보기는 클라이언트 JS로 동작한다.

127.0.0.1 전용. 서버는 공고와 수집 상태를 읽어 JSON 임베드 HTML과 로컬 폰트를 제공한다.
DB 없으면 안내 출력 후 종료.
"""
from __future__ import annotations

from dataclasses import fields
import http.server
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys

from .normalize import NoticeRecord, content_basis
from .store import NEW_COLUMNS

DB_PATH = os.environ.get("GOV_DB", "gov_notices.db")
PORT = int(os.environ.get("PORT", "8000"))
ASSETS = Path(__file__).with_name("assets")

PAGE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="정부 지원사업·연구개발·입찰 공고를 검색하고 마감과 공식 원문을 확인하세요.">
<title>정부과제 찾기</title>
<style>
:root{--bg:#f6f8fb;--surface:#fff;--ink:#182230;--muted:#526175;--line:#dce3ec;--accent:#1d4ed8;--soft:#edf3ff}

*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:'Pretendard Variable',Pretendard,sans-serif;font-size:14px;line-height:1.5}
button,input,select{font:inherit}
button,summary{cursor:pointer}
button{color:inherit}
button,a,input,select{touch-action:manipulation}
button:focus-visible,a:focus-visible,input:focus-visible,summary:focus-visible,select:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
[hidden]{display:none!important}
a{color:var(--accent)}

.topbar{height:56px;background:white;border-bottom:1px solid var(--line)}
.top-inner{max-width:1264px;padding:0 32px;margin:auto;height:100%;display:flex;align-items:center;justify-content:space-between;gap:16px}
.wordmark{font-weight:750;font-size:18px;letter-spacing:-.7px}
.wordmark span{font-weight:450;color:var(--muted);font-size:13px;margin-left:16px;letter-spacing:0}

main{max-width:1264px;padding:24px 32px 40px;margin:auto}
h1{font-size:30px;letter-spacing:-1px;line-height:1.25;margin:0 0 8px;font-weight:700}
.intro p{color:var(--muted);margin:0;font-size:15px}
.intro{display:flex;justify-content:space-between;align-items:center;gap:24px;margin-bottom:16px}
.quiet{border:1px solid var(--line);border-radius:8px;background:white;min-height:44px;padding:9px 14px;white-space:nowrap}
.search{position:relative;display:flex;gap:8px}
.search input{height:48px;border:1px solid #b8c4d5;border-radius:8px;background:white;width:100%;padding:0 18px 0 46px;outline-offset:2px;font-size:16px;box-shadow:0 2px 5px #18223005}
.search svg{position:absolute;top:14px;left:16px;width:20px;height:20px;stroke:var(--muted)}
.tabs{display:flex;gap:28px;border-bottom:1px solid var(--line);margin-top:12px}
.tabs button{border:0;border-bottom:2px solid transparent;background:transparent;min-height:44px;padding:10px 0;color:var(--muted);font-weight:550}
.tabs button[aria-pressed=true]{color:var(--accent);border-bottom-color:var(--accent);font-weight:650}

.tools{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:12px 0}
.views{display:flex;gap:4px}
.views button{border:0;border-radius:6px;background:transparent;padding:9px 12px;min-height:40px;color:var(--muted)}
.views button[aria-pressed=true]{background:var(--soft);color:var(--accent);font-weight:600}
.tools-right{display:flex;gap:8px;align-items:center}
.tools-right select{background:transparent;border:0;padding:10px 26px 10px 10px;color:var(--muted);min-height:44px}
.tools-right .quiet{padding:8px 12px}
.filter-box,.notice{margin-bottom:16px;padding:16px 20px;border:1px solid var(--line);border-radius:8px;background:white;color:var(--muted)}
.filter-box label{display:inline-flex;align-items:center;gap:8px;margin-right:20px;min-height:44px}
.filter-box select{padding:8px;border:1px solid #b8c4d5;border-radius:6px}
.filter-box input{width:18px;height:18px}
.results-top{display:flex;gap:12px;align-items:center;justify-content:space-between;margin:1px 0 12px}
.count{font-size:14px}
.count strong{font-weight:650}
.results-top small{color:var(--muted);font-size:12px}

.list{background:white;border:1px solid var(--line);border-radius:12px;overflow:hidden}
table{width:100%;border-collapse:collapse;table-layout:fixed}
.col-title{width:auto}
.col-status{width:128px}
.col-deadline{width:168px}
.col-link{width:112px}
th{padding:11px 22px;background:#fafbfd;color:var(--muted);text-align:left;font-size:12px;font-weight:500;border-bottom:1px solid var(--line)}
td{padding:18px 22px;border-bottom:1px solid #e9edf3;vertical-align:middle}
.record:hover td{background:#fafcff}
.record:last-of-type td{border-bottom:0}
.title-button{display:block;text-align:left;font-size:16px;font-weight:600;letter-spacing:-.25px;background:none;border:0;padding:0;min-height:26px;line-height:1.55}
.title-button:hover{color:var(--accent)}
.meta{font-size:13px;color:var(--muted);margin-top:6px;display:flex;flex-wrap:wrap;gap:6px}
.source{color:#435572}
.dot{color:#b1bccc}
.badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:550;padding:4px 8px;border-radius:4px;white-space:nowrap}
.open{color:#146145;background:#edf7f1}
.unknown,.closed{color:#526175;background:#f0f3f7}
.deadline strong{font-size:16px;font-weight:650;display:block;font-variant-numeric:tabular-nums}
.deadline small{color:var(--muted);display:block;margin-top:2px;font-size:12px;font-variant-numeric:tabular-nums}
.deadline.urgent strong{color:#b42318}
.link{display:inline-flex;align-items:center;gap:8px;text-decoration:none;border:1px solid #cbd6e8;color:var(--accent);border-radius:7px;min-height:44px;min-width:72px;padding:9px 12px;white-space:nowrap;background:white;font-size:13px}
.link:hover{background:var(--soft)}
.new{font-size:11px;color:var(--accent);font-weight:550;margin-left:5px}
.detail td{background:#fafbfd;padding:18px 24px;color:var(--muted)}
.detail p{margin:4px 0}
.detail strong{color:var(--ink)}
.detail .quiet{margin-top:10px}
.empty{text-align:center;padding:52px 20px}
.empty h2{font-size:18px;margin:0 0 8px}
.empty p{color:var(--muted)}
.empty button{background:var(--accent);color:white;border:0;border-radius:8px;padding:12px 20px;min-height:44px}
.footer-note{display:flex;justify-content:space-between;gap:24px;margin-top:18px;color:var(--muted);font-size:12px}
.footer-note p{margin:0}

@media(max-width:740px){.topbar{height:52px}
.top-inner{padding:0 16px}
.wordmark span{display:none}
main{padding:22px 16px 32px}
.intro{margin-bottom:16px;align-items:flex-start;gap:8px}
h1{font-size:25px}
.intro p{font-size:13px;max-width:none}
.intro>.quiet{display:none}
.search input{height:48px;font-size:14px}
.search svg{top:14px}
.tabs{gap:24px;margin-top:10px}
.tabs button{font-size:13px;min-height:44px}
.tools{padding:12px 0;gap:8px;align-items:flex-start}
.views{gap:2px}
.views button{padding:8px;font-size:12px;min-height:40px}
.tools-right{gap:2px}
.tools-right select{display:none}
.tools-right .quiet{font-size:12px;padding:8px;min-height:40px}
.results-top{margin:0 0 10px}
.results-top small{display:none}
.filter-box label{display:flex;margin:0;justify-content:space-between}
.list{border:0;border-radius:0;background:transparent;overflow:visible}
table,tbody{display:block}
colgroup{display:none}
thead{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
.record{display:grid;grid-template-columns:1fr auto;gap:12px 8px;background:white;border:1px solid var(--line);border-radius:10px;padding:18px 16px;margin-bottom:10px}
td{padding:0;border:0}
.title-cell{grid-column:1/-1}
.title-button{font-size:16px}
.meta{font-size:12px;gap:5px;margin-top:6px}
.status-cell{grid-column:1;grid-row:2;align-self:center}
.deadline{grid-column:1;grid-row:3;align-self:center}
.deadline strong{display:inline;font-size:15px}
.deadline small{display:inline;margin-left:7px}
.link-cell{grid-column:2;grid-row:2/4;align-self:end}
.record:hover td{background:transparent}
.detail{display:block;margin:-10px 0 10px;padding:16px;border:1px solid var(--line);border-top:0;border-radius:0 0 10px 10px;background:#fafbfd}
.detail td{display:block;padding:0}
.footer-note{display:block;font-size:11px}
.footer-note p+p{margin-top:8px}
}

@media(prefers-reduced-motion:no-preference){button,a{transition:background-color .12s,color .12s}
}
@font-face { font-family: 'Pretendard Variable'; font-style: normal; font-weight: 45 920; font-display: swap; src: url('assets/pretendard/PretendardVariable.woff2') format('woff2'); }
.top-inner .updated { color: var(--muted); font-size: 12px; text-align: right; }
.search input { min-width: 0; }
.skip-link { position: absolute; top: -100px; left: 16px; z-index: 10; background: white; padding: 12px; }
.skip-link:focus { top: 8px; }
.title-button { overflow-wrap: anywhere; min-height: 44px; width: 100%; }
.title-button[aria-expanded="false"] .title-text { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.title-button::after { content: '상세 보기'; display: inline-block; margin-left: 8px; color: var(--muted); font-size: 11px; font-weight: 400; }
.title-button[aria-expanded="true"]::after { content: '상세 닫기'; }
.meta, .detail td, .match, .filter-box, .notice { overflow-wrap: anywhere; }
.meta { margin-top: 3px; }
.detail h2 { font-size: 16px; margin: 0 0 12px; color: var(--ink); }
.detail dl { margin: 0; display: grid; grid-template-columns: 110px 1fr; gap: 12px 20px; }
.detail dt { color: var(--ink); font-weight: 600; }
.detail dd { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.detail .quiet { margin-top: 16px; }
.match { margin-top: 6px; color: var(--muted); font-size: 13px; }
mark { background: #fff0b3; color: var(--ink); padding: 0 1px; }
.active-filters { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 14px; }
.active-filters button { border: 1px solid var(--line); border-radius: 6px; background: white; padding: 8px 12px; min-height: 44px; }
.active-filters .reset { color: var(--accent); border-color: transparent; background: transparent; }
.text-button { background: none; border: none; color: var(--accent); padding: 8px 0; min-height: 44px; font-size: 12px; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 16px; margin-top: 20px; }
.pagination button { min-width: 64px; }
.pagination button:disabled { opacity: .45; cursor: default; }
.page-summary { color: var(--muted); font-variant-numeric: tabular-nums; }
.filter-box { display: flex; flex-wrap: wrap; gap: 12px 24px; }
.filter-box label { margin: 0; }
.filter-box select { max-width: 100%; }
.notice h2 { font-size: 16px; color: var(--ink); margin: 0 0 8px; }
.notice p { margin: 6px 0; }
.notice ul { margin: 8px 0; padding-left: 20px; }
.notice li { margin: 6px 0; }
.no-url { font-size: 12px; color: var(--muted); }
.load-error { padding: 20px; background: #fff4ed; color: #9c2a10; border-radius: 8px; margin-bottom: 16px; }
.tools-right select { max-width: 160px; }
.views button { min-height: 44px; }
.list.cards { background: transparent; border: 0; overflow: visible; }
.cards table, .cards tbody { display: block; }
.cards colgroup { display: none; }
.cards thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
.cards .record { display: grid; grid-template-columns: 1fr 144px 100px; align-items: center; gap: 16px; border: 1px solid var(--line); border-radius: 10px; padding: 20px; margin-bottom: 12px; background: white; }
.cards td { border: 0; padding: 0; }
.cards .title-cell { grid-column: 1; grid-row: 1 / 3; }
.cards .status-cell { grid-column: 2; grid-row: 1; }
.cards .deadline { grid-column: 2; grid-row: 2; }
.cards .link-cell { grid-column: 3; grid-row: 1 / 3; }
.cards .detail { display: block; background: #fafbfd; padding: 20px; margin: -12px 0 12px; border: 1px solid var(--line); border-radius: 0 0 10px 10px; }
.cards .detail td { display: block; }
@media (max-width: 900px) {
  .col-status { width: 100px; } .col-deadline { width: 140px; } .col-link { width: 104px; }
  th, td { padding-left: 16px; padding-right: 16px; }
}
@media (max-width: 740px) {
  .intro > .quiet { display: inline-flex; align-items: center; padding: 8px; font-size: 12px; }
  .intro { flex-wrap: wrap; }
  .intro p { max-width: none; }
  .tools-right { flex: 1; justify-content: flex-end; }
  .tools-right select { display: block; font-size: 12px; padding: 6px; min-height: 44px; }
  .tools-right .quiet { min-height: 44px; }
  .filter-box { display: grid; grid-template-columns: 1fr; padding: 12px; }
  .filter-box select { max-width: 200px; }
  .results-top { align-items: center; flex-wrap: wrap; gap: 0 8px; }
  .top-inner .updated { font-size: 11px; }
  .detail dl { grid-template-columns: 1fr; gap: 6px; }
  .detail dd { margin-bottom: 12px; }
  .cards .record, .record { grid-template-columns: minmax(0, 1fr) auto; padding: 16px; }
  .cards .title-cell, .title-cell { grid-column: 1 / -1; grid-row: 1; }
  .cards .status-cell, .status-cell { grid-column: 1; grid-row: 2; }
  .cards .deadline, .deadline { grid-column: 1; grid-row: 3; }
  .cards .link-cell, .link-cell { grid-column: 2; grid-row: 2 / 4; }
  .deadline small { display: block; margin-left: 0; }
  .cards .record:hover td { background: transparent; }
  .title-button { font-size: 16px; }
}
</style>
</head>
<body>
<a class="skip-link" href="#results">공고 목록으로 건너뛰기</a>
<header class="topbar"><div class="top-inner"><div class="wordmark">정부과제<span>공고 탐색</span></div><div class="updated">공식 출처의 공고를 한곳에서</div></div></header>
<main>
<section class="intro"><div><h1>정부과제 찾기</h1><p>지원사업·연구개발 공고를 찾고 원문을 확인하세요.</p></div><button type="button" class="quiet" id="health-toggle" aria-controls="health" aria-expanded="false">수집 정보</button></section>
<section class="notice" id="health" hidden aria-label="수집 정보"><h2>저장된 공고 정보</h2><p>전체 <strong id="total"></strong>건 · 마지막 수집 기록 <strong id="updated"></strong></p><ul id="dist"></ul><p>마감 전 표시는 최근 48시간 안에 확인한 신청기간 기준입니다. 확인이 오래되거나 정보가 상충하면 재확인이 필요합니다. 수집 완료도 신청자격을 보장하지 않습니다.</p></section>
<div class="search"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.7" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/></svg><input id="q" type="search" placeholder="공고명, 기관, 관심 분야를 검색하세요" aria-label="공고 검색" autocomplete="off"></div>
<nav class="tabs" aria-label="공고 종류"><button type="button" data-kind="support" aria-pressed="true">지원·사업 공고</button><button type="button" data-kind="bid" aria-pressed="false">입찰</button><button type="button" data-kind="all" aria-pressed="false">전체</button></nav>
<div class="tools"><div class="views" id="view" role="group" aria-label="빠른 필터"><button type="button" data-view="all" aria-pressed="true">전체</button><button type="button" data-view="soon" aria-pressed="false">7일 내 마감</button><button type="button" data-view="new" aria-pressed="false">새로 수집</button></div><div class="tools-right"><select id="sort" aria-label="정렬"><option value="near">가까운 마감순</option><option value="far">먼 마감순</option></select><button type="button" class="quiet" id="filter-toggle" aria-controls="filters" aria-expanded="false">상세 필터</button></div></div>
<section class="filter-box" id="filters" hidden aria-label="상세 필터"><label>분야 <select id="cat" aria-label="분야 필터"><option value="__ALL__">전체 분야</option><option value="__TECH__">기술 전체</option></select></label><label>출처 <select id="source" aria-label="출처 필터"><option value="all">전체 출처</option></select></label><label>보기 <select id="layout" aria-label="목록 레이아웃"><option value="table">표</option><option value="cards">카드</option></select></label><label><input id="hideClosed" type="checkbox" checked>마감된 공고 숨기기</label></section>
<div class="active-filters" id="active-filters" aria-label="적용 중인 필터" hidden></div>
<div class="results-top" id="results" tabindex="-1"><span class="count" id="count" role="status" aria-live="polite">공고를 불러오는 중입니다.</span><button type="button" class="text-button" id="unknown" aria-pressed="false">마감 확인 필요</button></div>
<noscript><p class="load-error">공고 검색과 목록을 보려면 JavaScript를 켜 주세요.</p></noscript>
<div class="load-error" id="load-error" role="alert" hidden>공고 목록을 표시하지 못했습니다. 페이지를 새로고침해 주세요. 문제가 계속되면 각 기관의 공식 사이트에서 공고를 확인해 주세요.</div>
<section class="list" id="list" aria-label="공고 목록"><table aria-label="공고 검색 결과"><colgroup><col class="col-title"><col class="col-status"><col class="col-deadline"><col class="col-link"></colgroup><thead><tr><th scope="col">공고</th><th scope="col">접수 상태</th><th scope="col">마감</th><th scope="col">원문</th></tr></thead><tbody id="rows"></tbody></table><div class="empty" id="empty" hidden><h2 id="empty-title">조건에 맞는 공고가 없습니다</h2><p id="empty-help">검색어를 줄이거나 선택한 필터를 해제해 보세요.</p><button type="button" id="empty-reset">검색 조건 초기화</button></div></section>
<nav class="pagination" id="pagination" aria-label="목록 페이지" hidden><button type="button" class="quiet" id="prev">이전</button><span class="page-summary" id="page-summary"></span><button type="button" class="quiet" id="next">다음</button></nav>
<footer class="footer-note"><p>마감과 신청자격은 신청 전 기관 원문에서 확인하세요.</p><p>D-day는 한국 시각 기준 · 새로 수집은 최근 3일간 수집된 공고</p></footer>
</main>
<script>
const DATA = __DATA__;
const HEALTH = __HEALTH__;
__STATUS_JS__
const SRC = { kstartup: 'K-Startup', bizinfo: '기업마당', msit: '과기정통부', nara: '나라장터', iris: 'IRIS' };
const EXCERPTS = [['funding_amount', '지원금액'], ['eligibility', '신청자격'], ['required_docs', '제출서류'], ['key_dates', '주요일정']];
const DAY = 86400000;
const PAGE_SIZE = 50;
function koreanDate(now = new Date()) {
  return new Date(now.getTime() + 9 * 3600000).toISOString().slice(0, 10);
}
function parseDeadline(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?$/.exec(value || '');
  if (!m) return null;
  const [year, month, day] = m.slice(1, 4).map(Number);
  const utc = Date.UTC(year, month - 1, day);
  if (new Date(utc).toISOString().slice(0, 10) !== m[0].slice(0, 10)) return null;
  const timed = m[4] !== undefined;
  const hour = Number(m[4] || 0), minute = Number(m[5] || 0), second = Number(m[6] || 0);
  if (hour > 23 || minute > 59 || second > 59) return null;
  const end = utc - 9 * 3600000 + (timed ? hour * 3600000 + minute * 60000 + second * 1000 : DAY);
  return { date: m[0].slice(0, 10), utc, end, time: timed ? `${m[4]}:${m[5]}` : '' };
}
function noticeState(d, now = new Date()) {
  const deadline = parseDeadline(d.deadline);
  const days = deadline ? Math.round((deadline.utc - Date.parse(koreanDate(now) + 'T00:00:00Z')) / DAY) : null;
  const kind = reliabilityState(d, now);
  const labels = { open: '마감 전', closed: '마감', scheduled: '접수 예정', unknown: '확인 필요', conflict: '정보 상충' };
  return { deadline, days, kind, closed: kind === 'closed', label: labels[kind], tone: ['open', 'closed'].includes(kind) ? kind : 'unknown' };
}
function isNew(d, now = new Date()) {
  // 운영 GitHub Actions는 UTC로 실행된다. 기존 시간대 없는 수집 기록도 UTC로 해석한다.
  const raw = d.first_seen || '';
  const stamp = new Date(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(raw) ? raw + 'Z' : raw);
  if (Number.isNaN(stamp.getTime()) || stamp > now) return false;
  const age = (Date.parse(koreanDate(now)) - Date.parse(koreanDate(stamp))) / DAY;
  return age >= 0 && age <= 2;
}
function searchFields(d) {
  const fields = ['title', 'agency', 'target', 'specialized_agency', 'category'];
  if (d.summary_current) fields.push('summary');
  if (d.extraction_status === 'ok' && d.extraction_current) fields.push(...EXCERPTS.map(([field]) => field));
  return fields.map(field => String(d[field] || '')).concat(SRC[d.source] || d.source || '');
}
function safeUrl(value) {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : ''; }
  catch { return ''; }
}
function filterNotices(data, filters, now = new Date()) {
  const query = (filters.q || '').trim().toLowerCase();
  return data.filter(d => {
    if (filters.kind === 'support' && d.source === 'nara') return false;
    if (filters.kind === 'bid' && d.source !== 'nara') return false;
    if (filters.source !== 'all' && d.source !== filters.source) return false;
    if (filters.cat === '__TECH__' && d.is_tech !== '1') return false;
    if (!['__TECH__', '__ALL__'].includes(filters.cat) && d.category !== filters.cat) return false;
    return !query || searchFields(d).some(text => text.toLowerCase().includes(query));
  }).map(d => ({ d, state: noticeState(d, now) })).filter(({ d, state }) => {
    if (filters.hideClosed && state.closed) return false;
    if (filters.view === 'soon' && (state.kind !== 'open' || state.days === null || state.days < 0 || state.days > 7)) return false;
    if (filters.view === 'new' && !isNew(d, now)) return false;
    if (filters.view === 'unknown' && !['unknown', 'conflict'].includes(state.kind)) return false;
    return true;
  }).sort((a, b) => {
    if (!a.state.deadline) return b.state.deadline ? 1 : 0;
    if (!b.state.deadline) return -1;
    const delta = a.state.deadline.end - b.state.deadline.end;
    return filters.sort === 'far' && filters.view !== 'soon' ? -delta : delta;
  });
}
// DOM wiring
const $ = id => document.getElementById(id);
let kind = 'support', view = 'all', page = 1, searchTimer, refreshTimer;
const boundaries = DATA.flatMap(d => [instant(d.deadline, true), instant(d.starts_at),
  ...[d.source_checked_at, d.verified_at].map(value => { const t = instant(value); return t === null ? null : t + 48 * 3600000; })]).filter(t => t !== null);
const distribution = Object.create(null);
for (const d of DATA) { const entry = distribution[d.source] ||= { count: 0, latest: '' }; entry.count++; if (d.last_seen > entry.latest) entry.latest = d.last_seen; }
const expandedKeys = new Set();
function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
function highlight(parent, text, query) {
  text = String(text || '');
  if (!query) { parent.append(document.createTextNode(text)); return; }
  const lower = text.toLowerCase();
  let from = 0, at;
  while ((at = lower.indexOf(query, from)) !== -1) {
    parent.append(document.createTextNode(text.slice(from, at)), element('mark', '', text.slice(at, at + query.length)));
    from = at + query.length;
  }
  parent.append(document.createTextNode(text.slice(from)));
}
function currentFilters() {
  return { q: $('q').value.trim().toLowerCase(), kind, view, cat: $('cat').value, source: $('source').value, sort: $('sort').value, hideClosed: $('hideClosed').checked };
}
function addDetail(detail, d, query, close) {
  const cell = element('td'); cell.colSpan = 4;
  const heading = element('h2'); highlight(heading, d.title, query); cell.append(heading);
  const dl = element('dl');
  const fields = [['target', '신청 대상'], ['specialized_agency', '전담·수요 기관']];
  if (d.summary_current) fields.unshift(['summary', '요약']);
  if (d.extraction_status === 'ok' && d.extraction_current) fields.push(...EXCERPTS.map(([field, label]) => [field, label + ' 발췌']));
  let shown = 0;
  for (const [field, label] of fields) {
    if (!d[field]) continue;
    const dd = element('dd'); highlight(dd, d[field], query);
    dl.append(element('dt', '', label), dd); shown++;
  }
  if (!shown) cell.append(element('p', '', '상세 정보가 제공되지 않았습니다. 원문에서 확인해 주세요.'));
  else cell.append(dl);
  const from = safeUrl(d.extracted_from);
  if (from && d.extraction_status === 'ok' && d.extraction_current) {
    const p = element('p'); const link = element('a', '', '발췌 출처 확인 ↗');
    link.href = from; link.target = '_blank'; link.rel = 'noopener noreferrer'; p.append(link); cell.append(p);
  }
  cell.append(element('p', '', '출처 응답 확인: ' + displayTime(d.source_checked_at) + ' · 원문 신청기간 확인: ' + displayTime(d.verified_at)));
  if ((d.summary && !d.summary_current) || (d.extraction_status && !d.extraction_current)) cell.append(element('p', '', '현재 공고와의 일치가 확인되지 않은 요약·발췌는 표시하지 않습니다.'));
  cell.append(element('p', '', '요약과 발췌는 공고 원문의 일부입니다. 신청 전 최신 원문과 자격을 확인하세요.'));
  const button = element('button', 'quiet', '상세 닫기'); button.type = 'button'; button.onclick = close;
  cell.append(button); detail.append(cell);
}
function makeRow(d, state, query, index, now) {
  const row = element('tr', 'record');
  const recordKey = d.key || `${d.source}:${d.source_id}:${index}`;
  row.dataset.recordKey = recordKey;
  const titleCell = element('td', 'title-cell');
  const toggle = element('button', 'title-button'); toggle.type = 'button';
  const title = element('span', 'title-text'); highlight(title, d.title || '제목 미제공', query); toggle.append(title);
  toggle.setAttribute('aria-expanded', 'false'); toggle.setAttribute('aria-controls', 'detail-' + index);
  titleCell.append(toggle);
  const meta = element('div', 'meta');
  const labels = [d.agency, SRC[d.source] || d.source, d.category].filter(Boolean);
  labels.forEach((label, i) => { if (i) meta.append(element('span', 'dot', '·')); const span = element('span'); highlight(span, label, query); meta.append(span); });
  if (isNew(d, now)) meta.append(element('span', 'new', '새로 수집'));
  titleCell.append(meta);
  if (query && ![d.title, d.agency, SRC[d.source], d.category].some(text => String(text || '').toLowerCase().includes(query))) {
    const matched = searchFields(d).find(text => text.toLowerCase().includes(query));
    if (matched) { const at = matched.toLowerCase().indexOf(query); const start = Math.max(0, at - 30); const end = Math.min(matched.length, at + query.length + 70); const snippet = element('div', 'match'); highlight(snippet, (start ? '…' : '') + matched.slice(start, end) + (end < matched.length ? '…' : ''), query); titleCell.append(snippet); }
  }
  const status = element('td', 'status-cell'); status.append(element('span', 'badge ' + state.tone, state.label));
  const deadline = element('td', 'deadline' + (state.kind === 'open' && state.days !== null && state.days <= 7 ? ' urgent' : ''));
  deadline.append(element('strong', '', state.closed ? '마감' : ['unknown', 'conflict'].includes(state.kind) ? '마감 확인 필요' : state.days === 0 ? '오늘 마감' : 'D-' + state.days));
  if (state.deadline) {
    const date = state.deadline.date.replace(/-/g, '.');
    deadline.append(element('small', '', (['unknown', 'conflict'].includes(state.kind) ? '저장된 마감 ' : '') + date + (state.deadline.time ? ' · ' + state.deadline.time : '')));
    if (!state.deadline.time) deadline.append(element('small', '', '마감 시각 미제공'));
  } else deadline.append(element('small', '', '원문 확인 필요'));
  const urlCell = element('td', 'link-cell'); const url = safeUrl(d.url);
  if (url) { const link = element('a', 'link', '원문 ↗'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.setAttribute('aria-label', (d.title || '공고') + ' 원문 새 창 열기'); urlCell.append(link); }
  else urlCell.append(element('span', 'no-url', '원문 미제공'));
  row.append(titleCell, status, deadline, urlCell);
  const detail = element('tr', 'detail'); detail.id = 'detail-' + index; detail.hidden = true; detail.dataset.recordKey = recordKey;
  const close = () => { expandedKeys.delete(recordKey); detail.hidden = true; toggle.setAttribute('aria-expanded', 'false'); toggle.focus({ preventScroll: true }); };
  toggle.onclick = () => {
    if (!detail.childElementCount) addDetail(detail, d, query, close);
    detail.hidden = !detail.hidden;
    if (detail.hidden) expandedKeys.delete(recordKey); else expandedKeys.add(recordKey);
    toggle.setAttribute('aria-expanded', String(!detail.hidden));
  };
  if (expandedKeys.has(recordKey)) { addDetail(detail, d, query, close); detail.hidden = false; toggle.setAttribute('aria-expanded', 'true'); }
  detail.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); close(); } });
  return [row, detail];
}
function updateChips(filters) {
  const host = $('active-filters'); host.replaceChildren();
  const add = (label, clear) => { const button = element('button', '', label + ' ×'); button.type = 'button'; button.setAttribute('aria-label', label + ' 필터 해제'); button.onclick = () => { clear(); page = 1; render(); $('q').focus({ preventScroll: true }); }; host.append(button); };
  if (filters.q) add('검색: ' + filters.q, () => { $('q').value = ''; });
  if (filters.cat !== '__ALL__') add($('cat').selectedOptions[0].textContent, () => { $('cat').value = '__ALL__'; });
  if (filters.source !== 'all') add(SRC[filters.source] || filters.source, () => { $('source').value = 'all'; });
  if (!filters.hideClosed) add('마감 공고 포함', () => { $('hideClosed').checked = true; });
  if (view !== 'all') add({ soon: '7일 내 마감', new: '새로 수집', unknown: '마감 확인 필요' }[view], () => { view = 'all'; });
  host.hidden = host.childElementCount === 0;
  if (!host.hidden) { const reset = element('button', 'reset', '전체 초기화'); reset.type = 'button'; reset.onclick = resetFilters; host.append(reset); }
}
const healthLabels = {success: '수집 완료', empty: '정상 응답 0건', partial: '부분 수집', failed: '수집 실패'};
function displayTime(value, legacy = false) {
  if (!value) return '기록 없음';
  const date = new Date(legacy && !/[Z+-]\d*:?\d*$/.test(value.slice(10)) ? value + 'Z' : value);
  return Number.isNaN(date.getTime()) ? '시각 미확인' : date.toLocaleString('ko-KR', {timeZone: 'Asia/Seoul'});
}
function renderHealth(now) {
  const el = $('dist'); el.textContent = '';
  for (const [source, name] of Object.entries(SRC)) {
    const h = HEALTH.find(x => x.source === source);
    const p = document.createElement('li');
    if (h) {
      const checked = instant(h.completed_at);
      const old = checked === null || now.getTime() < checked || now.getTime() - checked > 48 * 3600000;
      p.textContent = name + ': ' + (healthLabels[h.state] || '상태 미확인') + (old ? ' · 갱신 지연' : '')
        + ' · 최근 시도 ' + displayTime(h.completed_at) + ' · ' + h.count + '건'
        + ' · 마지막 완전 수집 ' + displayTime(h.last_success);
    } else {
      const entry = distribution[source];
      const seen = entry ? entry.latest : '';
      p.textContent = name + ': 수집 상태 미확인 · 누적 ' + (distribution[source]?.count || 0) + '건'
        + ' · 과거 저장 기록 ' + displayTime(seen, true);
    }
    el.appendChild(p);
  }
}

function render() {
  const focused = document.activeElement;
  const focusedRow = focused && focused.closest('#rows tr');
  const focusedKey = focusedRow && focusedRow.dataset.recordKey;
  const focusedAction = focused && focused.matches('.detail button') ? '.detail button' : focused && focused.matches('.detail a') ? '.detail a' : focused && focused.matches('.record a') ? '.record a' : '.title-button';
  const filters = currentFilters(), now = new Date();
  let nextRefresh = instant(kstDay(now), true);
  for (const boundary of boundaries) if (boundary >= now.getTime()) nextRefresh = Math.min(nextRefresh, boundary + 50);
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(render, Math.max(50, Math.min(60000, nextRefresh - now.getTime())));
  renderHealth(now);
  const rows = filterNotices(DATA, filters, now);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE)); page = Math.min(page, pages);
  const from = (page - 1) * PAGE_SIZE;
  const fragment = document.createDocumentFragment();
  rows.slice(from, from + PAGE_SIZE).forEach(({ d, state }, i) => fragment.append(...makeRow(d, state, filters.q, from + i, now)));
  $('rows').replaceChildren(fragment);
  if (focusedKey) {
    const target = [...$('rows').querySelectorAll(focusedAction)].find(el => el.closest('tr').dataset.recordKey === focusedKey);
    if (target) target.focus({ preventScroll: true });
  }
  $('count').textContent = '검색 결과 ' + rows.length.toLocaleString() + '건';
  $('empty').hidden = rows.length !== 0;
  $('empty-title').textContent = DATA.length ? '조건에 맞는 공고가 없습니다' : '아직 저장된 공고가 없습니다';
  $('empty-help').textContent = DATA.length ? '검색어를 줄이거나 선택한 필터를 해제해 보세요.' : '공고 수집 후 이 화면에서 검색할 수 있습니다.';
  $('empty-reset').hidden = DATA.length === 0;
  $('pagination').hidden = rows.length <= PAGE_SIZE;
  $('page-summary').textContent = `${page} / ${pages} 페이지`;
  $('prev').disabled = page === 1; $('next').disabled = page === pages;
  const unknownCount = rows.filter(({ state }) => ['unknown', 'conflict'].includes(state.kind)).length;
  $('unknown').hidden = unknownCount === 0 && view !== 'unknown';
  $('unknown').textContent = view === 'unknown' ? '전체 결과로 돌아가기' : `마감 확인 필요 ${unknownCount.toLocaleString()}건`;
  $('unknown').setAttribute('aria-pressed', String(view === 'unknown'));
  document.querySelectorAll('[data-kind]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.kind === kind)));
  document.querySelectorAll('[data-view]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.view === view)));
  $('list').classList.toggle('cards', $('layout').value === 'cards');
  updateChips(filters);
  try { sessionStorage.setItem('gov-dashboard-view', JSON.stringify({ ...filters, page, layout: $('layout').value })); } catch { /* Storage may be disabled. */ }
}
function resetFilters() {
  $('q').value = ''; $('cat').value = '__ALL__'; $('source').value = 'all'; $('hideClosed').checked = true;
  $('sort').value = 'near'; view = 'all'; page = 1; render(); $('q').focus({ preventScroll: true });
}
function setup() {
  for (const category of [...new Set(DATA.map(d => d.category).filter(Boolean))].sort()) {
    const option = element('option', '', category); option.value = category; $('cat').append(option);
  }
  for (const [source, label] of Object.entries(SRC)) { const option = element('option', '', label); option.value = source; $('source').append(option); }
  $('total').textContent = DATA.length.toLocaleString();
  const latest = Object.values(distribution).reduce((max, d) => d.latest > max ? d.latest : max, '');
  $('updated').textContent = displayTime(latest, true) + ' (한국 시각)';
  try {
    const saved = JSON.parse(sessionStorage.getItem('gov-dashboard-view') || 'null');
    if (saved) {
      if (['support', 'bid', 'all'].includes(saved.kind)) kind = saved.kind;
      if (['all', 'soon', 'new', 'unknown'].includes(saved.view)) view = saved.view;
      if (typeof saved.q === 'string') $('q').value = saved.q;
      for (const id of ['cat', 'source', 'sort', 'layout']) if ([...$(id).options].some(o => o.value === saved[id])) $(id).value = saved[id];
      if (typeof saved.hideClosed === 'boolean') $('hideClosed').checked = saved.hideClosed;
      if (Number.isSafeInteger(saved.page) && saved.page > 0) page = saved.page;
    }
  } catch { /* A stored view is optional. */ }
  $('q').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { page = 1; render(); }, 120); });
  ['cat', 'source', 'sort', 'hideClosed'].forEach(id => $(id).addEventListener('change', () => { page = 1; render(); }));
  $('layout').addEventListener('change', render);
  document.querySelectorAll('[data-kind]').forEach(button => button.onclick = () => { kind = button.dataset.kind; page = 1; render(); });
  document.querySelectorAll('[data-view]').forEach(button => button.onclick = () => { view = button.dataset.view; page = 1; render(); });
  $('unknown').onclick = () => { view = view === 'unknown' ? 'all' : 'unknown'; page = 1; render(); };
  $('empty-reset').onclick = resetFilters;
  for (const [id, delta] of [['prev', -1], ['next', 1]]) $(id).onclick = () => { page += delta; render(); $('results').scrollIntoView({ block: 'start' }); $('results').focus({ preventScroll: true }); };
  for (const [buttonId, panelId] of [['filter-toggle', 'filters'], ['health-toggle', 'health']]) $(buttonId).onclick = () => { $(panelId).hidden = !$(panelId).hidden; $(buttonId).setAttribute('aria-expanded', String(!$(panelId).hidden)); };
  // Preserve browsing position when returning to the same tab. Fresh visits still start at the top.
  window.addEventListener('pagehide', () => { try { sessionStorage.setItem('gov-dashboard-scroll', String(scrollY)); } catch {} });
  render();
  const navigation = performance.getEntriesByType('navigation')[0];
  if (navigation && ['back_forward', 'reload'].includes(navigation.type)) {
    try { const y = Number(sessionStorage.getItem('gov-dashboard-scroll')); if (Number.isFinite(y) && y >= 0) requestAnimationFrame(() => scrollTo(0, y)); } catch {}
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) render(); });
}
try { setup(); } catch (error) { $('load-error').hidden = false; $('count').textContent = '목록을 불러오지 못했습니다'; console.error(error); }
</script>
</body>
</html>
"""
PAGE = PAGE.replace("__STATUS_JS__", Path(__file__).with_name("status.js").read_text(encoding="utf-8"))


def fetch_notices(db_path: str) -> list[dict]:
    """notices 전건을 last_seen 내림차순으로. NULL→"" 보정."""
    conn = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
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
        path = self.path.split("?", 1)[0]
        if path == "/assets/pretendard/PretendardVariable.woff2":
            data = (ASSETS / "pretendard" / "PretendardVariable.woff2").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "font/woff2")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path != "/":
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
        out = Path(sys.argv[sys.argv.index("--build") + 1])
        html = render_page(fetch_notices(DB_PATH), fetch_health(DB_PATH))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        shutil.copytree(ASSETS, out.parent / "assets", dirs_exist_ok=True)
        print(f"wrote {out} ({len(html.encode('utf-8'))} bytes) and assets/")
        return
    if not os.path.exists(DB_PATH):
        print(f"DB 없음: {DB_PATH}\n"
              f"(CI DB 보려면: git show origin/data:gov_notices.db > gov_notices.db)")
        sys.exit(1)
    print(f"http://127.0.0.1:{PORT}  (Ctrl+C 종료)")
    http.server.HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
