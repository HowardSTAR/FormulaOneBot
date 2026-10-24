// Context-specific home destinations: navigation, content isolation, reflow and real links.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.HOME_UI_URL || 'http://127.0.0.1:5173';
const destinations = {
  games: ['Игры', 'Сделать прогноз', '/predictions'],
  guide: ['Справка и отзывы', 'Написать отзыв', '/contact-admin'],
  subscription: ['Подписка', 'Подписаться на Boosty', 'https://boosty.to/turbotears'],
};
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true }); let checks = 0;
  try {
    for (const theme of ['light', 'dark']) for (const [width, auth, scale] of [[390, 'guest', 1], [820, 'member', 1], [1440, 'guest', 1], [1440, 'member', 1], [320, 'member', 2]]) {
      const page = await browser.newPage({ viewport: { width, height: 1100 }, reducedMotion: 'reduce' });
      const errors = []; page.on('pageerror', e => errors.push(e.message));
      await page.route('https://telegram.org/**', r => r.abort());
      await page.goto(`${base}/tests/home-design-preview.html?theme=${theme}&auth=${auth}&scale=${scale}&spotlight=driver-1`);
      await page.locator('.home-standing-table').waitFor();
      for (const stage of await page.locator('.home-race, .home-favorite-card').all()) {
        const surface = await stage.evaluate(e => { const c = getComputedStyle(e); return [c.backgroundColor, c.borderTopWidth, c.borderTopLeftRadius]; });
        assert.deepEqual(surface, ['rgba(0, 0, 0, 0)', '0px', '0px']);
      }
      const nav = width >= 900 ? page.getByRole('navigation', { name: 'Главное меню', exact: true }) : page.getByRole('navigation', { name: 'Разделы главной', exact: true });
      for (const [section, [label, action, to]] of Object.entries(destinations)) {
        await nav.getByRole('link', { name: label, exact: true }).focus(); await page.keyboard.press('Enter');
        await page.locator(`.home-section-hero--${section}`).waitFor();
        assert.equal(await page.locator('.home-screen h1').innerText(), label);
        const banner = await page.locator('.home-banner-panel[data-active] .home-section-hero').evaluate(e => { const s = getComputedStyle(e); return { background: s.backgroundColor, border: s.borderTopWidth, radius: s.borderTopLeftRadius }; });
        assert.deepEqual(banner, { background: 'rgba(0, 0, 0, 0)', border: '0px', radius: '0px' });
        assert.equal(await page.locator('.home-screen h1').evaluate(e => e.getBoundingClientRect().width), 1);
        assert.equal(await page.locator('.home-banner-panel[data-active] .home-section-hero a').getAttribute('href'), to);
        assert.equal(await page.locator('.home-banner-panel[data-active] .home-section-hero a').innerText(), action);
        assert.equal(await page.locator('.home-spotlight').isVisible(), false);
        assert.equal(await page.locator('.home-weekend, .home-championship').count(), 0);
        assert.equal(await page.locator('.home-banner-panel:not([data-active]):not([inert])').count(), 0);
        assert.equal(await nav.getByRole('link', { name: label, exact: true }).getAttribute('aria-current'), 'page');
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${theme}/${width}/${section}: overflow`);
        const outside = await page.locator('.home-screen').evaluate(root => {
          const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), issues = [];
          while (walker.nextNode()) { const n = walker.currentNode, e = n.parentElement;
            if (!n.textContent.trim() || e.closest('[aria-hidden="true"],.home-sr-only') || !e.checkVisibility()) continue;
            const range = document.createRange(); range.selectNodeContents(n);
            const tile = e.closest('.home-media-tile')?.getBoundingClientRect();
            for (const r of range.getClientRects()) if (r.width && (r.left < -1 || r.right > innerWidth + 1 || tile && (r.left < tile.left - 1 || r.right > tile.right + 1))) issues.push(n.textContent);
          } return issues;
        });
        assert.deepEqual(outside, [], `${theme}/${width}/${section}`);
        if (section === 'games') {
          assert.deepEqual(await page.locator('.home-game-banner').evaluateAll(items => items.map(e => e.getAttribute('href'))), ['/reaction-game', '/reflex-grid-game', '/race-game']);
          await page.waitForFunction(() => [...document.querySelectorAll('.home-game-preview img')].every(img => img.complete && img.naturalWidth > 0));
          assert.notEqual(await page.locator('.home-game-caption').first().evaluate(e => getComputedStyle(e, '::before').backdropFilter), 'none');
          const tiles = await page.locator('.home-game-banner').evaluateAll(items => items.map(e => {
            const tile = e.getBoundingClientRect(), preview = e.querySelector('.home-game-preview').getBoundingClientRect();
            const text = e.querySelector('.home-game-caption').getBoundingClientRect();
            return { x: tile.x, y: tile.y, width: tile.width, height: tile.height, fullBackground: preview.left <= tile.left + 1 && preview.right >= tile.right - 1 && preview.top <= tile.top + 1 && preview.bottom >= tile.bottom - 1, textInside: text.top >= tile.top + 79 && text.bottom <= tile.bottom + 1 };
          }));
          assert.ok(tiles.every(t => t.fullBackground && t.textInside), JSON.stringify(tiles));
          if (width < 700 && scale === 1) { assert.ok(tiles[0].width > tiles[1].width * 1.5); assert.equal(tiles[1].y, tiles[2].y); }
          else if (width < 700) { assert.equal(tiles[1].width, tiles[2].width); assert.ok(tiles[2].y >= tiles[1].y + tiles[1].height); }
          else { assert.ok(tiles[0].height > tiles[1].height); assert.ok(tiles[1].x > tiles[0].x); }
          // The darkest possible source is harmless; even white beneath the 78% scrim passes.
          const contrast = await page.locator('.home-game-caption small').first().evaluate(e => {
            const ink = getComputedStyle(e).color.match(/[\d.]+/g).slice(0, 3).map(Number);
            const bg = [9, 14, 19].map(v => v * .78 + 255 * .22);
            const lum = values => values.map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((s, v, i) => s + v * [.2126, .7152, .0722][i], 0);
            return (lum(ink) + .05) / (lum(bg) + .05);
          });
          assert.ok(contrast >= 4.5, `Game description contrast: ${contrast}`);
          await page.emulateMedia({ contrast: 'more' });
          assert.equal(await page.locator('.home-game-caption').first().evaluate(e => getComputedStyle(e, '::before').display), 'none');
          await page.emulateMedia({ contrast: 'no-preference' });
        } else if (section === 'guide') {
          assert.deepEqual(await page.locator('.home-guide-link').evaluateAll(items => items.map(e => e.getAttribute('href'))), ['/history', '/wiki', '/wiki?term=race-weekend']);
          assert.equal(await page.getByRole('link', { name: 'Написать отзыв', exact: true }).count(), 1);
        } else {
          assert.equal(await page.locator('.home-banner-panel[data-active] .home-section-hero a').getAttribute('rel'), 'noopener noreferrer');
          assert.deepEqual(await page.locator('.home-membership-levels h3').allTextContents(), ['На старт', 'Свой стиль', 'Полный газ']);
          assert.doesNotMatch(await page.locator('.home-membership').innerText(), /виджет|live activity|телеметри/i);
        }
        const tiles = page.locator('.home-media-tile');
        assert.equal(await tiles.count(), 3);
        for (const tile of await tiles.all()) {
          assert.equal(await tile.locator('.home-media-preview[aria-hidden="true"]').count(), 1);
          const inside = await tile.evaluate(e => {
            const tile = e.getBoundingClientRect(), caption = e.querySelector('.home-media-caption').getBoundingClientRect();
            return caption.top >= tile.top + 79 && caption.bottom <= tile.bottom + 1;
          });
          assert.equal(inside, true);
        }
        if (section === 'guide') {
          for (const link of await tiles.all()) { await link.focus(); assert.equal(await link.evaluate(e => getComputedStyle(e).outlineStyle), 'solid'); }
        }
        if (section === 'subscription') {
          assert.equal(await tiles.locator('a,button,[tabindex]').count(), 0);
          assert.equal(await page.locator('.home-membership-preview--club .supporter-badge').count(), 1);
          assert.equal(await page.locator('.home-preview-avatar').count(), 4);
        }
        await page.emulateMedia({ contrast: 'more' });
        assert.equal(await page.locator('.home-media-caption').first().evaluate(e => getComputedStyle(e, '::before').display), 'none');
        await page.emulateMedia({ contrast: 'no-preference' });
        checks++;
      }
      await nav.getByRole('link', { name: 'Сезон', exact: true }).click();
      await page.locator('.home-standing-table').waitFor();
      assert.match(await page.locator('.home-spotlight-pages [aria-current]').getAttribute('aria-label'), /^2 из /);
      if (width >= 1200 && auth === 'member') {
        assert.equal(await page.locator('.home-favorite-card .home-glass-button').count(), 0);
        const gap = await page.evaluate(() => document.querySelector('.home-championship').getBoundingClientRect().top - document.querySelector('.home-weekend').getBoundingClientRect().bottom);
        assert.ok(gap >= 16 && gap <= 32, `Schedule/standings gap: ${gap}`);
        for (const name of await page.locator('.home-favorite-name').all()) {
          const box = await name.boundingBox(); assert.ok(box.height >= 44, `Name target: ${box.height}`);
        }
      }
      assert.deepEqual(errors, []); await page.close();
    }
    console.log(`${checks} section banner scenarios passed: context-specific heroes, real destinations, no hidden season cards, game imagery, subscription levels, keyboard, remembered favorite, 320–1440 reflow and 200% text.`);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
