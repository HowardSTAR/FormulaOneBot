// Local deep-link regression with synthetic scores and blocked external requests.
const assert = require('node:assert/strict');
const {pathToFileURL} = require('node:url');
const path = require('node:path');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '../front');
const base = 'http://127.0.0.1:5279';
const entries = Array.from({length: 5}, (_, i) => ({user_id: i + 1, display_name: `Pilot ${i + 1}`,
  total_points: 50 - i * 10, place: i + 1, best_points: 50 - i * 10, rounds_scored: 1,
  wins: i ? 0 : 1, tier_name: 'На старт', history: [{round: 1, points: 50 - i * 10}]}));

(async () => {
  process.chdir(root);
  const {createServer} = await import(pathToFileURL(path.join(root, 'node_modules/vite/dist/node/index.js')));
  const server = await createServer({root, server: {host: '127.0.0.1', port: 5279, strictPort: true}});
  await server.listen();
  let browser;
  try {
    browser = await chromium.launch({channel: 'msedge', headless: true});
    for (const width of [390, 1440]) {
      const context = await browser.newContext({viewport: {width, height: 960}, reducedMotion: 'reduce'});
      const page = await context.newPage();
      const errors = [], requested = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({status: 'completed'})));
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.origin !== base) return route.abort();
        if (!url.pathname.startsWith('/api/')) return route.continue();
        requested.push(url.pathname + url.search);
        let data = {items: [], unread: 0, status: 'none', entries: []};
        if (url.pathname === '/api/auth/me') data = {id: 1, role: 'user', telegram_id: 1001};
        if (url.pathname === '/api/next-race') data = {status: 'season_finished'};
        if (url.pathname === '/api/predictions/current') data = {status: 'ok', season: 2026, round: 1,
          is_open: false, profile: {completed: true, display_name: 'Pilot 1'}, drivers: [], scoring_rules: [], prediction: null};
        if (url.pathname === '/api/predictions/leaderboard') data = {season: 2025, entries, rounds: []};
        if (url.pathname === '/api/predictions/leagues') data = {leagues: [{id: 7, name: 'Friends', owner: false, mode: 'season', rounds: []},
          {id: 8, name: 'Other league', owner: false, mode: 'season', rounds: []}]};
        if (/^\/api\/predictions\/leagues\/\d+$/.test(url.pathname)) {
          assert.equal(url.searchParams.get('season'), '2025');
          data = {season: 2025, mode: 'season', rounds: [], entries};
        }
        if (url.pathname === '/api/profiles/me') data = {user_id: 1, is_owner: true, display_name: 'Pilot 1',
          supporter: true, tier: 1, tier_name: 'На старт', season: 2025, seasons: [2025, 2026],
          style: {frame: 'classic', color: 'white', background: 'carbon'}, options: {},
          best_prediction: null, predictions: [], records: [], total_points: 50, scored_rounds: 1, profile_guide_seen: true};
        if (url.pathname === '/api/profiles/supporters') {
          assert.equal(url.searchParams.get('season'), '2025');
          data = {season: 2025, current_user_id: 1, entries};
        }
        if (url.pathname.endsWith('/trophies')) data = {user_id: 1, families: [], earned: [], badge: null};
        return route.fulfill({json: data});
      });
      await page.goto(`${base}/predictions?tab=leagues&league=7&season=2025`);
      await page.locator('#prediction-league-7 .league-score-list li').last().waitFor();
      assert.equal(await page.locator('#prediction-league-7 .league-score-list li').count(), 5);
      assert.equal(await page.locator('#prediction-league-8 .league-score-list li').count(), 0);
      await page.getByRole('button', {name: 'Other league · Сезон →', exact: true}).click();
      await page.locator('#prediction-league-8 .league-score-list li').last().waitFor();
      assert.equal(new URL(page.url()).searchParams.get('league'), '8');
      assert(requested.includes('/api/predictions/leagues/7?season=2025'));
      assert(requested.includes('/api/predictions/leagues/8?season=2025'));
      await page.goto(`${base}/profile?league=supporters&season=2025`);
      await page.locator('#supporter-league-board tbody tr').last().waitFor();
      assert.equal(await page.locator('#supporter-league-board tbody tr').count(), 5);
      assert.equal(await page.getByRole('button', {name: 'Скрыть зачёт', exact: true}).getAttribute('aria-expanded'), 'true');
      assert(requested.includes('/api/profiles/supporters?season=2025'));
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No horizontal page overflow');
      assert.deepEqual(errors, []);
      await context.close();
    }
    console.log('League links: correct tables, all five participants, preserved season; mobile and desktop passed.');
  } finally {
    if (browser) await browser.close();
    await server.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
