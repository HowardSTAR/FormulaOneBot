// UI-only smoke test with synthetic data; never sends real forecasts or messages.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const future = new Date(Date.now() + 86400000).toISOString();
    const event = { round: 10, event_name: 'Тестовый Гран-при', race_start_utc: future, quali_start_utc: future };
    const summary = { id: 'qa', round: 10, session: 'race', created_at: Date.now() / 1000, status: 'ready', settled_at: null };
    const drivers = ['Lando Norris', 'Max Verstappen', 'Charles Leclerc', 'George Russell', 'Oscar Piastri'];
    const snapshot = { ...summary, error: null, actual: null, payload: {
      event, cutoff: summary.created_at, current_label: 'Квалификация', warnings: [], news_policy: 'Новости показаны как контекст.',
      model: { version: 'UI TEST DATA', trials: 12000, drivers: drivers.map((name, i) => ({ code: `D${i}`, name, team: 'Тестовая команда', win: .2, podium: .6, top10: 1, expected: i + 2.5, range: [1, 10], dnf: .1, reasons: ['Проверка пояснения модели'] })),
        scenarios: ['Победа фаворита', 'Победа преследователя', 'Неожиданный победитель'].map((label, i) => ({ label, probability: [.55, .3, .15][i], why: 'Синтетический сценарий для проверки вёрстки. Не реальный прогноз.', top5: drivers })) },
      inputs: { history: [{ name: 'Прошлый этап', season: 2025, round: 4 }], weather: { available: true, rain: .3, temperature: 23, wind: 9, hour: '2026-09-09T14:00' }, news_available: false, news: [] },
    } };
    let admin = true;
    await page.route('**/api/**', route => {
      const url = new URL(route.request().url());
      if (url.pathname === '/api/admin/me') return route.fulfill({ status: admin ? 200 : 403, json: admin ? { id: 1, role: 'admin' } : { detail: 'Forbidden' } });
      if (url.pathname === '/api/auth/me') return route.fulfill({ json: { id: 1, role: admin ? 'admin' : 'user', telegram_id: null } });
      if (url.pathname === '/api/admin/prediction-analytics/qa') return route.fulfill({ json: snapshot });
      if (url.pathname === '/api/admin/prediction-analytics') return route.fulfill({ json: route.request().method() === 'POST' ? { id: 'qa' } : { events: [event], snapshots: [summary], warning: null } });
      return route.fulfill({ json: { results: [], events: [], items: [] } });
    });
    await page.goto('http://127.0.0.1:5173/prediction-analytics');
    await page.getByRole('button', { name: /Этап 10/ }).click();
    await page.getByRole('heading', { name: 'Вероятности по пилотам' }).waitFor();
    await page.locator('summary').filter({ hasText: 'Lando Norris' }).click();
    await page.getByText('Проверка пояснения модели').first().waitFor();
    await page.screenshot({ path: path.resolve('artifacts/prediction-analytics-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.resolve('artifacts/prediction-analytics-mobile.png'), fullPage: true });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No viewport horizontal overflow');
    admin = false;
    await page.reload();
    await page.getByRole('heading', { name: 'Доступ запрещён' }).waitFor();
    assert.equal(await page.getByRole('heading', { name: 'Вероятности по пилотам' }).count(), 0);
    assert.deepEqual(errors, []);
    console.log('Desktop/mobile forecast display, explanation disclosure and denied route: passed');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
