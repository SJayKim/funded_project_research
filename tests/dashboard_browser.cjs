// Optional browser regression: NODE_PATH=<playwright node_modules> node tests/dashboard_browser.cjs [URL]
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { mkdirSync, writeFileSync } = require('node:fs');
const path = require('node:path');
const base = process.argv[2] || 'http://127.0.0.1:48272/';
const output = path.resolve('.gstack/dashboard-verification');
mkdirSync(output, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, timezoneId: 'America/Los_Angeles' });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base, { waitUntil: 'load', timeout: 60000 });
    await page.locator('.record').first().waitFor();
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.locator('.record').count(), 50);
    assert.equal(await page.locator('#load-error').isVisible(), false);
    assert.equal(await page.evaluate(() => document.fonts.check('16px "Pretendard Variable"')), true);
    const real = await page.locator('#count').innerText();
    await page.screenshot({ path: path.join(output, 'desktop.png') });
    await page.locator('.title-button').first().click();
    assert.equal(await page.locator('.detail:not([hidden])').count(), 1);
    await page.evaluate(() => render()); // the same path used for time refresh
    assert.equal(await page.locator('.detail:not([hidden])').count(), 1);
    assert.equal(await page.evaluate(() => document.activeElement.classList.contains('title-button')), true);
    await page.locator('.detail:not([hidden]) .quiet').click();
    await page.locator('#next').click();
    assert.match(await page.locator('#page-summary').innerText(), /^2 /);
    await page.locator('#prev').click();
    await page.locator('[data-kind="bid"]').click();
    assert.equal(await page.locator('.record .meta').first().innerText().then(text => text.includes('나라장터')), true);
    await page.locator('[data-kind="support"]').click();
    const widths = [];
    for (const width of [320, 375, 768, 1280, 1440]) {
      await page.setViewportSize({ width, height: width < 740 ? 812 : 1000 });
      const size = await page.evaluate(() => ({ viewport: innerWidth, content: document.documentElement.scrollWidth }));
      assert.equal(size.viewport, size.content, JSON.stringify(size));
      widths.push(size);
      if (width === 375) await page.screenshot({ path: path.join(output, 'mobile.png') });
    }
    await page.setViewportSize({ width: 720, height: 500 }); // 1440 CSS px at 200% equivalent reflow
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);

    const today = new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 10);
    const soon = new Date(Date.parse(today) + 3 * 86400000).toISOString().slice(0, 10);
    const fixture = [
      { key: 'test:safe', source: 'kstartup', source_id: 'safe', title: '브라우저 검증 공고', deadline: soon, status: 'Y', url: 'https://example.com/notice', category: 'AI', summary: '숨겨진검색어', first_seen: new Date().toISOString() },
      { key: 'test:unknown', source: 'msit', title: '마감 미확인 공고', deadline: '', status: '', url: '', category: '기타' },
      { key: 'test:closed', source: 'bizinfo', title: '종료된 공고', deadline: soon, status: 'N', url: 'https://example.com/closed' },
      { key: 'test:xss', source: 'kstartup', title: '<img src=x onerror="window.__xss=1">' + '아주긴한글제목'.repeat(50), deadline: soon, category: '<svg onload="window.__xss=1">', url: 'javascript:window.__xss=1', summary: '</script><script>window.__xss=1</script>', extraction_status: 'ok', required_docs: '서류검색어' },
      { key: 'test:bid', source: 'nara', title: '입찰 검증', deadline: soon, url: 'https://example.com/bid' }
    ];
    const html = execFileSync('python3', ['-c', 'import json,sys; from funded_project_research.serve import render_page; print(render_page(json.load(sys.stdin)))'], { input: JSON.stringify(fixture), encoding: 'utf8' });
    const fixtureURL = new URL('browser-fixture', base).href;
    await page.route(fixtureURL, route => route.fulfill({ contentType: 'text/html', body: html }));
    await page.goto(fixtureURL);
    await page.evaluate(() => { sessionStorage.clear(); });
    await page.reload();
    assert.equal(await page.locator('.record').count(), 3);
    assert.equal(await page.locator('#rows img, #rows svg, #rows script').count(), 0);
    assert.equal(await page.evaluate(() => window.__xss), undefined);
    assert.equal(await page.locator('#rows a[href^="javascript:"]').count(), 0);
    await page.locator('#q').fill('숨겨진검색어');
    await page.waitForFunction(() => document.querySelectorAll('.record').length === 1);
    assert.equal(await page.locator('.match mark').innerText(), '숨겨진검색어');
    await page.locator('.title-button').click();
    assert.match(await page.locator('.detail:not([hidden])').innerText(), /숨겨진검색어/);
    await page.locator('.detail:not([hidden]) button').focus();
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.title-button').getAttribute('aria-expanded'), 'false');
    assert.equal(await page.evaluate(() => document.activeElement.classList.contains('title-button')), true);
    assert.equal(await page.locator('.link').getAttribute('href'), 'https://example.com/notice');
    await page.locator('#q').fill('없는검색어');
    await page.locator('#empty').waitFor({ state: 'visible' });
    await page.locator('#empty-reset').click();
    assert.equal(await page.locator('.record').count(), 3);
    await page.locator('#unknown').click();
    assert.equal(await page.locator('.record').count(), 1);
    assert.match(await page.locator('.deadline').innerText(), /마감 미확인/);
    assert.equal(await page.locator('.link').count(), 0);
    await page.locator('#unknown').click();
    await page.locator('#filter-toggle').click();
    await page.locator('#hideClosed').uncheck();
    assert.equal(await page.locator('.record').count(), 4);
    await page.locator('#source').selectOption('bizinfo');
    assert.equal(await page.locator('.record').count(), 1);
    assert.equal(await page.locator('.badge').innerText(), '마감');
    await page.reload();
    assert.equal(await page.locator('#source').inputValue(), 'bizinfo');
    await page.locator('.active-filters .reset').click();
    await page.locator('#filter-toggle').click();
    await page.locator('#layout').selectOption('cards');
    await page.setViewportSize({ width: 320, height: 812 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.locator('#cat').selectOption('<svg onload="window.__xss=1">');
    assert.equal(await page.locator('.record').count(), 1);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.locator('#q').fill('가'.repeat(100));
    await page.locator('#empty').waitFor({ state: 'visible' });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.deepEqual(errors, []);
    const report = { actualDataResult: real, widths, browser: 'Chromium', browserTimezone: 'America/Los_Angeles', checks: ['pagination', 'detail and clock refresh', 'focus and Escape', 'bid view', 'search snippets', 'empty and reset', 'unknown deadline', 'closed status', 'source filter', 'session restore', 'cards', 'long titles', 'untrusted text and links', 'local font'], pageErrors: errors };
    writeFileSync(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
