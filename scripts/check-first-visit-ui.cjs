// Read-only local fixtures: the tour must not submit forecasts, messages or scores.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const base = process.env.FIRST_VISIT_UI_URL || 'http://127.0.0.1:5174';
const key = 'turbotears-onboarding-v2';
const steps = [['/', 'Главная'], ['/season', 'Календарь'], ['/race-results', 'Результаты'], ['/drivers', 'Пелотон'], ['/compare', 'Аналитика'], ['/predictions', 'Прогнозы'], ['/community', 'С друзьями'], ['/wiki', 'Справочник F1'], ['/reaction-game', 'Игры'], ['/account', 'Аккаунт и настройки'], ['/contact-admin', 'Обратная связь']];
const race = { status: 'ok', season: 2026, round: 17, event_name: 'Singapore Grand Prix', location: 'Marina Bay', country: 'Singapore', race_start_utc: '2026-10-11T12:00:00Z', next_session_iso: '2026-10-09T09:00:00Z', next_session_name: 'Практика 1' };

async function checkCard(page) {
  await page.waitForFunction(() => document.documentElement.dataset.onboardingPhase === 'ready');
  await page.waitForFunction(() => {
    const r = document.querySelector('.first-visit-card').getBoundingClientRect();
    return r.x >= 0 && r.y >= 0 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1;
  });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  const workspace = await page.evaluate(() => {
    const p = document.querySelector('.app-content').getBoundingClientRect();
    const c = document.querySelector('.first-visit-guide').getBoundingClientRect();
    return { separate: p.right <= c.left || p.bottom <= c.top, height: p.height,
      opacity: getComputedStyle(document.querySelector('.app-page-main')).opacity,
      darkOverlay: !!document.querySelector('.first-visit-backdrop, .first-visit-dialog') };
  });
  assert.ok(workspace.separate, 'Instructions must have their own space outside the page');
  assert.ok(workspace.height >= 320, `Portrait page must retain enough room to read and scroll: ${JSON.stringify(workspace)}`);
  assert.equal(workspace.opacity, '1');
  assert.equal(workspace.darkOverlay, false);
}
async function checkTrack(page, selector) {
  const border = page.locator(`${selector} .track-route-border:visible`).first();
  await border.waitFor();
  const style = await border.evaluate(border => {
    const red = getComputedStyle(border), surface = getComputedStyle(border.nextElementSibling);
    return { color: red.stroke, width: parseFloat(red.strokeWidth), surface: parseFloat(surface.strokeWidth), borderScaling: red.vectorEffect, surfaceScaling: surface.vectorEffect, glow: red.filter };
  });
  assert.equal(style.color, 'rgb(255, 48, 40)');
  assert.ok(style.width > style.surface);
  assert.equal(style.borderScaling, 'non-scaling-stroke');
  assert.equal(style.surfaceScaling, 'non-scaling-stroke');
  assert.match(style.glow, /drop-shadow/);
}
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const [width, height] of [[320, 640], [390, 844], [1440, 900]]) {
      const context = await browser.newContext({ viewport: { width, height }, timezoneId: 'Europe/Moscow', reducedMotion: width === 390 ? 'no-preference' : 'reduce' });
      const page = await context.newPage();
      const errors = [], mutations = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/static/circuit/*.svg', route => route.fulfill({ contentType: 'image/svg+xml', body: readFileSync(join(__dirname, '../front/public/static/circuit/Singapore Grand Prix.svg')) }));
      await page.route('**/api/**', route => {
        const path = new URL(route.request().url()).pathname;
        if (route.request().method() !== 'GET' && !path.startsWith('/api/analytics/')) mutations.push(path);
        if (path === '/api/auth/me') return route.fulfill({ status: 401, json: { detail: 'Guest' } });
        if (path === '/api/next-race') return route.fulfill({ json: race });
        if (path === '/api/settings') return route.fulfill({ json: { timezone: 'Europe/Moscow' } });
        if (path === '/api/weekend-schedule') return route.fulfill({ json: { sessions: [{ name: 'Практика 1', utc_iso: '2026-10-09T09:00:00Z' }, { name: 'Гонка', utc_iso: '2026-10-11T12:00:00Z' }] } });
        if (path === '/api/season') return route.fulfill({ json: { races: [{ ...race, date: '2026-10-11' }] } });
        if (path === '/api/predictions/preview') return route.fulfill({ json: { status: 'ok', season: 2026, round: 17, event_name: race.event_name, is_open: false, profile: { display_name: '', completed: false }, prediction: null, drivers: [], scoring_rules: [] } });
        if (path === '/api/engagement/weekly') return route.fulfill({ json: { track_id: 'emerald-loop', name: 'Трасса недели', start: '2026-10-05T00:00:00Z', end: '2026-10-12T00:00:00Z', entries: [] } });
        return route.fulfill({ json: { status: 'none', items: [], results: [], rounds: [], drivers: [], constructors: [], entries: [], unread: 0 } });
      });
      await page.goto(base);
      const guide = page.locator('.first-visit-guide');
      await guide.getByRole('heading', { name: 'Главная', exact: true }).waitFor();
      await checkCard(page);
      assert.equal(await guide.locator('input[type="radio"]').count(), 0);
      assert.ok((await guide.innerText()).includes('МСК (UTC+3)'));
      const initialHistory = await page.evaluate(() => history.length);
      for (const [index, [route, title]] of steps.entries()) {
        await page.waitForFunction(route => location.pathname === route, route);
        await guide.getByRole('heading', { name: title, exact: true }).waitFor();
        assert.ok((await guide.innerText()).includes(`${index + 1} / ${steps.length}`));
        await checkCard(page);
        await page.locator(`.first-visit-highlight[data-tour-route="${route}"]`).waitFor();
        if (index === 2) {
          await guide.getByRole('button', { name: 'Назад', exact: true }).click();
          await page.waitForFunction(() => location.pathname === '/season');
          await guide.getByRole('heading', { name: 'Календарь', exact: true }).waitFor();
          await guide.getByRole('button', { name: 'Дальше →' }).click();
          await guide.getByRole('heading', { name: title, exact: true }).waitFor();
          await page.locator(`.first-visit-highlight[data-tour-route="${route}"]`).waitFor();
        }
        if (index === 7) {
          const search = page.locator('.wiki-controls input');
          await search.fill('флаг');
          assert.equal(await search.inputValue(), 'флаг');
        }
        if (width === 390 && [0, 1, 2, 5, 8].includes(index)) await page.screenshot({ path: `artifacts/section-tour-${index}-mobile.png` });
        if (width === 1440 && index === 1) await page.screenshot({ path: 'artifacts/section-tour-desktop.png' });
        await guide.getByRole('button', { name: index === steps.length - 1 ? 'На главную →' : 'Дальше →', exact: true }).click();
        if (width === 390 && index === 0) {
          assert.equal(await page.evaluate(() => document.documentElement.dataset.onboardingPhase), 'leaving');
          assert.equal(await page.evaluate(() => location.pathname), '/', 'Outgoing page remains mounted during its fade');
          assert.equal(await guide.locator('.first-visit-primary').isDisabled(), true);
        }
      }
      await page.waitForFunction(() => location.pathname === '/');
      await guide.waitFor({ state: 'hidden' });
      assert.deepEqual(await page.evaluate(k => JSON.parse(localStorage.getItem(k)), key), { status: 'completed' });
      assert.equal(await page.evaluate(() => history.length), initialHistory);
      assert.equal(await page.evaluate(() => document.documentElement.dataset.onboardingActive), undefined);
      await page.reload();
      await page.locator('.weekend-board-location').waitFor();
      assert.equal(await page.locator('dialog[open]').count(), 0);
      if (width === 1440) {
        await checkTrack(page, '.index-hero-track-map');
        await page.goto(`${base}/season`);
        await checkTrack(page, '.season-desktop-track-svg');
        await page.goto(base);
      }
      await page.getByRole('button', { name: 'Короткое знакомство →' }).click();
      await guide.waitFor();
      await page.keyboard.press('Escape');
      await guide.waitFor({ state: 'hidden' });
      assert.equal(await page.evaluate(k => JSON.parse(localStorage.getItem(k)).status, key), 'skipped');
      if (width === 390) {
        await page.evaluate(k => localStorage.removeItem(k), key);
        await page.goto(`${base}/season`);
        await page.locator('.season-page, .season-desktop-header, .page-head-title').first().waitFor();
        assert.equal(await page.locator('dialog[open]').count(), 0);
        await page.addInitScript(k => {
          const get = Storage.prototype.getItem, set = Storage.prototype.setItem;
          Storage.prototype.getItem = function(name) { if (name === k) throw new Error('Storage denied'); return get.call(this, name); };
          Storage.prototype.setItem = function(name, value) { if (name === k) throw new Error('Storage denied'); return set.call(this, name, value); };
        }, key);
        await page.goto(base);
        await guide.waitFor();
        await guide.getByRole('button', { name: 'Пропустить', exact: true }).click();
        await page.locator('.quick-access a[href="/season"]').click();
        await page.waitForURL(`${base}/season`);
        await page.getByRole('link', { name: 'Главная', exact: true }).click();
        await page.locator('.weekend-board-location').waitFor();
        assert.equal(await page.locator('dialog[open]').count(), 0);
      }
      assert.deepEqual(errors, []);
      assert.deepEqual(mutations, []);
      console.log(`Section tour ${width}×${height}: all 11 pages, back, completion, replay, Escape, history and persistence passed`);
      await context.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
