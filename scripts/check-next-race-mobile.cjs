// Layout regression using the real circuit SVG and mocked schedule, no backend writes.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const miniApp of [false, true]) {
      const page = await browser.newPage({ reducedMotion: 'reduce' });
      await page.route('**/static/circuit/**', route => route.fulfill({
        path: 'front/public/static/circuit/Spanish Grand Prix.svg', contentType: 'image/svg+xml',
      }));
      if (miniApp) await page.addInitScript(() => {
        window.Telegram = { WebApp: { initData: 'layout-test', ready() {}, expand() {}, onEvent() {}, offEvent() {}, setHeaderColor() {}, setBackgroundColor() {} } };
      });
      await page.route('**/api/**', route => {
        const path = new URL(route.request().url()).pathname;
        const data = path === '/api/next-race' ? { status: 'ok', event_name: 'Spanish Grand Prix', season: 2026, round: 16, country: 'Spain', location: 'Madrid' }
          : path === '/api/weekend-schedule' ? { sessions: [{ name: 'Гонка', utc_iso: '2026-09-13T13:00:00Z' }] }
          : { timezone: 'Europe/Moscow' };
        return route.fulfill({ json: data });
      });
      for (const width of [320, 390, 430, 768]) {
        await page.setViewportSize({ width, height: 900 });
        await page.goto('http://127.0.0.1:5173/next-race');
        await page.locator('.next-race-hero.split').waitFor();
        await page.locator('.next-race-mobile-track-svg svg').waitFor();
        await page.locator('.next-race-hero').evaluate(async el => {
          await Promise.all(el.getAnimations({ subtree: true }).filter(a => a.effect.getTiming().iterations !== Infinity).map(a => a.finished));
        });
        const sizes = await page.evaluate(() => {
          const date = document.querySelector('.next-race-hero .next-race-date');
          const hero = document.querySelector('.next-race-hero').getBoundingClientRect();
          const d = date.getBoundingClientRect();
          const map = document.querySelector('.next-race-track-wrap').getBoundingClientRect();
          return { fits: date.scrollWidth <= date.clientWidth && d.left >= hero.left && d.right <= hero.right,
            mapWidth: map.width, heroWidth: hero.width, below: map.top >= d.bottom,
            overflow: document.documentElement.scrollWidth > innerWidth };
        });
        assert.ok(sizes.fits && sizes.below && !sizes.overflow, JSON.stringify({ width, miniApp, ...sizes }));
        assert.ok(sizes.mapWidth >= sizes.heroWidth - 42);
        if (width === 390 && !miniApp) await page.locator('.next-race-hero').screenshot({ path: 'artifacts/next-race-mobile-fixed.png' });
      }
      await page.close();
    }
    console.log('Date and full-width track fit at 320/390/430/768px, browser and simulated Mini App.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
