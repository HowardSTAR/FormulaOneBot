// The shared stage must stay the same size throughout section and carousel navigation.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.HOME_UI_URL || 'http://127.0.0.1:5173';
const views = { season: 'Сезон', games: 'Игры', guide: 'Справка и отзывы', subscription: 'Подписка' };
async function geometry(page) {
  return page.evaluate(() => {
    const stage = document.querySelector('.home-banner-stage').getBoundingClientRect();
    const nav = document.querySelector('.home-sections').getBoundingClientRect();
    return { height: stage.height, nav: nav.height ? nav.top + scrollY : 0,
      panels: [...document.querySelectorAll('.home-banner-panel')].map(e => e.getBoundingClientRect().height),
      inactive: document.querySelectorAll('.home-banner-panel:not([data-active])[inert][aria-hidden="true"]').length,
      overflow: document.documentElement.scrollWidth > innerWidth };
  });
}
async function frames(page) {
  return page.evaluate(() => new Promise(resolve => {
    const values = []; const tick = () => { values.push(document.querySelector('.home-banner-stage').getBoundingClientRect().height); if (values.length < 12) requestAnimationFrame(tick); else resolve(values); }; requestAnimationFrame(tick);
  }));
}
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true }); let checks = 0;
  try {
    for (const theme of ['light', 'dark']) for (const [width, auth, scale] of [[320, 'guest', 1], [390, 'member', 1], [820, 'member', 1], [1024, 'member', 1], [320, 'member', 2], [390, 'guest', 2]]) {
      const page = await browser.newPage({ viewport: { width, height: 1600 }, reducedMotion: 'reduce' });
      await page.route('https://telegram.org/**', r => r.abort()); await page.route('https://media.formula1.com/**', r => r.abort());
      await page.goto(`${base}/tests/home-design-preview.html?theme=${theme}&auth=${auth}&scale=${scale}&spotlight=driver-1`);
      await page.locator('.home-standing-table').waitFor();
      await page.waitForFunction(() => !document.querySelector('.home-favorite-card')?.textContent.includes('Загружаем'));
      const initial = await geometry(page);
      const nav = page.getByRole('navigation', { name: width < 900 ? 'Разделы главной' : 'Главное меню', exact: true });
      for (const view of ['games', 'guide', 'subscription', 'season', 'subscription', 'games', 'season']) {
        const [samples] = await Promise.all([frames(page), nav.getByRole('link', { name: views[view], exact: true }).click()]);
        await page.waitForFunction(view => document.querySelector('.home-screen').dataset.section === view, view);
        const next = await geometry(page);
        assert.ok(samples.every(h => Math.abs(h - initial.height) <= 1), `${theme}/${width}/${view}: ${samples}`);
        assert.ok(Math.abs(next.height - initial.height) <= 1 && Math.abs(next.nav - initial.nav) <= 1, JSON.stringify({ initial, next }));
        assert.ok(next.panels.every(h => Math.abs(h - initial.height) <= 1));
        assert.equal(next.inactive, 3); assert.equal(next.overflow, false);
        const clipped = await page.locator('.home-banner-panel[data-active]').evaluate(root => {
          const stage = root.getBoundingClientRect(), issues = [], walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
          while (walker.nextNode()) { const n = walker.currentNode, el = n.parentElement;
            if (!n.textContent.trim() || el.closest('[inert],[aria-hidden="true"],.home-sr-only') || !el.checkVisibility()) continue;
            const r = document.createRange(); r.selectNodeContents(n);
            for (const box of r.getClientRects()) if (box.top < stage.top - 1 || box.bottom > stage.bottom + 1) issues.push(n.textContent);
          } return issues;
        });
        assert.deepEqual(clipped, []);
      }
      const count = auth === 'member' ? 4 : 2;
      for (let i = 0; i < count; i++) {
        await page.getByRole('button', { name: 'Следующий слайд', exact: true }).click();
        assert.ok(Math.abs((await geometry(page)).height - initial.height) <= 1);
      }
      await page.setViewportSize({ width: width === 390 ? 820 : 390, height: 1600 });
      const resized = await geometry(page);
      const resizedNav = page.getByRole('navigation', { name: page.viewportSize().width < 900 ? 'Разделы главной' : 'Главное меню', exact: true });
      await resizedNav.getByRole('link', { name: 'Игры', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('.home-screen').dataset.section === 'games');
      assert.ok(Math.abs((await geometry(page)).height - resized.height) <= 1);
      await page.close(); checks++;
    }
    console.log(`${checks} banner stability scenarios passed: every animation frame across four sections, carousel slides, guest/member, 320–1024 widths, 200% text, equal panels, inert hidden actions, no clipped text and resize.`);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
