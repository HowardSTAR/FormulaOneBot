// Local UI test with mocked authentication/settings; never sends notifications.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let settings = { timezone: 'UTC', notify_before: 60, notifications_enabled: false, reminder_sessions: 31 };
    await page.route('**/api/**', async route => {
      if (new URL(route.request().url()).pathname === '/api/account/settings') {
        if (route.request().method() === 'POST') settings = route.request().postDataJSON();
        return route.fulfill({ json: settings });
      }
      return route.fulfill({ json: { id: 1, role: 'user', telegram_id: null, items: [] } });
    });
    await page.goto('http://127.0.0.1:5173/settings');
    const checks = page.locator('.session-reminder-option input');
    await checks.first().waitFor();
    assert.equal(await checks.count(), 5);
    for (const check of await checks.all()) assert.ok(await check.isChecked());
    await checks.first().uncheck();
    await page.getByRole('button', { name: 'Сохранить настройки' }).click();
    await page.getByRole('status').filter({ hasText: 'Настройки сохранены' }).waitFor();
    assert.equal(settings.reminder_sessions, 30);
    assert.equal(settings.notifications_enabled, false);
    await page.reload();
    await checks.first().waitFor();
    assert.equal(await checks.first().isChecked(), false);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.locator('.session-reminder-options').screenshot({ path: 'artifacts/session-reminders-mobile.png' });
    await page.setViewportSize({ width: 1440, height: 1000 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(errors, []);
    console.log('Five categories, save/reload, web-only account, mobile and desktop layout: OK');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
