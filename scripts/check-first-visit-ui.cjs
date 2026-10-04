// First-session checks use local fixtures; no account is created or updated.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const base = process.env.FIRST_VISIT_UI_URL || 'http://127.0.0.1:5174';
const key = 'turbotears-onboarding-v1';
const race = { status: 'ok', season: 2026, round: 17, event_name: 'Singapore Grand Prix', location: 'Marina Bay', country: 'Singapore', race_start_utc: '2026-10-11T12:00:00Z', next_session_iso: '2026-10-09T09:00:00Z', next_session_name: 'Практика 1' };
const races = [{ ...race, date: '2026-10-11', time: '12:00:00Z' }];

async function checkCard(page) {
  await page.waitForFunction(() => {
    const card = document.querySelector('.first-visit-card');
    const r = card.getBoundingClientRect();
    return r.x >= 0 && r.y >= 0 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1;
  });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
}
async function checkTrack(page, selector) {
  const border = page.locator(`${selector} .track-route-border:visible`).first();
  await border.waitFor();
  const style = await border.evaluate(border => {
    const red = getComputedStyle(border), surface = getComputedStyle(border.nextElementSibling);
    return { color: red.stroke, width: parseFloat(red.strokeWidth), surface: parseFloat(surface.strokeWidth), borderScaling: red.vectorEffect, surfaceScaling: surface.vectorEffect, glow: red.filter, opacity: red.opacity };
  });
  assert.equal(style.color, 'rgb(255, 48, 40)');
  assert.ok(style.width > style.surface);
  assert.equal(style.borderScaling, 'non-scaling-stroke');
  assert.equal(style.surfaceScaling, 'non-scaling-stroke');
  assert.match(style.glow, /drop-shadow/);
  assert.equal(style.opacity, '1');
}
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const [width, height, goal, destination] of [[320, 640, 'schedule', '/season'], [390, 844, 'predictions', '/predictions'], [1440, 900, 'results', '/race-results']]) {
      const context = await browser.newContext({ viewport: { width, height }, timezoneId: 'Europe/Moscow', reducedMotion: 'reduce' });
      const page = await context.newPage();
      const errors = [];
      let emptySchedule = false;
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/static/circuit/*.svg', route => route.fulfill({ contentType: 'image/svg+xml', body: readFileSync(join(__dirname, '../front/public/static/circuit/Singapore Grand Prix.svg')) }));
      await page.route('**/api/**', route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/auth/me') return route.fulfill({ status: 401, json: { detail: 'Guest' } });
        if (path === '/api/next-race') return route.fulfill({ json: race });
        if (path === '/api/settings') return route.fulfill({ json: { timezone: 'Europe/Moscow' } });
        if (path === '/api/weekend-schedule') return route.fulfill({ json: { sessions: emptySchedule ? [] : [{ name: 'Практика 1', utc_iso: '2026-10-09T09:00:00Z' }, { name: 'Квалификация', utc_iso: '2026-10-10T13:00:00Z' }, { name: 'Гонка', utc_iso: '2026-10-11T12:00:00Z' }] } });
        if (path === '/api/season') return route.fulfill({ json: { races } });
        return route.fulfill({ json: { status: 'none', items: [], results: [], rounds: [], drivers: [], constructors: [], entries: [], unread: 0 } });
      });
      await page.goto(base);
      const guide = page.getByRole('dialog');
      await page.getByRole('heading', { name: 'Ваш уик-энд начинается здесь' }).waitFor();
      await checkCard(page);
      assert.ok((await guide.innerText()).includes('МСК (UTC+3)'));
      await guide.locator(`input[value="${goal}"]`).check();
      await page.keyboard.press('Tab');
      assert.ok(await page.evaluate(() => document.querySelector('.first-visit-dialog').contains(document.activeElement)));
      if (width === 390 || width === 1440) await page.screenshot({ path: `artifacts/first-visit-welcome-${width}.png` });
      await guide.getByRole('button', { name: 'Показать, где что' }).click();
      for (const title of ['Когда следующая сессия?', 'Ваш первый прогноз', 'Что произошло на трассе?']) {
        await page.getByRole('heading', { name: title }).waitFor();
        await checkCard(page);
        await page.locator('.first-visit-highlight').waitFor();
        assert.ok(await page.locator('.first-visit-highlight').evaluate(el => el.getBoundingClientRect().height > 0));
        await page.waitForFunction(() => {
          const card = document.querySelector('.first-visit-card').getBoundingClientRect();
          const target = document.querySelector('.first-visit-highlight').getBoundingClientRect();
          return card.bottom <= target.top || card.top >= target.bottom || card.right <= target.left || card.left >= target.right;
        });
        if (width === 390 && title === 'Когда следующая сессия?') await page.screenshot({ path: 'artifacts/first-visit-tip-mobile.png' });
        if (title !== 'Что произошло на трассе?') await guide.getByRole('button', { name: 'Дальше →' }).click();
      }
      await guide.getByRole('button', { name: 'Назад', exact: true }).click();
      await page.getByRole('heading', { name: 'Ваш первый прогноз' }).waitFor();
      await guide.getByRole('button', { name: 'Дальше →' }).click();
      const action = { schedule: 'Открыть календарь', predictions: 'Перейти к прогнозам', results: 'Посмотреть результаты' }[goal];
      await guide.getByRole('button', { name: action, exact: true }).click();
      await page.waitForURL(`${base}${destination}`);
      assert.deepEqual(await page.evaluate(k => JSON.parse(localStorage.getItem(k)), key), { status: 'completed', goal });
      assert.equal(await page.evaluate(() => document.documentElement.dataset.onboardingActive), undefined);
      await page.goto(base);
      await page.locator('.first-visit-entry button').waitFor();
      assert.equal(await page.locator('dialog[open]').count(), 0);
      if (width === 1440) {
        await checkTrack(page, '.index-hero-track-map');
        await page.screenshot({ path: 'artifacts/neon-home-desktop.png' });
        await page.goto(`${base}/season`);
        await checkTrack(page, '.season-desktop-track-svg');
        await page.screenshot({ path: 'artifacts/neon-calendar-desktop.png' });
        await page.goto(base);
      }
      await page.getByRole('button', { name: 'Короткое знакомство →' }).click();
      await guide.waitFor();
      assert.ok(await guide.locator(`input[value="${goal}"]`).isChecked());
      await page.keyboard.press('Escape');
      await guide.waitFor({ state: 'hidden' });
      assert.equal(await page.evaluate(k => JSON.parse(localStorage.getItem(k)).status, key), 'skipped');
      assert.equal(await page.getByRole('button', { name: 'Короткое знакомство →' }).evaluate(el => el === document.activeElement), true);
      await page.reload();
      await page.locator('.weekend-board-location').waitFor();
      assert.equal(await page.locator('dialog[open]').count(), 0);
      if (width === 390) {
        await page.goto(`${base}/next-race`);
        await checkTrack(page, '.next-race-mobile-track-svg');
        // A fresh deep link must remain usable, without a home onboarding overlay.
        await page.evaluate(k => localStorage.removeItem(k), key);
        await page.goto(`${base}/season`);
        await page.getByRole('heading', { name: 'Календарь', exact: true }).waitFor();
        assert.equal(await page.locator('dialog[open]').count(), 0);
        // Recover corrupted storage and offer a usable tip even with no sessions.
        await page.evaluate(k => localStorage.setItem(k, '{broken'), key);
        emptySchedule = true;
        await page.goto(base);
        await guide.waitFor();
        await guide.getByRole('button', { name: 'Показать, где что' }).click();
        await page.getByRole('heading', { name: 'Когда следующая сессия?' }).waitFor();
        await checkCard(page);
        await guide.getByRole('button', { name: 'Закрыть знакомство' }).click();
        await guide.waitFor({ state: 'hidden' });
        // Private/embedded storage still remembers dismissal for this SPA session.
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
        console.log('Missing schedule, corrupt/denied storage, direct links, mobile neon passed');
      }
      assert.deepEqual(errors, []);
      console.log(`First visit ${width}×${height}: goal, tour, back, completion, replay, Escape, persistence passed`);
      await context.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
