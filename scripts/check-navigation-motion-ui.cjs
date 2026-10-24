// Local browser check with mocked APIs; no production data is changed.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.NAVIGATION_MOTION_UI_URL || 'http://127.0.0.1:5173';

async function setup(browser, { width = 390, reduced = false, native = true } = {}) {
  const context = await browser.newContext({ viewport: { width, height: 844 }, reducedMotion: reduced ? 'reduce' : 'no-preference' });
  await context.addInitScript(({ native }) => {
    localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'completed' }));
    window.motionEvidence = { entrances: [], transitions: [], failures: [], loadingFallbacks: 0 };
    document.addEventListener('DOMContentLoaded', () => {
      new MutationObserver(() => {
        if (document.querySelector('.route-loading')) window.motionEvidence.loadingFallbacks += 1;
      }).observe(document.body, { childList: true, subtree: true });
    });
    const animate = Element.prototype.animate;
    Element.prototype.animate = function (...args) {
      if (this.classList.contains('app-page-main')) window.motionEvidence.entrances.push(args[0]);
      return animate.apply(this, args);
    };
    if (!native) document.startViewTransition = undefined;
    else if (document.startViewTransition) {
      const start = document.startViewTransition.bind(document);
      document.startViewTransition = (...args) => {
        const transition = start(...args);
        window.motionEvidence.transitions.push(true);
        transition.ready.catch(error => window.motionEvidence.failures.push(error.message));
        return transition;
      };
    }
  }, { native });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('https://telegram.org/**', route => route.abort());
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/auth/me') return route.fulfill({ status: 401, json: { detail: 'Guest' } });
    const json = {
      '/api/season': { races: [] }, '/api/settings': { timezone: 'Europe/Moscow' },
      '/api/drivers': { drivers: [] }, '/api/constructors': { constructors: [] },
      '/api/predictions/preview': { status: 'none', season: 2026, round: null, profile: { display_name: '', completed: true }, drivers: [], scoring_rules: [] },
      '/api/next-race': { status: 'none' },
      '/api/reaction-leaderboard/profile': { prompt_seen: true, participate: false, display_name: '' },
    }[path] || { status: 'none', items: [], entries: [], results: [], unread: 0 };
    return route.fulfill({ json });
  });
  return { context, page, errors };
}

async function settled(page) {
  await page.waitForFunction(() => !document.getAnimations().some(animation => animation.playState === 'running'));
}

(async () => {
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true });
  try {
    for (const values of [{ width: 320 }, { width: 390 }, { width: 820 }, { native: false }, { reduced: true }]) {
      const { context, page, errors } = await setup(browser, values);
      await page.goto(`${base}/reaction-game`);
      await page.locator('.reaction-board').waitFor();
      for (const [label, destination] of [['Прогнозы', '/predictions'], ['Уик-энд', '/next-race'], ['Мой профиль', '/account'], ['Главная', '/'], ['Wiki Formula 1™', '/wiki']]) {
        const from = new URL(page.url()).pathname;
        await page.getByRole('link', { name: 'Меню', exact: true }).filter({ visible: true }).click();
        await page.waitForURL(`${base}/menu`);
        await page.locator('.menu-page').waitFor();
        assert.equal(await page.locator('dialog, .mobile-primary-nav').count(), 0);
        assert.equal(await page.locator('.menu-page h1').evaluate(node => node === document.activeElement), true);
        await page.getByRole('navigation', { name: 'Все разделы сайта', exact: true }).getByRole('link', { name: label, exact: true }).click();
        await page.waitForURL(`${base}${destination}`);
        await settled(page);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        await page.goBack(); await page.waitForURL(`${base}/menu`);
        await page.locator('.menu-page').waitFor();
        await page.getByRole('button', { name: 'Назад из меню' }).click();
        await page.waitForURL(`${base}${from}`);
      }
      await settled(page);
      const evidence = await page.evaluate(() => window.motionEvidence);
      assert.deepEqual(evidence.failures, []);
      assert.deepEqual(evidence.transitions, [], 'Ordinary navigation does not capture document transitions');
      if (values.reduced) assert.deepEqual(evidence.entrances, []);
      else assert.ok(evidence.entrances.length > 0, 'Route content animates when motion is allowed');
      assert.deepEqual(errors, []);
      console.log(`${JSON.stringify(values)}: full-page menu, links, focus, browser Back and reduced motion passed`);
      await context.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
