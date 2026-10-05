// Local UI check with mocked data; no production data or accounts are changed.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.UI_BASE_URL || 'http://127.0.0.1:5174';
const names = ['Andrea Kimi Antonelli', 'Prince Birabongse Bhanudej Bhanubandh', 'Max Verstappen'];
const team = 'Visa Cash App Racing Bulls Formula One Team';
const drivers = names.map((name, index) => ({ position: index + 1, name, code: ['ANT', 'BIR', 'VER'][index], driverId: `driver_${index}`, points: 250 - index * 25, number: '12', constructorId: 'long_team', constructorName: team }));
const results = drivers.map(driver => ({ ...driver, driver: driver.code, team, best: '1:30.123', gap: '+0.100', time: '1:30:20.123', status: 'Finished', segment: 'Q3', laps: 30 }));
const races = [{ round: 14, event_name: 'Spanish Grand Prix', location: 'Madrid', country: 'Spain', date: '2026-09-13', race_start_utc: '2026-09-13T13:00:00Z', is_sprint_weekend: true }];

async function checkNames(page, selector) {
  const evidence = await page.locator(selector).evaluateAll(elements => elements.filter(element => element.getClientRects().length && element.getBoundingClientRect().width > 0).map(element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    const row = element.closest('.desktop-standings-row, .race-results-desktop-row, .standings-item, .driver-card, .constructor-card, .season-podium-list li, .index-standing-line, .index-standings-row');
    const rowRect = row?.getBoundingClientRect();
    return { text: element.textContent.trim(), whiteSpace: style.whiteSpace, ellipsis: style.textOverflow === 'ellipsis', clippedX: element.clientWidth > 0 && element.scrollWidth > element.clientWidth + 2, clippedY: element.clientHeight > 0 && element.scrollHeight > element.clientHeight + 2, outsideRow: rowRect && (rect.top < rowRect.top - 1 || rect.bottom > rowRect.bottom + 1) };
  }));
  assert.ok(evidence.length, `No visible names: ${selector}`);
  for (const item of evidence) {
    assert.equal(item.whiteSpace, 'normal', JSON.stringify(item));
    assert.equal(item.ellipsis, false, JSON.stringify(item));
    assert.equal(item.clippedX, false, JSON.stringify(item));
    assert.equal(item.clippedY, false, JSON.stringify(item));
    assert.ok(!item.outsideRow, JSON.stringify(item));
  }
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Page overflows horizontally');
  const inaccessible = await page.locator('.desktop-standings-table, .race-results-desktop-table').evaluateAll(tables => tables.filter(table => table.getClientRects().length).flatMap(table => {
    const maxScroll = table.scrollWidth - table.clientWidth;
    table.scrollLeft = maxScroll;
    const row = table.querySelector('.desktop-standings-row, .race-results-desktop-row');
    const last = row?.lastElementChild?.getBoundingClientRect();
    const bounds = table.getBoundingClientRect();
    const missed = last && last.right > bounds.right + 2;
    table.scrollLeft = 0;
    return missed ? [table.className] : [];
  }));
  assert.deepEqual(inaccessible, [], 'The last table column must remain reachable');
}

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const width of [320, 390, 768, 900, 1024, 1440, 1920]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
      await context.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'completed' })));
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route('https://telegram.org/**', route => route.abort());
      await page.route('**/api/**', route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/auth/me') return route.fulfill({ status: 401, json: { detail: 'Guest' } });
        if (['/api/pilot-portrait', '/api/team-logo', '/api/car-image'].includes(path)) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><rect width="120" height="120" fill="#343743"/></svg>' });
        const json = {
          '/api/drivers': { round: 14, drivers },
          '/api/constructors': { round: 14, constructors: [{ position: 1, name: team, constructorId: 'long_team', points: 500 }] },
          '/api/season': { races }, '/api/settings': { timezone: 'Europe/Moscow' },
          '/api/next-race': { status: 'none' },
          '/api/practice-results': { season: 2026, round: 14, session: 1, available_sessions: [1, 2, 3], results },
          '/api/compare/multi': { labels: ['Spain', 'Austria'], series: drivers.slice(0, 2).map(driver => ({ code: driver.code, history: [10, 25], race_wins: 1, quali_wins: 1, quali_samples: 2, total_points: 35, average_points: 17.5 })) },
        }[path] || (['/api/race-results', '/api/quali-results', '/api/sprint-results', '/api/sprint-quali-results'].includes(path)
          ? { season: 2026, round: 14, race_info: { event_name: 'Spanish Grand Prix' }, results }
          : { status: 'none', items: [], results: [] });
        return route.fulfill({ json });
      });
      const cases = [
        ['/drivers', width >= 900 ? '.desktop-standings-name, .drivers-row-team span' : '.driver-name'],
        ['/constructors', width >= 900 ? '.constructors-table .desktop-standings-name' : '.team-name-main'],
        ['/race-results', width >= 900 ? '.race-results-driver-cell strong, .race-results-team-cell span, .race-results-desktop-winner-team strong' : '.standings-name, .standings-code'],
        ['/quali-results', width >= 900 ? '.quali-results-table .race-results-desktop-row > span:nth-child(2)' : '.standings-name'],
        ['/sprint-results', width >= 900 ? '.race-results-driver-cell strong, .race-results-team-cell span, .race-results-desktop-winner-team strong' : '.standings-name, .results-mobile-team'],
        ['/sprint-quali-results', width >= 900 ? '.quali-results-table .race-results-desktop-row > span:nth-child(2)' : '.standings-name'],
        ['/practice-results', width >= 900 ? '.practice-unified-table .race-results-desktop-row > span:nth-child(2), .practice-unified-table .race-results-desktop-row > span:nth-child(3)' : '.standings-name, .results-mobile-team'],
        ['/compare', '.compare-table-driver strong, .compare-driver-chip-copy strong, .compare-driver-chip-copy small'],
      ];
      for (const [path, selector] of cases) {
        await page.goto(`${base}${path}${path.includes('results') ? '?mode=archive&season=2026&round=14' : ''}`);
        try { await page.locator(selector).filter({ visible: true }).first().waitFor(); }
        catch (error) { throw new Error(`${width}px ${path}: ${errors.join('; ')}\n${(await page.locator('body').innerText()).slice(0, 1400)}`, { cause: error }); }
        await checkNames(page, selector);
        if ([390, 1024].includes(width) && ['/drivers', '/race-results', '/practice-results'].includes(path)) await page.screenshot({ path: `artifacts/table-names-${path.slice(1)}-${width}.png`, fullPage: true });
      }
      await page.goto(`${base}/`);
      const homeSelector = width >= 900 ? '.index-standing-line > div > span, .index-standing-line > div > small' : '.index-standings-row > span:nth-child(2)';
      await page.locator(homeSelector).first().waitFor({ state: 'attached' });
      if (await page.locator(homeSelector).first().isVisible()) await checkNames(page, homeSelector);
      if (width >= 900) {
        await page.goto(`${base}/season?filter=past`);
        await page.getByRole('button', { name: 'Выбрать этап 14: Spanish Grand Prix', exact: true }).click();
        await page.locator('.season-podium-list li').nth(2).waitFor();
        await checkNames(page, '.season-podium-driver strong, .season-podium-driver small');
        if (width === 1440) {
          await page.waitForFunction(() => !document.getAnimations().some(animation => animation.playState === 'running'));
          await page.locator('.season-podium-content').screenshot({ path: 'artifacts/table-names-podium.png' });
        }
      }
      assert.deepEqual(errors, [], `Browser errors at ${width}px`);
      await context.close();
      console.log(`${width}px: full driver/team names in standings, session results, home and podium OK`);
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
