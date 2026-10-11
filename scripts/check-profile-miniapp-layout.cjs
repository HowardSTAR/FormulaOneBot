// Regression checks for Telegram host controls and readable mobile club standings.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.PROFILE_UI_URL || 'http://127.0.0.1:5174';
const cases = [
  { name: 'browser-320', width: 320, height: 640, top: 0, bottom: 0, left: 0, right: 0 },
  { name: 'telegram-390', width: 390, height: 844, top: 91, bottom: 34, left: 0, right: 0 },
  { name: 'telegram-landscape', width: 740, height: 390, top: 44, bottom: 21, left: 44, right: 44 },
  { name: 'desktop', width: 1440, height: 1000, top: 0, bottom: 0, left: 0, right: 0 },
];
const avatar = { helmet: 'scarlet', suit: 'scarlet', background: 'garage' };
const avatarOptions = {
  helmet: { scarlet: 'Алый / полоса', cobalt: 'Кобальт / двойная полоса', mint: 'Жемчуг / мята' },
  suit: { scarlet: 'Алый / графит', cobalt: 'Индиго / лайм', mint: 'Графит / мята' },
  background: { garage: 'Ночной бокс', scarlet: 'Красный сектор', cobalt: 'Синий час', mint: 'Полярное сияние', gold: 'Золотой подиум' },
};
const fixture = {
  user_id: 1, display_name: 'Admin', is_owner: true, profile_guide_seen: true,
  tier: 3, tier_name: 'Полный газ', supporter: true, avatar, avatar_options: avatarOptions,
  style: { frame: 'classic', color: 'white', background: 'carbon' },
  options: { frame: { classic: 0, red: 2, gold: 3 }, color: { white: 0, red: 2, gold: 3 }, background: { carbon: 0, grid: 2, champion: 3 } },
  season: 2026, seasons: [2026], total_points: 57, scored_rounds: 8,
  best_prediction: null, predictions: [], records: [], favorites: { drivers: [], teams: [] },
};
const board = {
  season: 2026, current_user_id: 1,
  entries: [
    { user_id: 1, display_name: 'Admin', tier_name: 'Полный газ', place: 1, total_points: 57, rounds_scored: 8, wins: 4, best_points: 25 },
    { user_id: 2, display_name: 'Nastushka', tier_name: 'Свой стиль', place: 2, total_points: 31, rounds_scored: 6, wins: 1, best_points: 19 },
    { user_id: 3, display_name: 'ОченьДлинноеИмяУчастникаБезПробеловДляПроверкиПереноса', tier_name: 'На старт', place: 123, total_points: 123456, rounds_scored: 24, wins: 12, best_points: 40 },
  ],
};
async function applyInsets(page, values) {
  await page.evaluate(values => {
    document.documentElement.dataset.telegramMobile = values.name.startsWith('telegram') ? 'true' : 'false';
    for (const side of ['top', 'bottom', 'left', 'right']) {
      // Split iOS status bar and Telegram controls as the SDK does.
      const device = side === 'top' && values.top === 91 ? 47 : values[side];
      document.documentElement.style.setProperty(`--tg-safe-area-inset-${side}`, `${device}px`);
      document.documentElement.style.setProperty(`--tg-content-safe-area-inset-${side}`, `${values[side] - device}px`);
    }
  }, values);
}
async function checkEditor(page, values) {
  const metrics = await page.locator('.avatar-editor').evaluate(dialog => {
    const rect = element => { const r = element.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height }; };
    return { dialog: rect(dialog), close: rect(dialog.querySelector('header>button')), title: rect(dialog.querySelector('h2')), overflow: dialog.scrollWidth > dialog.clientWidth };
  });
  assert.ok(metrics.dialog.top >= values.top + 15, JSON.stringify(metrics));
  assert.ok(metrics.dialog.bottom <= values.height - values.bottom - 15, JSON.stringify(metrics));
  assert.ok(metrics.dialog.left >= values.left + 11);
  assert.ok(metrics.dialog.right <= values.width - values.right - 11);
  assert.ok(metrics.title.right <= metrics.close.left);
  assert.ok(metrics.close.height >= 44);
  assert.equal(metrics.overflow, false);
  await page.locator('.avatar-editor').evaluate(dialog => { dialog.scrollTop = dialog.scrollHeight; });
  const footer = await page.locator('.avatar-editor footer').evaluate(element => {
    const r = element.getBoundingClientRect();
    return { bottom: r.bottom, top: r.top, statusBottom: document.querySelector('.avatar-editor-subscription-status').getBoundingClientRect().bottom,
      buttons: [...element.querySelectorAll('button')].map(button => { const b = button.getBoundingClientRect(); return { bottom: b.bottom, height: b.height }; }) };
  });
  assert.ok(footer.statusBottom <= footer.top + 1, 'Subscription details scroll clear of the footer');
  assert.ok(footer.buttons.every(button => button.bottom <= values.height - values.bottom && button.height >= 44), JSON.stringify(footer));
  await page.locator('.avatar-editor').evaluate(dialog => { dialog.scrollTop = 0; });
}
(async () => {
  fs.mkdirSync('artifacts', { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const values of cases) {
      const page = await browser.newPage({ viewport: { width: values.width, height: values.height }, reducedMotion: 'reduce' });
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'completed' })));
      await page.route('**/api/**', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/auth/me') return route.fulfill({ json: { id: 1, email: 'layout@example.test', email_verified: true, telegram_id: 2099386, role: 'user' } });
        if (url.pathname === '/api/profiles/supporters') return route.fulfill({ json: board });
        if (url.pathname === '/api/profiles/avatar/v1.png') {
          const key = ['helmet', 'suit', 'background'].map(k => url.searchParams.get(k)).join('-');
          return route.fulfill({ contentType: 'image/png', body: fs.readFileSync(`.tmp/profile-avatar-fixtures/${key}.png`) });
        }
        if (url.pathname.endsWith('/trophies')) return route.fulfill({ json: { user_id: 1, season: 2026, families: [], earned: [], pending: [], badge: null } });
        if (url.pathname === '/api/account/boosty') return route.fulfill({ json: { eligible: true, configured: true, active: true, level_name: 'Полный газ', checked_at: 1791630000, can_check: true, premium_override: null } });
        return route.fulfill({ json: url.pathname.startsWith('/api/profiles/') ? fixture : {} });
      });
      await page.goto(`${base}/profile`);
      await page.getByRole('heading', { name: /Admin/ }).waitFor();
      await applyInsets(page, values);
      await page.getByRole('button', { name: 'Аватар и оформление', exact: true }).click();
      await page.getByRole('dialog').waitFor();
      await page.locator('.avatar-editor-subscription-status').getByText(/Подписка «Полный газ» активна\./).waitFor();
      await checkEditor(page, values);
      await page.screenshot({ path: `artifacts/miniapp-avatar-${values.name}.png` });
      if (values.name === 'telegram-390') {
        const resized = { ...values, top: 107, bottom: 48 };
        await applyInsets(page, resized);
        await checkEditor(page, resized);
        await applyInsets(page, values);
      }
      await page.getByRole('button', { name: 'Закрыть настройки аватара и оформления' }).click();
      await page.getByRole('button', { name: 'Показать зачёт · 2026' }).click();
      await page.locator('.supporter-league-table tbody tr').first().waitFor();
      const rows = await page.locator('.supporter-league-table tbody tr').evaluateAll(elements => elements.map(row => {
        const bounds = row.getBoundingClientRect();
        const cells = [...row.children].filter(cell => getComputedStyle(cell).display !== 'none').map(cell => cell.getBoundingClientRect());
        return { contained: cells.every(cell => cell.left >= bounds.left - 1 && cell.right <= bounds.right + 1),
          separate: cells.slice(1).every(cell => cells[0].right <= cell.left || cells[0].bottom <= cell.top),
          nameBeforePoints: cells[1].right <= cells[2].left && cells[1].width >= 45,
          textFits: [...row.querySelectorAll('a, strong')].every(element => element.scrollWidth <= element.clientWidth + 1),
          metricsBelow: !row.querySelector('.supporter-league-mobile-metrics').checkVisibility() || row.querySelector('.supporter-league-mobile-metrics').getBoundingClientRect().top >= Math.max(...cells.slice(0, 3).map(cell => cell.bottom)),
          labelsVisible: [...row.querySelectorAll('.supporter-league-mobile-label')].every(label => getComputedStyle(label).display !== 'none') };
      }));
      assert.ok(rows.every(row => row.contained && row.separate && row.nameBeforePoints && row.textFits && row.metricsBelow), JSON.stringify(rows));
      if (values.width <= 600) assert.ok(rows.every(row => row.labelsVisible), 'Every mobile score has a readable label');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.locator('.supporter-league').screenshot({ path: `artifacts/miniapp-league-${values.name}.png`, style: '.mobile-primary-nav, .scroll-to-top { visibility: hidden !important; }' });
      assert.deepEqual(errors, []);
      console.log(`${values.name}: safe modal, reachable actions, long names and labelled standings passed`);
      await page.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
