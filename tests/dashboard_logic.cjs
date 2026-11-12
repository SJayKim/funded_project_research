// Run the actual embedded dashboard functions without a DOM or external services.
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const code = readFileSync(require('node:path').join(__dirname, '../funded_project_research/serve.py'), 'utf8')
  .split('<script>')[1].split('// DOM wiring')[0].replace('__DATA__', '[]');
const context = vm.createContext({ Date, URL });
vm.runInContext(code, context);
const { parseDeadline, noticeState, isNew, filterNotices, safeUrl, koreanDate } = context;
const now = new Date('2026-11-12T07:00:00Z'); // 16:00 KST
const filters = { q: '', kind: 'support', source: 'all', cat: '__ALL__', view: 'all', hideClosed: true, sort: 'near' };
const record = (extra = {}) => ({ source: 'kstartup', source_id: '1', title: '공고', status: '', deadline: '2026-11-15', ...extra });
const ids = rows => Array.from(rows, ({ d }) => d.source_id);

test('D-day uses current Korean date, not last collection or browser time zone', () => {
  assert.equal(koreanDate(new Date('2026-11-12T15:01:00Z')), '2026-11-13');
  assert.equal(noticeState(record({ last_seen: '2026-06-01' }), now).days, 3);
  assert.equal(noticeState(record(), new Date('2026-11-12T15:01:00Z')).days, 2);
});
test('invalid and absent dates stay unknown; leap days are validated', () => {
  for (const value of ['', '상시', '2026-02-29', '2026-02-30', '2026-13-01', '2026-11-12 25:61', '2026-11-12 09:00:60']) assert.equal(parseDeadline(value), null, value);
  assert.ok(parseDeadline('2028-02-29'));
  assert.equal(noticeState(record({ deadline: '' }), now).days, null);
});
test('date-only deadlines remain valid throughout the Korean day without inventing a time', () => {
  const d = record({ deadline: '2026-11-12' });
  assert.equal(noticeState(d, new Date('2026-11-12T14:59:59Z')).closed, false);
  assert.equal(noticeState(d, new Date('2026-11-12T15:00:00Z')).closed, true);
  assert.equal(parseDeadline(d.deadline).time, '');
});
test('explicit deadline times and closed source status override open labels', () => {
  assert.equal(noticeState(record({ deadline: '2026-11-12 15:59:00', status: 'Y' }), now).label, '마감');
  assert.equal(noticeState(record({ deadline: '2026-12-31', status: 'N' }), now).closed, true);
  assert.equal(noticeState(record(), now).label, '미확인');
  assert.equal(noticeState(record({ status: 'Y' }), now).label, '접수중');
});
test('newly collected uses UTC collection timestamps and Korean calendar days', () => {
  assert.equal(isNew(record({ first_seen: '2026-11-09T16:00:00' }), now), true);
  assert.equal(isNew(record({ first_seen: '2026-11-09T10:00:00' }), now), false);
  assert.equal(isNew(record({ first_seen: '2027-01-01T00:00:00' }), now), false);
  assert.equal(isNew(record({ first_seen: 'garbage' }), now), false);
});
test('support and bid views partition all notices without a hidden technical filter', () => {
  const data = [record({ source_id: 'support', is_tech: '0' }), record({ source: 'nara', source_id: 'bid' })];
  assert.deepEqual(ids(filterNotices(data, filters, now)), ['support']);
  assert.deepEqual(ids(filterNotices(data, { ...filters, kind: 'bid' }, now)), ['bid']);
  assert.equal(filterNotices(data, { ...filters, kind: 'all' }, now).length, 2);
  assert.equal(filterNotices(data, { ...filters, cat: '__TECH__' }, now).length, 0);
});
test('search preserves agency, summary, target, specialized agency and verified excerpts', () => {
  for (const field of ['title', 'summary', 'agency', 'target', 'specialized_agency', 'category', 'funding_amount', 'eligibility', 'required_docs', 'key_dates']) {
    assert.equal(filterNotices([record({ [field]: '검증단어', extraction_status: 'ok' })], { ...filters, q: '검증단어' }, now).length, 1, field);
  }
  assert.equal(filterNotices([record({ required_docs: '실패발췌', extraction_status: 'failed' })], { ...filters, q: '실패발췌' }, now).length, 0);
});
test('unknown deadlines sort last in either direction and remain accessible', () => {
  const data = [record({ source_id: 'unknown', deadline: '' }), record({ source_id: 'far', deadline: '2026-12-31' }), record({ source_id: 'near', deadline: '2026-11-13' })];
  assert.deepEqual(ids(filterNotices(data, filters, now)), ['near', 'far', 'unknown']);
  assert.deepEqual(ids(filterNotices(data, { ...filters, sort: 'far' }, now)), ['far', 'near', 'unknown']);
  assert.deepEqual(ids(filterNotices(data, { ...filters, view: 'unknown' }, now)), ['unknown']);
});
test('seven-day view excludes closed and unknown dates even when closed notices are included', () => {
  const data = [record({ source_id: 'valid' }), record({ source_id: 'closed', status: 'N' }), record({ source_id: 'unknown', deadline: '' }), record({ source_id: 'expired', deadline: '2026-11-12 14:00' })];
  assert.deepEqual(ids(filterNotices(data, { ...filters, view: 'soon', hideClosed: false }, now)), ['valid']);
});
test('category and source filters combine; all archived records remain reachable', () => {
  const data = [record({ source_id: '1', source: 'bizinfo', category: '로봇', status: 'N' }), record({ source_id: '2', source: 'iris', category: 'AI' })];
  assert.deepEqual(ids(filterNotices(data, { ...filters, source: 'bizinfo', cat: '로봇', hideClosed: false }, now)), ['1']);
});
test('links accept only absolute HTTP(S) URLs', () => {
  for (const url of ['', 'javascript:alert(1)', 'data:text/html,test', '//evil.example', '/relative', 'file:///etc/passwd']) assert.equal(safeUrl(url), '');
  assert.equal(safeUrl('https://example.com/a?b=c'), 'https://example.com/a?b=c');
});
