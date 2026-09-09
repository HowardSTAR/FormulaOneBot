// Mocked local UI test: no actual error messages or push subscriptions are sent.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const levels = ['minimal', 'low', 'medium', 'critical', 'blocking'];
    await page.route('**/api/**', route => {
      if (new URL(route.request().url()).pathname === '/api/web-notifications') return route.fulfill({ json: {
        items: levels.map((priority, i) => ({ id: i+1, priority, title: 'Тестовый алёрт', body: 'Источник: bot.update\nТип: TimeoutError\nПовторов в серии: 1', url: '/notifications', created_at: Date.now()/1000, read_at: null })),
        unread: 5, next_before: null, push: { enabled: false, public_key: '' },
      } });
      return route.fulfill({ json: { id: 1, role: 'admin', items: [] } });
    });
    await page.goto('http://127.0.0.1:5173/notifications');
    await page.locator('.priority-blocking').waitFor();
    assert.equal(await page.locator('.notification-priority').count(), 5);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.locator('.priority-low').scrollIntoViewIfNeeded();
    await page.screenshot({ path: 'artifacts/error-notifications-mobile.png' });
    assert.deepEqual(errors, []);
    console.log('All five priorities render; mobile layout has no horizontal overflow.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
