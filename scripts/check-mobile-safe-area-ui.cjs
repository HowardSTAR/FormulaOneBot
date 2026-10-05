const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.MOBILE_SAFE_AREA_UI_URL || 'http://127.0.0.1:5174';
const mobileCases = [
  { name: 'browser', width: 320, height: 640, top: 0, bottom: 0, left: 0, right: 0 },
  { name: 'telegram-portrait', width: 390, height: 844, top: 47, contentTop: 44, bottom: 34, left: 0, right: 0 },
  { name: 'telegram-landscape', width: 740, height: 390, top: 0, contentTop: 44, bottom: 21, left: 44, right: 44 },
];
async function applyInsets(page, values) {
  await page.evaluate(values => {
    for (const side of ['top', 'bottom', 'left', 'right']) {
      document.documentElement.style.setProperty(`--tg-safe-area-inset-${side}`, `${values[side] || 0}px`);
      const contentSide = `content${side[0].toUpperCase()}${side.slice(1)}`;
      document.documentElement.style.setProperty(`--tg-content-safe-area-inset-${side}`, `${values[contentSide] || 0}px`);
    }
  }, values);
}
async function checkNavigation(page, values) {
  const metrics = await page.evaluate(() => {
    const nav = document.querySelector('.mobile-primary-nav').getBoundingClientRect();
    const back = document.querySelector('.btn-back').getBoundingClientRect();
    const brand = document.querySelector('.app-header-brand').getBoundingClientRect();
    return { nav: { bottom: nav.bottom, left: nav.left, right: nav.right }, back: { top: back.top, width: back.width, height: back.height }, brandTop: brand.top, width: innerWidth, height: innerHeight, overflow: document.documentElement.scrollWidth > innerWidth };
  });
  assert.ok(metrics.height - metrics.nav.bottom >= values.bottom + 11);
  assert.ok(metrics.nav.left >= values.left + 11);
  assert.ok(metrics.nav.right <= metrics.width - values.right - 11);
  assert.ok(metrics.brandTop >= values.top + (values.contentTop || 0));
  assert.ok(metrics.back.top >= values.top + (values.contentTop || 0));
  assert.equal(metrics.back.width, 44);
  assert.equal(metrics.back.height, 44);
  assert.equal(metrics.overflow, false);
  assert.equal(await page.locator('.back-button-arrow').first().textContent(), '←');
  assert.equal(await page.getByRole('button', { name: 'Назад', exact: true }).first().isVisible(), true);
}
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const values of mobileCases) {
      const context = await browser.newContext({ viewport: { width: values.width, height: values.height }, reducedMotion: 'reduce' });
      await context.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'completed' })));
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/api/**', route => {
        if (new URL(route.request().url()).pathname === '/api/auth/me') return route.fulfill({ status: 401, json: { detail: 'Guest' } });
        if (new URL(route.request().url()).pathname === '/api/reaction-leaderboard/profile') return route.fulfill({ json: { prompt_seen: true, participate: false, display_name: '' } });
        return route.fulfill({ json: { status: 'none', items: [], entries: [], results: [] } });
      });
      await page.goto(`${base}/reaction-game`);
      await page.locator('.btn-back').first().waitFor();
      await applyInsets(page, values);
      await checkNavigation(page, values);
      await page.screenshot({ path: `artifacts/mobile-safe-area-${values.name}.png` });
      await page.getByRole('button', { name: 'Меню', exact: true }).click();
      const menu = page.locator('.mobile-menu-dialog');
      await menu.waitFor();
      const rect = await menu.evaluate(node => { const r = node.getBoundingClientRect(); return { top: r.top, bottom: r.bottom }; });
      assert.ok(rect.top >= values.top + (values.contentTop || 0) + 11);
      assert.ok(rect.bottom <= values.height - values.bottom - 11);
      await page.getByRole('button', { name: 'Закрыть меню' }).click();
      if (values.name === 'telegram-portrait') {
        const resized = { ...values, contentTop: 60, bottom: 48 };
        await applyInsets(page, resized);
        await checkNavigation(page, resized);
      }
      await page.getByRole('button', { name: 'Назад', exact: true }).first().click();
      await page.waitForURL(`${base}/`);
      await page.getByRole('button', { name: 'Короткое знакомство →' }).click();
      await page.waitForFunction(() => document.documentElement.dataset.onboardingPhase === 'ready');
      await page.waitForFunction(({ top, bottom, left, right, contentTop = 0 }) => {
        const card = document.querySelector('.first-visit-card').getBoundingClientRect();
        return card.top >= top + contentTop + 11 && card.bottom <= innerHeight - bottom - 11 && card.left >= left + 11 && card.right <= innerWidth - right - 11;
      }, values);
      const workspace = await page.evaluate(() => {
        const p = document.querySelector('.app-content').getBoundingClientRect();
        const c = document.querySelector('.first-visit-guide').getBoundingClientRect();
        return { top: p.top, bottom: p.bottom, left: p.left, right: p.right,
          separate: p.right <= c.left || p.bottom <= c.top, height: p.height, width: p.width };
      });
      assert.ok(workspace.separate, 'Guide must not cover the page, including landscape');
      assert.ok(workspace.top >= values.top + (values.contentTop || 0) + 11);
      assert.ok(workspace.bottom <= values.height - values.bottom - 11);
      assert.ok(workspace.left >= values.left + 11);
      assert.ok(workspace.right <= values.width - values.right - 11);
      assert.ok(workspace.height >= 300);
      assert.ok(workspace.width >= 280, 'Actual page must remain wide enough to read in landscape');
      await page.screenshot({ path: `artifacts/onboarding-safe-area-${values.name}.png` });
      await page.keyboard.press('Escape');
      assert.deepEqual(errors, []);
      console.log(`${values.name}: safe header, floating navigation, menu bounds and icon back passed`);
      await context.close();
    }
    const desktop = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await desktop.route('**/api/**', route => route.fulfill({ status: 401, json: { detail: 'Guest' } }));
    await desktop.goto(`${base}/reaction-game`);
    await desktop.locator('.btn-back .back-button-arrow').first().waitFor();
    assert.equal(await desktop.locator('.mobile-primary-nav').isVisible(), false);
    assert.equal(await desktop.locator('.back-button-arrow').first().textContent(), '←');
    console.log('Desktop navigation unchanged.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
