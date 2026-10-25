// Local UI regression check with mocked APIs; no production data is changed.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.UI_BASE_URL || 'http://127.0.0.1:5173';
const races = [
  { round: 17, event_name: 'Azerbaijan Grand Prix', location: 'Baku', country: 'Azerbaijan', date: '2026-09-27', race_start_utc: '2026-09-27T11:00:00Z' },
  { round: 18, event_name: 'United States Grand Prix', location: 'Austin', country: 'United States', date: '2026-10-25', race_start_utc: '2026-10-25T19:00:00Z' },
  { round: 19, event_name: 'Mexico City Grand Prix', location: 'Mexico City', country: 'Mexico', date: '2026-11-01', race_start_utc: '2026-11-01T19:00:00Z' },
  { round: 20, event_name: 'A deliberately long cancelled Grand Prix name for narrow screens', location: 'Long circuit location', country: '', date: '2026-11-08', is_cancelled: true },
];
const driver = { position: 1, name: 'Max Verstappen', driverId: 'max_verstappen', code: 'VER', number: '3', points: 250, constructorId: 'red_bull', constructorName: 'Red Bull' };
const stats = { position: 1, points: 250, grand_prix_races: 17, grand_prix_points: 250, grand_prix_wins: 5, grand_prix_podiums: 10, grand_prix_poles: 5, grand_prix_top10s: 16, fastest_laps: 3, dnfs: 1, sprint_races: 0 };
const details = { ...driver, givenName: 'Max', familyName: 'Verstappen', permanentNumber: '3', nationality: 'Dutch', dateOfBirth: '1997-09-30', bio: 'Пилот Формулы-1.', season: 2026, season_stats: stats, career_stats: { grand_prix_entered: 230, career_points: 3500, highest_race_finish: { position: 1, count: 65 }, highest_grid: { position: 1, count: 40 }, podiums: 110, pole_positions: 40, world_championships: 4, dnfs: 20 } };

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true, timeout: 30000 });
  try {
    for (const width of [320, 390, 460, 768, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 900 } });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.clock.setFixedTime(new Date('2026-10-02T12:00:00Z'));
      await page.route('**/api/**', route => {
        const path = new URL(route.request().url()).pathname;
        if (['/api/pilot-portrait', '/api/team-logo'].includes(path)) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="200"><rect width="160" height="200" fill="#242831"/></svg>' });
        const json = {
          '/api/season': { races }, '/api/settings': { timezone: 'Europe/Moscow' },
          '/api/drivers': { drivers: [driver] }, '/api/driver-details': details,
          '/api/driver-guide': { guide: null }, '/api/constructors': { constructors: [] },
          '/api/next-race': { status: 'none' }, '/api/race-results': { results: [] },
          '/api/auth/me': { authenticated: false },
        }[path] || {};
        return route.fulfill({ json });
      });

      await page.goto(`${base}/season?filter=all`);
      const stages = page.locator('.calendar-stages > li');
      await stages.nth(3).waitFor();
      assert.equal(await page.locator('#calendar-overview').count(), 1);
      await stages.nth(1).getByRole('button').click();
      await page.getByRole('heading', { name: 'United States Grand Prix', exact: true }).waitFor();
      await page.locator('.calendar-disclosure > summary').filter({ hasText: 'Расписание сессий' }).click();
      assert.ok(await page.locator('.calendar-sessions').isVisible());
      await page.locator('.calendar-disclosure > summary').filter({ hasText: 'О трассе' }).click();
      assert.ok(await page.locator('.calendar-facts').isVisible());
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Horizontal overflow at ${width}px`);
      await page.screenshot({ path: `artifacts/calendar-expanded-${width}.png` });
      await page.getByRole('link', { name: 'Открыть уик-энд', exact: true }).click();
      await page.waitForURL('**/next-race?season=2026&round=18');

      // Direct entry has no router history: back retains the requested standings season.
      await page.goto(`${base}/driver-details?code=VER&season=2025`);
      const back = page.getByRole('button', { name: 'Назад', exact: true });
      await back.waitFor();
      await page.locator('.driver-profile-navigation').waitFor();
      assert.equal(await back.count(), 1);
      assert.ok(await back.isVisible());
      assert.equal(await page.locator('.driver-profile-navigation a').getAttribute('href'), '/drivers?year=2025');
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: `artifacts/driver-profile-back-${width}.png` });
      await back.click();
      await page.waitForURL('**/drivers?year=2025');

      // Navigate through the app, then check that back restores the exact previous URL.
      const previousUrl = page.url();
      await page.locator('[role="button"]').filter({ hasText: 'Max Verstappen' }).filter({ visible: true }).first().click();
      await page.waitForURL('**/driver-details?**');
      await page.locator('.driver-profile-navigation').waitFor();
      await page.getByRole('button', { name: 'Назад', exact: true }).click();
      await page.waitForURL(previousUrl);
      assert.deepEqual(errors, [], `Browser errors at ${width}px`);
      await context.close();
      console.log(`${width}px: layout and profile back OK`);
    }
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
