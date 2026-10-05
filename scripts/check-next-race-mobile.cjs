// Layout regression using the real circuit SVG and mocked schedule, no backend writes.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.NEXT_RACE_UI_URL || 'http://127.0.0.1:5173';
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
        await page.goto(`${base}/next-race`);
        await page.locator('.next-race-hero.split').waitFor();
        await page.locator('.circuit-map-launcher .next-race-mobile-track-svg svg').waitFor();
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
    for (const width of [320, 390, 768, 1440]) {
      const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'no-preference' });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('https://telegram.org/**', route => route.abort());
      await page.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'completed' })));
      await page.route('**/static/circuit/**', async route => {
        await new Promise(resolve => setTimeout(resolve, 250));
        await route.fulfill({ path: 'front/public/static/circuit/Singapore Grand Prix.svg', contentType: 'image/svg+xml' });
      });
      await page.route('**/api/**', route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/auth/me') return route.fulfill({ status: 401, json: { detail: 'Guest' } });
        return route.fulfill({ json: path === '/api/next-race'
          ? { status: 'ok', event_name: 'Singapore Grand Prix', season: 2026, round: 18, country: 'Singapore', location: 'Marina Bay' }
          : path === '/api/weekend-schedule' ? { sessions: [{ name: 'Гонка', utc_iso: '2026-10-11T12:00:00Z' }] }
          : { timezone: 'Europe/Moscow', drivers: [], constructors: [], races: [], unread: 0 } });
      });
      await page.goto(`${base}/next-race`);
      const map = page.locator(`${width < 900 ? '.next-race-mobile' : '.next-race-desktop'} .circuit-map-launcher .animated-track-svg`);
      const stroke = map.locator('.track-route-border');
      await stroke.waitFor();
      const beginning = await stroke.evaluate(path => ({ offset: parseFloat(getComputedStyle(path).strokeDashoffset), drawing: path.classList.contains('track-drawing') }));
      assert.ok(beginning.drawing && beginning.offset > 0, JSON.stringify({ width, beginning }));
      await stroke.evaluate(path => Promise.all(path.getAnimations().map(animation => animation.finished)));
      await page.waitForFunction(selector => document.querySelector(selector).classList.contains('animation-complete'), `${width < 900 ? '.next-race-mobile' : '.next-race-desktop'} .circuit-map-launcher .track-route-border`);
      assert.equal(await stroke.evaluate(path => parseFloat(getComputedStyle(path).strokeDashoffset)), 0);
      assert.equal(await stroke.evaluate(path => path.getAnimations().length), 0, 'Completed maps must not keep animating');
      if (width < 900) {
        await page.locator('.next-race-hero.split').waitFor();
        const frames = await page.locator('.next-race-hero').evaluate(async hero => {
          const frames = []; const start = performance.now();
          do {
            const map = hero.querySelector('.next-race-track-wrap').getBoundingClientRect();
            const heading = document.querySelector('.next-race-mobile > h3').getBoundingClientRect();
            frames.push({ height: hero.getBoundingClientRect().height, time: performance.now(), contained: map.bottom <= hero.getBoundingClientRect().bottom && heading.top >= hero.getBoundingClientRect().bottom, overflow: document.documentElement.scrollWidth > innerWidth });
            await new Promise(requestAnimationFrame);
          } while (performance.now() - start < 700);
          return frames;
        });
        assert.ok(frames.every(frame => frame.contained && !frame.overflow));
        assert.ok(frames.at(-1).height - frames[0].height > 50, 'Date must reveal by changing height gradually');
        assert.ok(new Set(frames.map(frame => Math.round(frame.height))).size > 5, 'Date reveal needs intermediate heights');
        for (let i = 1; i < frames.length; i++) if (frames[i].time - frames[i - 1].time < 50) assert.ok(Math.abs(frames[i].height - frames[i - 1].height) < 40, 'Hero height jumped in one frame');
        assert.equal(await page.locator('.next-race-date').textContent(), '11 ОКТЯБРЯ');
        if (width === 390) await page.locator('.next-race-hero').screenshot({ path: 'artifacts/next-race-reveal-final.png' });
      } else assert.equal(await page.locator('.next-race-desktop-start').evaluate(node => getComputedStyle(node).animationName), 'next-race-date-appear');
      assert.deepEqual(errors, []);
      await page.close();
      console.log(`${width}px: finite track drawing and smooth date reveal passed`);
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
