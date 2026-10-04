const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const routes = ['/', '/season', '/race-results', '/drivers', '/compare', '/predictions', '/community', '/wiki', '/reaction-game', '/account', '/contact-admin'];
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, timezoneId: 'Europe/Moscow' });
    const response = await context.request.get('https://www.f1hub.ru/api/race-results?season=2026', { timeout: 90000 });
    assert.equal(response.status(), 200);
    const result = await response.json();
    assert.equal(result.round, 16);
    assert.equal(result.data_incomplete, false);
    assert.equal(result.results.length, 22);
    assert.equal(result.results[0].code, 'VER');
    assert.equal(result.results[0].points, 25);
    console.log(JSON.stringify({ round: result.round, drivers: result.results.length, winner: result.results[0].name, points: result.results[0].points, complete: !result.data_incomplete }));
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('https://www.f1hub.ru/', { waitUntil: 'domcontentloaded', timeout: 60000 });
    const guide = page.locator('.first-visit-guide');
    await guide.waitFor({ timeout: 60000 });
    for (const [index, route] of routes.entries()) {
      await page.waitForFunction(route => location.pathname === route, route);
      await page.locator(`.first-visit-highlight[data-tour-route="${route}"]`).waitFor({ timeout: 45000 });
      await page.waitForFunction(() => document.documentElement.dataset.onboardingPhase === 'ready');
      const layout = await page.evaluate(() => {
        const page = document.querySelector('.app-content').getBoundingClientRect();
        const card = document.querySelector('.first-visit-guide').getBoundingClientRect();
        const target = document.querySelector('.first-visit-highlight').getBoundingClientRect();
        return { separate: page.bottom <= card.top || page.right <= card.left,
          visible: target.top < page.bottom && target.bottom > page.top,
          opacity: getComputedStyle(document.querySelector('.app-page-main')).opacity,
          height: page.height };
      });
      assert.ok(layout.separate);
      assert.ok(layout.visible);
      assert.ok(layout.height >= 320);
      assert.equal(layout.opacity, '1');
      if ([1, 2].includes(index)) {
        const heading = page.locator('.app-page-main h1:visible, .app-page-main h2:visible').first();
        assert.ok(await heading.evaluate(node => {
          const h = node.getBoundingClientRect(), p = document.querySelector('.app-content').getBoundingClientRect();
          return h.top >= p.top && h.bottom <= p.bottom;
        }));
      }
      assert.ok((await guide.innerText()).includes(`${index + 1} / 11`));
      if (index === 2) await page.screenshot({ path: 'artifacts/section-tour-production-mobile.png' });
      await guide.getByRole('button', { name: index === 10 ? 'На главную →' : 'Дальше →', exact: true }).click();
    }
    await guide.waitFor({ state: 'hidden' });
    assert.equal(await page.evaluate(() => location.pathname), '/');
    assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('turbotears-onboarding-v2')).status), 'completed');
    await page.goto('https://www.f1hub.ru/race-results');
    await page.getByText('Max Verstappen', { exact: true }).first().waitFor({ timeout: 60000 });
    await page.screenshot({ path: 'artifacts/race-results-production-mobile.png', fullPage: true });
    assert.deepEqual(errors, []);
    console.log('Production: all 11 sections readable, highlighted and separate from the guide; published race visible; no runtime errors.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
