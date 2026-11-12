// Python status.py와 tests/fixtures/notice_states.json의 동일 규칙.
function kstDay(now = new Date()) {
  return new Date(now.getTime() + 9 * 3600000).toISOString().slice(0, 10);
}
function instant(value, end = false) {
  if (!value) return null;
  const m = value.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?(Z|[+-]\d{2}:\d{2})?)?$/);
  if (!m) return null;
  const [y, mo, d, h, mi, s] = m.slice(1, 7).map(x => Number(x || 0));
  const check = new Date(Date.UTC(y, mo - 1, d));
  if (check.getUTCFullYear() !== y || check.getUTCMonth() !== mo - 1 ||
      check.getUTCDate() !== d || h > 23 || mi > 59 || s > 59) return null;
  const text = `${m[1]}-${m[2]}-${m[3]}T${m[4] || '00'}:${m[5] || '00'}:${m[6] || '00'}${m[7] || '+09:00'}`;
  const result = new Date(text).getTime();
  return Number.isFinite(result) ? result + (end && value.length === 10 ? 86400000 : 0) : null;
}
function noticeState(d, now = new Date()) {
  const close = instant(d.deadline, true), begin = instant(d.starts_at), ts = now.getTime();
  if (d.status === 'N') return 'closed';
  if ((d.deadline && close === null) || (d.starts_at && begin === null)) return 'conflict';
  if (begin !== null && close !== null && begin >= close) return 'conflict';
  if (d.verification_status === 'conflict') return 'conflict';
  if (close !== null && ts >= close) return 'closed';
  if (close === null) return 'unknown';
  let checked = instant(d.source_checked_at);
  if (d.verification_status === 'confirmed' && d.verified_deadline === d.deadline) {
    const verified = instant(d.verified_at);
    if (verified !== null && (checked === null || verified > checked)) checked = verified;
  }
  if (checked === null || ts < checked || ts - checked > 48 * 3600000) return 'unknown';
  if (begin !== null && ts < begin) return 'scheduled';
  return 'open';
}
if (typeof module !== 'undefined') module.exports = {noticeState, kstDay, instant};
