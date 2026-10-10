// Local browser check with mocked APIs; no production data is changed.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.NAVIGATION_MOTION_UI_URL || 'http://127.0.0.1:5174';

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

async function checkIndicator(page, index) {
  await page.waitForFunction(index => {
    const nav = document.querySelector('.mobile-primary-nav');
    const indicator = nav.querySelector('.mobile-nav-indicator').getBoundingClientRect();
    const target = nav.querySelectorAll('a, button')[index].getBoundingClientRect();
    return Math.abs(indicator.left - target.left) < 1.5;
  }, index);
  await settled(page);
  const metrics = await page.evaluate(index => {
    const nav = document.querySelector('.mobile-primary-nav');
    const indicator = nav.querySelector('.mobile-nav-indicator').getBoundingClientRect();
    const target = nav.querySelectorAll('a, button')[index].getBoundingClientRect();
    return { offset: Math.abs(indicator.left - target.left), width: Math.abs(indicator.width - target.width), active: nav.querySelectorAll('.active').length, overflow: document.documentElement.scrollWidth > innerWidth };
  }, index);
  assert.ok(metrics.offset < 1.5, JSON.stringify(metrics));
  assert.ok(metrics.width < 1.5, JSON.stringify(metrics));
  assert.equal(metrics.active, 1);
  assert.equal(metrics.overflow, false);
}

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const values of [{ width: 320 }, { width: 390 }, { width: 740 }, { native: false }, { reduced: true }]) {
      const { context, page, errors } = await setup(browser, values);
      // Exercise a first visit to a lazy page with a deliberately delayed module.
      await page.route(/\/src\/pages\/predictions\/PredictionsPage\.tsx/, async route => {
        await new Promise(resolve => setTimeout(resolve, 250));
        await route.continue();
      });
      await page.goto(`${base}/reaction-game`);
      await page.locator('.reaction-board').waitFor();
      assert.equal(await page.locator('.app-page-main .btn-back').count(), 0);
      await checkIndicator(page, 4);
      const nav = page.getByRole('navigation', { name: 'Основная навигация', exact: true });
      await page.evaluate(() => { window.motionEvidence.loadingFallbacks = 0; });
      await nav.getByRole('link', { name: 'Прогнозы', exact: true }).click();
      await page.waitForURL('**/predictions');
      await page.locator('.predictions-page').waitFor();
      await checkIndicator(page, 2);
      assert.equal(await page.evaluate(() => window.motionEvidence.loadingFallbacks), 0, 'A slow lazy route must retain the outgoing page');
      for (const [label, path, index] of [['Уик-энд', '/next-race', 1], ['Мой профиль', '/account', 3], ['Главная', '/', 0]]) {
        await nav.getByRole('link', { name: label, exact: true }).click();
        await page.waitForURL(`${base}${path}`);
        await checkIndicator(page, index);
        assert.equal(await page.locator('.app-page-main .btn-back').count(), 0, `No back button on ${path}`);
      }
      // Rapid taps must settle on the last selected page and indicator.
      await nav.getByRole('link', { name: 'Прогнозы', exact: true }).click();
      await nav.getByRole('link', { name: 'Мой профиль', exact: true }).click();
      await nav.getByRole('link', { name: 'Уик-энд', exact: true }).click();
      await page.waitForURL('**/next-race');
      await checkIndicator(page, 1);
      if (values.width === 390) await nav.screenshot({ path: 'artifacts/navigation-motion-indicator.png' });

      const menuButton = nav.getByRole('button', { name: 'Меню', exact: true });
      const dialog = page.locator('.mobile-menu-dialog');
      await menuButton.click();
      await dialog.waitFor();
      assert.equal(await menuButton.getAttribute('aria-expanded'), 'true');
      if (!values.reduced) assert.equal(await dialog.evaluate(node => getComputedStyle(node).animationName), 'mobile-menu-in');
      await checkIndicator(page, 4);
      if (values.width === 390) await page.screenshot({ path: 'artifacts/navigation-motion-menu.png' });
      await page.getByRole('button', { name: 'Закрыть меню' }).click();
      if (!values.reduced) assert.equal(await dialog.getAttribute('data-phase'), 'closing');
      await dialog.waitFor({ state: 'hidden' });
      await page.waitForFunction(() => document.querySelector('[aria-controls="mobile-full-menu"]').getAttribute('aria-expanded') === 'false');
      assert.equal(await menuButton.getAttribute('aria-expanded'), 'false');
      assert.equal(await menuButton.evaluate(node => node === document.activeElement), true);
      await checkIndicator(page, 1);
      await menuButton.click(); await dialog.waitFor(); await page.keyboard.press('Escape');
      await dialog.waitFor({ state: 'hidden' });
      await menuButton.click(); await dialog.waitFor();
      await page.getByRole('navigation', { name: 'Все разделы сайта', exact: true }).getByRole('link', { name: 'Wiki Formula 1™', exact: true }).click();
      await page.waitForURL('**/wiki');
      await dialog.waitFor({ state: 'hidden' });
      await settled(page);
      assert.equal(await page.locator('.app-page-main .btn-back').count(), 0, 'Menu sections have no back button');
      await page.goBack();
      await page.waitForURL('**/next-race');
      await checkIndicator(page, 1);
      const evidence = await page.evaluate(() => window.motionEvidence);
      assert.deepEqual(evidence.failures, []);
      if (values.reduced) {
        assert.deepEqual(evidence.entrances, []);
        assert.equal(await page.locator('.mobile-nav-indicator').evaluate(node => getComputedStyle(node).transitionDuration), '0s');
        assert.equal(await dialog.evaluate(node => getComputedStyle(node).animationName), 'none');
      } else assert.ok(evidence.entrances.length >= 5, 'Page content must animate while the navigation remains live');
      assert.deepEqual(evidence.transitions, [], 'Bottom navigation must not capture a document view transition');
      assert.deepEqual(errors, []);
      console.log(`${JSON.stringify(values)}: indicator, lazy route, fast taps, menu close/Escape/link, focus and back passed`);
      await context.close();
    }

    const { context, page, errors } = await setup(browser, { width: 1440, native: false });
    await page.goto(`${base}/privacy`);
    await page.locator('.legal-page').waitFor();
    await page.getByRole('link', { name: 'Условия использования', exact: true }).click();
    await page.waitForURL('**/terms');
    await settled(page);
    assert.equal(await page.locator('.mobile-primary-nav').isVisible(), false);
    assert.ok(await page.evaluate(() => window.motionEvidence.entrances.length > 0));
    assert.deepEqual(errors, []);
    await context.close();
    console.log('Desktop: ordinary page links animate; mobile navigation stays hidden.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
