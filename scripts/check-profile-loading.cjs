// Exercise profile request transitions with deliberately delayed API responses.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/sevag/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const base = process.env.PROFILE_UI_URL || 'http://127.0.0.1:5174';

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let account = 1, capture;
    const failedSeason = 2024;
    const requests = [];
    const holdNextProfile = () => new Promise(resolve => { capture = resolve; });
    await page.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'skipped' })));
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url()), path = url.pathname;
      if (path === '/api/auth/me') return route.fulfill({ json: { id: account, email: 'racer@example.test', email_verified: true, telegram_id: 2099386, role: 'user' } });
      if (path === '/api/profiles/avatar/v1.png') return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="88" height="88"><rect width="88" height="88" fill="#394"/></svg>' });
      if (path.endsWith('/trophies')) return route.fulfill({ json: { user_id: account, season: 2026, families: [], earned: [], pending: [], badge: null } });
      if (path === '/api/profiles/supporters') return route.fulfill({ json: { season: 2026, current_user_id: account, entries: [{ user_id: 99, display_name: 'Other Racer', tier_name: 'Полный газ', place: 1, total_points: 10, rounds_scored: 1, wins: 1, best_points: 10 }] } });
      if (!/^\/api\/profiles\/(me|\d+)$/.test(path)) return route.fulfill({ json: {} });
      const id = path.endsWith('/me') ? account : Number(path.split('/').pop());
      const season = Number(url.searchParams.get('season')) || 2026;
      const response = season === failedSeason ? { status: 503, json: { detail: 'Сезон временно недоступен' } } : { json: {
        user_id: id, display_name: `Racer ${id}`, is_owner: id === account, profile_guide_seen: true,
        tier: 3, tier_name: 'Полный газ', supporter: true, style: { frame: 'classic', color: 'white', background: 'carbon' },
        options: { frame: { classic: 0 }, color: { white: 0 }, background: { carbon: 0 } },
        avatar: { helmet: 'scarlet', suit: 'scarlet', background: 'garage' },
        avatar_options: { helmet: { scarlet: 'Алый' }, suit: { scarlet: 'Алый' }, background: { garage: 'Гараж' } },
        season, seasons: [2026, 2025, 2024], total_points: season, scored_rounds: 0,
        best_prediction: null, predictions: [], records: [], favorites: { drivers: [], teams: [] },
      } };
      if (capture) {
        const held = { route, response };
        requests.push(held);
        capture(held);
        capture = null;
        return;
      }
      return route.fulfill(response);
    });
    const expectLoading = async () => {
      await page.getByRole('status').filter({ hasText: 'Загружаем профиль…' }).waitFor();
      assert.equal(await page.locator('.profile-hero').count(), 0, 'Previous profile is hidden while loading');
      assert.equal(await page.locator('.user-profile-page [role="alert"]').count(), 0, 'Previous error is cleared');
    };
    const release = async request => {
      const received = page.waitForResponse(response => response.url() === request.route.request().url());
      await request.route.fulfill(request.response);
      await received;
    };
    await page.goto(base + '/profile');
    await page.getByRole('heading', { name: /^Racer 1\b/ }).waitFor();
    const pendingSeason = holdNextProfile();
    await page.getByRole('combobox', { name: 'Сезон профиля' }).selectOption('2025');
    await expectLoading();
    const olderSeason = await pendingSeason;
    await page.goBack();
    await page.getByRole('heading', { name: 'Прогнозы · 2026', exact: true }).waitFor();
    await release(olderSeason);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await page.getByRole('combobox', { name: 'Сезон профиля' }).inputValue(), '2026', 'Late response cannot replace the selected season');

    await page.getByRole('combobox', { name: 'Сезон профиля' }).selectOption('2024');
    await page.locator('.user-profile-page [role="alert"]').filter({ hasText: 'Сервис временно недоступен' }).waitFor();
    const pendingRecovery = holdNextProfile();
    await page.goBack();
    await expectLoading();
    await release(await pendingRecovery);
    await page.getByRole('heading', { name: 'Прогнозы · 2026', exact: true }).waitFor();

    await page.getByRole('button', { name: 'Показать зачёт · 2026' }).click();
    const pendingVisitor = holdNextProfile();
    await page.getByRole('link', { name: /Other Racer/ }).click();
    await expectLoading();
    await release(await pendingVisitor);
    await page.getByRole('heading', { name: /^Racer 99\b/ }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Возможности профиля' }).count(), 0, 'Public profile has no owner controls');
    await page.getByRole('link', { name: 'Мой профиль', exact: true }).click();
    await page.getByRole('heading', { name: /^Racer 1\b/ }).waitFor();
    await page.getByRole('button', { name: 'Аватар и оформление', exact: true }).click();
    await page.getByRole('dialog', { name: 'Аватар и оформление' }).waitFor();
    account = 2;
    const pendingAccount = holdNextProfile();
    await page.evaluate(() => window.dispatchEvent(new Event('turbotears-auth-changed')));
    await expectLoading();
    assert.equal(await page.getByRole('dialog', { name: 'Аватар и оформление' }).count(), 0, 'Switching account closes the previous editor');
    await release(await pendingAccount);
    await page.getByRole('heading', { name: /^Racer 2\b/ }).waitFor();
    assert.equal(requests.length, 4);
    assert.deepEqual(errors, []);
    console.log('PASS: loading, error recovery, stale season responses, public navigation and account/editor isolation.');
    await page.close();
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
