// Read-only coverage of the desktop overview and the standings glass switch.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.HOME_UI_URL || 'http://127.0.0.1:5173';
async function touch(session, type, x, y) { await session.send('Input.dispatchTouchEvent', { type, touchPoints: ['touchEnd', 'touchCancel'].includes(type) ? [] : [{ x, y }] }); }
async function verify(page, wide, count) {
  await page.waitForFunction(({ wide, count }) => document.querySelectorAll('.home-spotlight-slide:not([inert])').length === (wide ? count : 1), { wide, count });
  const geometry = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('.home-spotlight-slide')];
    const r = element => { const { x, y, width, height } = element.getBoundingClientRect(); return { x, y, width, height }; };
    return { overflow: document.documentElement.scrollWidth > innerWidth,
      cards: cards.map(r), interactive: cards.filter(e => !e.inert).length,
      controls: document.querySelector('.home-spotlight-controls').checkVisibility(),
      navigation: document.querySelector('.home-sections').checkVisibility(),
      championship: r(document.querySelector('.home-championship')),
      personal: document.querySelector('.personal-home') ? r(document.querySelector('.home-personal-column')) : null,
      track: document.querySelector('.home-spotlight-slide .home-circuit-svg .track-outline-group') ? r(document.querySelector('.home-spotlight-slide .home-circuit-svg .track-outline-group')) : null,
      map: r(document.querySelector('.home-spotlight-slide .home-circuit-map')),
      car: document.querySelector('.home-spotlight-slide .home-team-car') ? r(document.querySelector('.home-spotlight-slide .home-team-car')) : null,
      summary: r(document.querySelector('.home-schedule > summary')),
      weekend: r(document.querySelector('.home-weekend')) };
  });
  assert.equal(geometry.overflow, false, JSON.stringify(geometry));
  // A decorative pseudo-element must never become an extra table column.
  const standings = await page.locator('.home-standing-table').evaluate(table => {
    const cells = row => [...row.children].filter(cell => getComputedStyle(cell).display !== 'none').map(cell => {
      const { x, width } = cell.getBoundingClientRect(); return { x, width };
    });
    return { headers: cells(table.tHead.rows[0]), rows: [...table.tBodies[0].rows].map(cells) };
  });
  for (const row of standings.rows) {
    assert.equal(row.length, standings.headers.length);
    row.forEach((cell, index) => {
      const header = standings.headers[index];
      assert.ok(Math.abs(cell.x - header.x) < 1 && Math.abs(cell.width - header.width) < 1, JSON.stringify(standings));
    });
  }
  assert.equal(geometry.cards.length, count);
  assert.equal(geometry.interactive, wide ? count : 1);
  assert.equal(geometry.controls, !wide);
  assert.equal(geometry.navigation, page.viewportSize().width < 900);
  if (wide) {
    const [race, ...favorites] = geometry.cards;
    assert.ok(favorites.every(card => card.x >= race.x + race.width), JSON.stringify(geometry));
    assert.ok(geometry.weekend.x < favorites[0].x);
    assert.ok(geometry.championship.y >= race.y + race.height);
    if (geometry.personal) {
      assert.ok(geometry.personal.x >= geometry.championship.x + geometry.championship.width, JSON.stringify(geometry));
      assert.ok(geometry.personal.y >= favorites[2].y + favorites[2].height + 16, JSON.stringify(geometry));
      assert.equal(await page.locator('.personal-home details').count(), 0);
      assert.equal(await page.locator('.personal-destinations a[href="/account"]').count(), 0);
      assert.equal(await page.locator('.personal-destinations a[href="/predictions"]').count(), 1);
    }
    if (geometry.track) {
      assert.ok(geometry.track.y >= geometry.map.y - 1 && geometry.track.y + geometry.track.height <= geometry.map.y + geometry.map.height + 1, JSON.stringify(geometry));
      assert.ok(geometry.track.y + geometry.track.height < geometry.weekend.y, JSON.stringify(geometry));
    }
    assert.ok(geometry.weekend.height <= 88, JSON.stringify(geometry));
    if (count === 4) {
      assert.ok(favorites[1].y >= favorites[0].y + favorites[0].height);
      if (geometry.car?.height) assert.ok(Math.abs(geometry.car.y + geometry.car.height / 2 - geometry.cards[3].y - geometry.cards[3].height / 2) <= 1, JSON.stringify(geometry));
    }
  }
}
(async () => {
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true }); let checks = 0;
  try {
    for (const theme of ['light', 'dark']) for (const width of [390, 1200, 1440, 1920, 2560]) {
      const context = await browser.newContext({ viewport: { width, height: 1100 }, hasTouch: true });
      const page = await context.newPage(); const errors = []; page.on('pageerror', e => errors.push(e.message));
      await page.route('https://telegram.org/**', r => r.abort()); await page.route('https://media.formula1.com/**', r => r.abort());
      await page.goto(`${base}/tests/home-design-preview.html?theme=${theme}&auth=member&spotlight=driver-2`);
      await page.locator('.home-standing-table').waitFor(); await page.waitForFunction(() => document.querySelectorAll('.home-spotlight-slide').length === 4);
      await page.locator('.home-spotlight-slide .home-circuit-svg .track-outline-group').waitFor({ state: 'attached' });
      await verify(page, width >= 1200, 4);
      assert.equal(await page.locator('.personal-home-refresh').count(), 0);
      if (width >= 1200) {
        const team = page.locator('.home-spotlight-slide .home-favorite-card--team');
        const car = page.locator('.home-spotlight-slide .home-team-car');
        const beforeTeam = await team.boundingBox(), beforeCar = await car.boundingBox();
        const position = () => page.evaluate(() => { const y = s => document.querySelector(s).getBoundingClientRect().top + scrollY; return { personal: y('.home-personal-column'), championship: y('.home-championship') }; });
        const before = await position();
        const summary = page.locator('.home-schedule > summary');
        await summary.focus(); await page.keyboard.press('Enter');
        await page.waitForFunction(() => document.querySelector('.home-schedule').open);
        assert.equal((await team.boundingBox()).height, beforeTeam.height, 'Expanding the schedule must not stretch the team poster');
        assert.equal((await car.boundingBox()).height, beforeCar.height);
        const after = await position();
        assert.ok(Math.abs(after.personal - before.personal) < 1, 'Personal destinations must stay in place');
        assert.ok(after.championship > before.championship + 100, 'Only the championship follows the expanded schedule');
        await page.keyboard.press('Enter');
      }
      const nav = page.getByRole('navigation', { name: 'Выбрать зачёт', exact: true });
      await nav.getByRole('link', { name: 'Команды', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('.home-standing-table tbody .home-entrant strong')?.textContent === 'McLaren');
      assert.equal(await nav.evaluate(e => Number(e.style.getPropertyValue('--section-position'))), 1);
      assert.match(await nav.getByRole('link', { name: 'Команды', exact: true }).getAttribute('href'), /spotlight=driver-2/);
      await nav.scrollIntoViewIfNeeded();
      const first = await nav.getByRole('link', { name: 'Пилоты', exact: true }).boundingBox(), second = await nav.getByRole('link', { name: 'Команды', exact: true }).boundingBox();
      const x = second.x + second.width / 2, y = second.y + second.height / 2, step = second.x - first.x;
      const session = await context.newCDPSession(page);
      await touch(session, 'touchStart', x, y); await touch(session, 'touchMove', x - step * .4, y);
      await page.waitForFunction(() => { const n = document.querySelector('.home-standing-switch'); const p = Number(n.style.getPropertyValue('--section-position')); return n.hasAttribute('data-dragging') && p > .5 && p < .7; });
      assert.equal(await nav.getByRole('link', { name: 'Команды', exact: true }).getAttribute('aria-current'), 'page');
      await touch(session, 'touchMove', x - step, y); await touch(session, 'touchEnd');
      await page.waitForFunction(() => document.querySelector('.home-standing-table tbody .home-entrant strong')?.textContent.includes('Норрис'));
      await nav.getByRole('link', { name: 'Команды', exact: true }).focus(); await page.keyboard.press('Enter');
      await page.waitForFunction(() => document.querySelector('.home-standing-table tbody .home-entrant strong')?.textContent === 'McLaren');
      await page.emulateMedia({ reducedMotion: 'reduce', contrast: 'more' });
      assert.equal(await nav.locator('.home-section-lens').evaluate(e => getComputedStyle(e).backdropFilter), 'none');
      assert.equal(await nav.locator('.home-section-lens').evaluate(e => getComputedStyle(e).transitionDuration), '0s');
      if (width === 1440) {
        for (const size of [1199, 1200, 390]) { await page.setViewportSize({ width: size, height: 1100 }); await verify(page, size >= 1200, 4); }
        assert.match(await page.locator('.home-spotlight-pages button[aria-current]').getAttribute('aria-label'), /^3 из 4:/);
      }
      assert.deepEqual(errors, []); await session.detach(); await context.close(); checks++;
    }
    for (const [width, extra, count] of [[1440, '', 2], [320, '&auth=member&scale=2', 4]]) {
      const page = await browser.newPage({ viewport: { width, height: 1100 }, reducedMotion: 'reduce' });
      await page.goto(`${base}/tests/home-design-preview.html?theme=light${extra}`); await page.locator('.home-standing-table').waitFor(); await verify(page, width >= 1200, count);
      await page.getByRole('navigation', { name: 'Выбрать зачёт', exact: true }).getByRole('link', { name: 'Команды', exact: true }).click();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.close(); checks++;
    }
    console.log(`${checks} desktop/standings scenarios passed: simultaneous favorites and race, guest layout, native glass drag, links/keyboard, URL state, 1199/1200 resize, 200% text and contrast settings.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
