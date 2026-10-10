// Read-only local fixtures: the tour must not submit forecasts, messages or scores.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const base = process.env.FIRST_VISIT_UI_URL || 'http://127.0.0.1:5174';
const key = 'turbotears-onboarding-v2';
const steps = [['/', 'Главная'], ['/season', 'Календарь'], ['/race-results', 'Результаты'], ['/drivers', 'Пелотон'], ['/compare', 'Сравнение'], ['/predictions', 'Прогнозы'], ['/community', 'С друзьями'], ['/wiki', 'Справочник F1'], ['/reaction-game', 'Игры'], ['/profile', 'Мой профиль'], ['/account', 'Аккаунт и настройки'], ['/account', 'Boosty и бонусы'], ['/contact-admin', 'Обратная связь']];
const race = { status: 'ok', season: 2026, round: 17, event_name: 'Singapore Grand Prix', location: 'Marina Bay', country: 'Singapore', race_start_utc: '2026-10-11T12:00:00Z', next_session_iso: '2026-10-09T09:00:00Z', next_session_name: 'Практика 1' };

async function checkCard(page) {
  await page.waitForFunction(() => document.documentElement.dataset.onboardingPhase === 'ready');
  await page.waitForFunction(() => {
    const r = document.querySelector('.first-visit-card').getBoundingClientRect();
    return r.x >= 0 && r.y >= 0 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1;
  });
  await page.waitForFunction(() => {
    const p = document.querySelector('.app-content').getBoundingClientRect();
    const c = document.querySelector('.first-visit-guide').getBoundingClientRect();
    return p.right <= c.left || p.bottom <= c.top;
  });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  const workspace = await page.evaluate(() => {
    const p = document.querySelector('.app-content').getBoundingClientRect();
    const c = document.querySelector('.first-visit-guide').getBoundingClientRect();
    return { separate: p.right <= c.left || p.bottom <= c.top, height: p.height,
      opacity: getComputedStyle(document.querySelector('.app-page-main')).opacity,
      darkOverlay: !!document.querySelector('.first-visit-backdrop, .first-visit-dialog') };
  });
  assert.ok(workspace.separate, 'Instructions must have their own space outside the page');
  assert.ok(workspace.height >= 320, `Portrait page must retain enough room to read and scroll: ${JSON.stringify(workspace)}`);
  assert.equal(workspace.opacity, '1');
  assert.equal(workspace.darkOverlay, false);
  const guide = page.locator('.first-visit-guide');
  assert.equal(await guide.getByRole('button', { name: 'Пропустить', exact: true }).count(), 0);
  const back = guide.getByRole('button', { name: 'Назад', exact: true });
  if (await back.count()) {
    const b = await back.boundingBox(), next = await guide.locator('.first-visit-primary').boundingBox();
    assert.ok(b.width >= 56 && b.height >= 44 && next.x - b.x - b.width >= 10, 'Back must be easy to tap separately from Next');
  }
}
async function replayGuide(page, width) {
  if (width < 768) {
    await page.getByRole('button', { name: 'Меню', exact: true }).click();
    const section = page.locator('.mobile-menu-dialog section').filter({ has: page.getByRole('heading', { name: 'Справка и аккаунт', exact: true }) });
    await section.getByRole('button', { name: 'Короткое знакомство', exact: true }).click();
    await page.locator('.mobile-menu-dialog').waitFor({ state: 'hidden' });
  } else {
    const header = page.locator('.app-header');
    const help = header.getByRole('button', { name: 'Помощь', exact: true });
    if (await help.getAttribute('aria-expanded') !== 'true') await help.click();
    await header.getByRole('button', { name: 'Короткое знакомство', exact: true }).click();
  }
  await page.waitForURL(`${base}/`);
}
async function checkTrack(page, selector) {
  const border = page.locator(`${selector} .track-route-border:visible`).first();
  await border.waitFor();
  const style = await border.evaluate(border => {
    const red = getComputedStyle(border), surface = getComputedStyle(border.nextElementSibling);
    return { color: red.stroke, width: parseFloat(red.strokeWidth), surface: parseFloat(surface.strokeWidth), borderScaling: red.vectorEffect, surfaceScaling: surface.vectorEffect, glow: red.filter };
  });
  assert.equal(style.color, 'rgb(255, 48, 40)');
  assert.ok(style.width > style.surface);
  assert.equal(style.borderScaling, 'non-scaling-stroke');
  assert.equal(style.surfaceScaling, 'non-scaling-stroke');
  assert.match(style.glow, /drop-shadow/);
}
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const { width, height, member, eligible, tier } of [
      { width: 320, height: 640, member: false, eligible: false, tier: 0 },
      { width: 390, height: 844, member: true, eligible: true, tier: 0 },
      { width: 1440, height: 900, member: true, eligible: true, tier: 3 },
      { width: 1440, height: 900, member: true, eligible: false, tier: 0 },
    ]) {
      const timezoneId = width === 390 ? 'Asia/Tokyo' : width === 1440 ? 'America/New_York' : 'Europe/Moscow';
      const context = await browser.newContext({ viewport: { width, height }, timezoneId, reducedMotion: width === 390 ? 'no-preference' : 'reduce' });
      await context.route('https://telegram.org/**', route => route.abort());
      if (width === 390) await context.addInitScript(() => {
        window.Telegram = { WebApp: { initData: 'local-test', platform: 'android', ready() {}, expand() {} } };
      });
      const page = await context.newPage();
      const errors = [], mutations = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', message => { if (/same key|unique.*key/i.test(message.text())) errors.push(message.text()); });
      await page.route('**/static/circuit/*.svg', route => route.fulfill({ contentType: 'image/svg+xml', body: readFileSync(join(__dirname, '../front/public/static/circuit/Singapore Grand Prix.svg')) }));
      await page.route('**/api/**', route => {
        const path = new URL(route.request().url()).pathname;
        if (route.request().method() !== 'GET' && !path.startsWith('/api/analytics/')) mutations.push(path);
        if (path === '/api/profiles/avatar/v1.png') return route.fulfill({ contentType: 'image/png', body: readFileSync(join(__dirname, '../app/profile_avatar_assets/scarlet-v1.png')) });
        if (path === '/api/auth/me') return route.fulfill(member ? { json: { id: 777, email: 'local@example.test', email_verified: true, telegram_id: 777, display_name: 'Local member', role: 'user' } } : { status: 401, json: { detail: 'Guest' } });
        if (path === '/api/profiles/me') return route.fulfill(member ? { json: {
          user_id: 777, display_name: 'Local member', tier, tier_name: tier ? 'Полный газ' : 'Участник', supporter: tier > 0,
          style: { frame: 'classic', color: 'white', background: 'carbon' }, is_owner: true,
          season: 2026, seasons: [2026], best_prediction: null, predictions: [], records: [], total_points: 0, scored_rounds: 0,
          favorites: { drivers: [], teams: [] }, options: { frame: { classic: 0 }, color: { white: 0 }, background: { carbon: 0 } },
        } } : { status: 401, json: { detail: 'Guest' } });
        if (path === '/api/account/boosty') return route.fulfill({ json: {
          eligible, configured: true, active: tier > 0, blog_url: 'https://boosty.to/turbotears',
          level_name: tier ? 'Полный газ' : null, checked_at: null, check_failed: false, premium_active: tier > 0, premium_override: null,
        } });
        if (path === '/api/next-race') return route.fulfill({ json: race });
        if (path === '/api/settings') return route.fulfill({ json: { timezone: 'Europe/Moscow' } });
        if (path === '/api/weekend-schedule') return route.fulfill({ json: { sessions: [{ name: 'Практика 1', utc_iso: '2026-10-09T09:00:00Z' }, { name: 'Гонка', utc_iso: '2026-10-11T12:00:00Z' }] } });
        if (path === '/api/season') return route.fulfill({ json: { races: [{ ...race, date: '2026-10-11' }] } });
        if (['/api/predictions/preview', '/api/predictions/current'].includes(path)) return route.fulfill({ json: { status: 'ok', season: 2026, round: 17, event_name: race.event_name, is_open: false, profile: { display_name: '', completed: false }, prediction: null, drivers: [], scoring_rules: [] } });
        if (path === '/api/engagement/weekly') return route.fulfill({ json: { track_id: 'emerald-loop', name: 'Трасса недели', start: '2026-10-05T00:00:00Z', end: '2026-10-12T00:00:00Z', entries: [] } });
        if (path === '/api/engagement/mine') return route.fulfill({ json: { badges: [], shares: [], referrals: { arrived: 0, activated: 0, returned: 0 } } });
        if (path === '/api/engagement/weekly/me') return route.fulfill({ json: { user_id: 777, weekly: null } });
        if (path === '/api/reaction-leaderboard/profile') return route.fulfill({ json: { prompt_seen: true, participate: false, display_name: '' } });
        return route.fulfill({ json: { status: 'none', items: [], results: [], rounds: [], drivers: [], constructors: [], entries: [], unread: 0 } });
      });
      await page.goto(base);
      const guide = page.locator('.first-visit-guide');
      await guide.getByRole('heading', { name: 'Главная', exact: true }).waitFor();
      await checkCard(page);
      assert.equal(await guide.locator('input[type="radio"]').count(), 0);
      assert.ok((await guide.innerText()).includes(timezoneId === 'Europe/Moscow' ? 'МСК (UTC+3)' : timezoneId.replace(/_/g, ' ')));
      const raceTime = new Date(race.race_start_utc).toLocaleTimeString('ru-RU', { timeZone: timezoneId, hour: '2-digit', minute: '2-digit' });
      assert.ok((await page.locator('.weekend-board').innerText()).includes(raceTime), 'Home must use the device timezone even when the account stores Moscow');
      const initialHistory = await page.evaluate(() => history.length);
      for (const [index, [route, title]] of steps.entries()) {
        await page.waitForFunction(route => location.pathname === route, route);
        await guide.getByRole('heading', { name: title, exact: true }).waitFor();
        assert.equal(await page.locator('.app-page-main .btn-back').count(), 0, `No section back button: ${route}`);
        if (index === steps.length - 1) {
          assert.match(await guide.innerText(), width < 768 ? /Повторить знакомство.*Справка и аккаунт/ : /Повторить знакомство.*Помощь → Короткое знакомство/);
        }
        assert.ok((await guide.innerText()).includes(`${index + 1} / ${steps.length}`));
        try { await checkCard(page); } catch (error) {
          console.error({ width, route, errors, page: (await page.locator('body').innerText()).slice(0, 1500) });
          throw error;
        }
        await page.locator(`.first-visit-highlight[data-tour-route="${route}"]`).waitFor();
        if (title === 'Мой профиль') {
          await page.locator(member ? '.profile-hero.first-visit-highlight' : '.user-profile-page [role="alert"].first-visit-highlight').waitFor();
          assert.match(await guide.innerText(), /Аватар и оформление.*поделиться с друзьями/);
          if (member) {
            await page.getByRole('button', { name: 'Аватар и оформление', exact: true }).waitFor();
            await page.locator('.profile-avatar img').evaluate(image => image.decode());
          }
          else await page.getByRole('link', { name: 'Войти в аккаунт', exact: true }).waitFor();
        }
        if (title === 'Аккаунт и настройки') assert.match(await guide.innerText(), /одинаковый подтверждённый email/);
        if (title === 'Boosty и бонусы') {
          const highlight = member ? eligible ? '.account-boosty-card' : '.account-hero h1' : '.account-auth-card';
          await page.locator(`${highlight}.first-visit-highlight`).waitFor();
          assert.match(await guide.innerText(), /«На старт» — значок и клуб; «Свой стиль» — рамки, цвет ника и фоны; «Полный газ» — вся коллекция/);
          // Adjacent steps share /account; Back/Next must still change the copy and highlight.
          await guide.getByRole('button', { name: 'Назад', exact: true }).click();
          await guide.getByRole('heading', { name: 'Аккаунт и настройки', exact: true }).waitFor();
          await checkCard(page);
          assert.ok((await guide.innerText()).includes(`${index} / ${steps.length}`));
          assert.equal(await page.evaluate(() => location.pathname), '/account');
          await guide.getByRole('button', { name: 'Дальше →', exact: true }).click();
          await guide.getByRole('heading', { name: title, exact: true }).waitFor();
          await checkCard(page);
          await page.locator(`${highlight}.first-visit-highlight`).waitFor();
          assert.ok((await guide.innerText()).includes(`${index + 1} / ${steps.length}`));
        }
        if ([1, 2].includes(index)) {
          const heading = page.locator('.app-page-main h1:visible, .app-page-main h2:visible').first();
          const headingPosition = await heading.evaluate(node => {
            const h = node.getBoundingClientRect(), p = document.querySelector('.app-content').getBoundingClientRect();
            return { top: h.top, bottom: h.bottom, pageTop: p.top, pageBottom: p.bottom };
          });
          assert.ok(headingPosition.top >= headingPosition.pageTop && headingPosition.bottom <= headingPosition.pageBottom,
            `Keep the page heading visible: ${width} ${route} ${JSON.stringify(headingPosition)}`);
        }
        if (index === 2) {
          await guide.getByRole('button', { name: 'Назад', exact: true }).click();
          await page.waitForFunction(() => location.pathname === '/season');
          await guide.getByRole('heading', { name: 'Календарь', exact: true }).waitFor();
          await guide.getByRole('button', { name: 'Дальше →' }).click();
          await guide.getByRole('heading', { name: title, exact: true }).waitFor();
          await page.locator(`.first-visit-highlight[data-tour-route="${route}"]`).waitFor();
          await checkCard(page);
        }
        if (index === 7) {
          const search = page.locator('.wiki-controls input');
          await search.fill('флаг');
          assert.equal(await search.inputValue(), 'флаг');
        }
        if (width === 390 && [0, 1, 2, 5, 8, 9, 11].includes(index)) await page.screenshot({ path: `artifacts/section-tour-${index}-mobile.png` });
        if (width === 1440 && index === 1) await page.screenshot({ path: 'artifacts/section-tour-desktop.png' });
        if (width === 1440 && eligible && [9, 11].includes(index)) await page.screenshot({ path: `artifacts/section-tour-${index}-desktop.png` });
        await guide.getByRole('button', { name: index === steps.length - 1 ? 'На главную →' : 'Дальше →', exact: true }).click();
        if (width === 390 && index === 0) {
          assert.equal(await page.evaluate(() => document.documentElement.dataset.onboardingPhase), 'leaving');
          assert.equal(await page.evaluate(() => location.pathname), '/', 'Outgoing page remains mounted during its fade');
          assert.equal(await guide.locator('.first-visit-primary').isDisabled(), true);
        }
      }
      await page.waitForFunction(() => location.pathname === '/');
      await guide.waitFor({ state: 'hidden' });
      assert.deepEqual(await page.evaluate(k => JSON.parse(localStorage.getItem(k)), key), { status: 'completed' });
      assert.equal(await page.evaluate(() => history.length), initialHistory);
      assert.equal(await page.evaluate(() => document.documentElement.dataset.onboardingActive), undefined);
      await page.reload();
      await page.locator('.weekend-board-location').waitFor();
      assert.equal(await page.locator('dialog[open]').count(), 0);
      if (width === 1440) {
        await checkTrack(page, '.index-hero-track-map');
        await page.goto(`${base}/season`);
        await checkTrack(page, '.season-desktop-track-svg');
        await page.goto(base);
      }
      assert.equal(await page.locator('.first-visit-entry').count(), 0);
      assert.equal(await page.getByText('Все разделы TurboTears', { exact: true }).count(), 0);
      if (width === 390) {
        await page.getByRole('navigation', { name: 'Основная навигация', exact: true }).getByRole('link', { name: 'Уик-энд', exact: true }).click();
        await page.locator('.next-race-mobile .weekend-session-list').waitFor();
        assert.ok((await page.locator('.next-race-mobile .weekend-session-list').innerText()).includes(raceTime), 'Telegram weekend must use the same local time as Home');
        assert.equal(await page.locator('.app-page-main .btn-back').count(), 0);
      }
      await replayGuide(page, width);
      await guide.waitFor();
      await page.keyboard.press('Escape');
      await guide.waitFor({ state: 'hidden' });
      assert.equal(await page.evaluate(k => JSON.parse(localStorage.getItem(k)).status, key), 'skipped');
      if (width === 390) {
        await page.evaluate(k => localStorage.removeItem(k), key);
        await page.goto(`${base}/season`);
        await page.locator('.season-page, .season-desktop-header, .page-head-title').first().waitFor();
        assert.equal(await page.locator('dialog[open]').count(), 0);
        await page.addInitScript(k => {
          const get = Storage.prototype.getItem, set = Storage.prototype.setItem;
          Storage.prototype.getItem = function(name) { if (name === k) throw new Error('Storage denied'); return get.call(this, name); };
          Storage.prototype.setItem = function(name, value) { if (name === k) throw new Error('Storage denied'); return set.call(this, name, value); };
        }, key);
        await page.goto(base);
        await guide.waitFor();
        await guide.getByRole('button', { name: 'Закрыть знакомство', exact: true }).click();
        await page.locator('.quick-access a[href="/season"]').click();
        await page.waitForURL(`${base}/season`);
        await page.getByRole('link', { name: 'Главная', exact: true }).click();
        await page.locator('.weekend-board-location').waitFor();
        assert.equal(await page.locator('dialog[open]').count(), 0);
      }
      assert.deepEqual(errors, []);
      assert.deepEqual(mutations, []);
      console.log(`Section tour ${width}×${height} ${member ? `member tier=${tier} Boosty=${eligible}` : 'guest'}: all ${steps.length} steps, profile, Boosty, same-page back/next, completion, replay, Escape, history and persistence passed`);
      await context.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
