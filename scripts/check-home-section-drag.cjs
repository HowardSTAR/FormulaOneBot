// Read-only checks of guest paging and the directly manipulated glass navigation.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.HOME_UI_URL || 'http://127.0.0.1:5173';
async function position(page) { return page.locator('.home-sections').evaluate(el => Number(el.style.getPropertyValue('--section-position'))); }
async function touch(session, type, x, y) { await session.send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchEnd' || type === 'touchCancel' ? [] : [{ x, y }] }); }
(async () => {
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true });
  let checks = 0;
  try {
    for (const theme of ['light', 'dark']) for (const width of [320, 390]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, hasTouch: true });
      const page = await context.newPage(); const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.route('https://telegram.org/**', r => r.abort());
      await page.goto(`${base}/tests/home-design-preview.html?theme=${theme}&spotlight=team`);
      await page.locator('.home-personalize').waitFor();
      assert.equal(await page.locator('.home-spotlight-slide').count(), 2);
      assert.equal(await page.locator('.home-spotlight-pages button').count(), 2);
      await page.waitForFunction(() => document.querySelector('.home-spotlight-pages button[aria-current]')?.getAttribute('aria-label').startsWith('2 из 2'));
      await page.getByRole('button', { name: 'Следующий слайд', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('.home-spotlight-pages button[aria-current]')?.getAttribute('aria-label').startsWith('1 из 2'));
      await page.getByRole('button', { name: 'Предыдущий слайд', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('.home-spotlight-pages button[aria-current]')?.getAttribute('aria-label').startsWith('2 из 2'));
      const nav = page.getByRole('navigation', { name: 'Разделы главной', exact: true });
      const first = await nav.getByRole('link', { name: 'Сезон', exact: true }).boundingBox();
      const second = await nav.getByRole('link', { name: 'Игры', exact: true }).boundingBox();
      const x = first.x + first.width / 2, y = first.y + first.height / 2, step = second.x - first.x;
      const session = await context.newCDPSession(page);
      await touch(session, 'touchStart', x, y);
      await touch(session, 'touchMove', x + step * .4, y);
      await page.waitForFunction(() => document.querySelector('.home-sections').hasAttribute('data-dragging'));
      assert.ok(await position(page) > .3 && await position(page) < .5, 'Lens must follow a fractional finger position');
      assert.equal(await nav.getByRole('link', { name: 'Сезон', exact: true }).getAttribute('aria-current'), 'page');
      await touch(session, 'touchMove', x + step * 2.1, y);
      await page.waitForFunction(() => Number(document.querySelector('.home-sections').style.getPropertyValue('--section-position')) > 2);
      assert.ok(await position(page) > 2 && await position(page) < 2.2);
      await touch(session, 'touchEnd');
      await page.getByRole('heading', { name: 'Справка и отзывы', exact: true }).waitFor();
      assert.equal(await position(page), 2);
      // A cancelled gesture returns to the committed page.
      await touch(session, 'touchStart', x + step * 2, y);
      await touch(session, 'touchMove', x + step, y);
      await touch(session, 'touchCancel');
      assert.equal(await position(page), 2);
      assert.equal(await nav.getByRole('link', { name: 'Справка и отзывы', exact: true }).getAttribute('aria-current'), 'page');
      // Mouse click has an actual transition; keyboard remains normal link navigation.
      await nav.getByRole('link', { name: 'Игры', exact: true }).click();
      await page.getByRole('heading', { name: 'Между гонками', exact: true }).waitFor();
      const transition = await nav.locator('.home-section-lens').evaluate(el => getComputedStyle(el).transitionDuration);
      assert.equal(transition, '0.28s');
      await nav.getByRole('link', { name: 'Сезон', exact: true }).focus(); await page.keyboard.press('Enter');
      await page.locator('.home-standing-table').waitFor();
      assert.equal(await position(page), 0);
      // Pointer capture keeps the lens responsive beyond the panel's edge.
      await touch(session, 'touchStart', x, y);
      await touch(session, 'touchMove', x + step * 4, y);
      await page.waitForFunction(() => Number(document.querySelector('.home-sections').style.getPropertyValue('--section-position')) === 3);
      await touch(session, 'touchEnd');
      await page.getByRole('heading', { name: 'Что даёт подписка', exact: true }).waitFor();
      assert.equal(await position(page), 3);
      await page.emulateMedia({ reducedMotion: 'reduce', contrast: 'more' });
      assert.equal(await nav.locator('.home-section-lens').evaluate(el => getComputedStyle(el).transitionDuration), '0s');
      assert.equal(await nav.locator('.home-section-lens').evaluate(el => getComputedStyle(el).backdropFilter), 'none');
      assert.deepEqual(errors, []);
      await session.detach(); await context.close(); checks++;
    }
    console.log(`${checks} glass-drag scenarios passed: two guest slides, stale link recovery, fractional native touch, release, cancellation, click, keyboard, reduced motion and high contrast.`);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
