// Mock APIs: no actual predictions or votes are submitted.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    const errors = []; const votes = [];
    page.on('pageerror', e => errors.push(e.message));
    const drivers = [
      { code: 'HAM', name: 'Lewis Hamilton', constructorName: 'Ferrari' },
      { code: 'LEC', name: 'Charles Leclerc', constructorName: 'Ferrari' },
      { code: 'NOR', name: 'Lando Norris', constructorName: 'McLaren' },
    ];
    await page.route('**/api/**', route => {
      const path = new URL(route.request().url()).pathname;
      if (path === '/api/pilot-portrait') return route.fulfill({ status: 404, body: '' });
      const json = {
        '/api/predictions/current': { status: 'ok', season: 2026, round: 1, event_name: 'Test GP', is_open: true, profile: { display_name: 'Tester', completed: true }, drivers, prediction: null, scoring_rules: [] },
        '/api/predictions/leaderboard': { entries: [], rounds: [] },
        '/api/drivers': { drivers },
        '/api/season': { races: [{ round: 1, event_name: 'Test GP', date: new Date().toISOString(), race_start_utc: new Date(Date.now() - 7200000).toISOString() }] },
        '/api/votes/me': { race_votes: {}, driver_votes: {} },
        '/api/votes/stats': { stats: [] }, '/api/votes/driver-stats': { stats: [] },
      }[path] || { id: 1, telegram_id: 42, role: 'user' };
      if (path === '/api/votes/driver') votes.push(route.request().postDataJSON());
      return route.fulfill({ json });
    });
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto('http://127.0.0.1:5173/predictions');
      await page.getByRole('button', { name: /^Победитель:/ }).click();
      await page.getByRole('textbox', { name: 'Поиск пилота' }).fill('ferrari');
      assert.equal(await page.locator('.driver-picker-option').count(), 2);
      await page.locator('.driver-picker-option').filter({ hasText: 'Lewis Hamilton' }).click();
      assert.equal(await page.getByRole('dialog').count(), 0);
      await page.getByRole('button', { name: /^2 место:/ }).click();
      assert.ok(await page.locator('.driver-picker-option').filter({ hasText: 'Lewis Hamilton' }).isDisabled());
      await page.getByRole('textbox', { name: 'Поиск пилота' }).fill('nothing');
      await page.getByText('Пилоты не найдены').waitFor();
      await page.keyboard.press('Escape');
      assert.ok(await page.getByRole('button', { name: /^2 место:/ }).evaluate(el => el === document.activeElement));
      await page.getByRole('button', { name: /^Победитель:/ }).click();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.getByRole('dialog').evaluate(async el => { await Promise.all(el.getAnimations().map(animation => animation.finished)); });
      await page.screenshot({ path: `artifacts/driver-picker-${width}.png` });
      await page.keyboard.press('Escape');
      await page.goto('http://127.0.0.1:5173/voting?round=1');
      await page.getByRole('button', { name: 'Пилот дня', exact: true }).click();
      await page.getByRole('button', { name: /^Пилот дня:/ }).click();
      await page.locator('.driver-picker-option').filter({ hasText: 'Lando Norris' }).click();
    }
    assert.equal(votes.length, 2);
    assert.ok(votes.every(vote => vote.driver_code === 'NOR'));
    assert.deepEqual(errors, []);
    console.log('Mobile/desktop predictions and voting, search, duplicate restriction, fallback portraits, Escape and focus: OK');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
