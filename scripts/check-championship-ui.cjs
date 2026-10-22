// Actual React form with deterministic scenarios from the production calculator.
const { chromium } = require('C:/Users/sevag/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const base = process.env.CHAMPIONSHIP_UI_URL || 'http://127.0.0.1:5176';
const root = 'artifacts/championship';
const codes = ['ANT', 'RUS', 'NOR', 'VER', 'LEC', 'HAM'];
const names = ['Кими Антонелли', 'Джордж Расселл', 'Ландо Норрис', 'Макс Ферстаппен', 'Шарль Леклер', 'Льюис Хэмилтон'];
const core = { sprint_pole_driver: 'ANT', sprint_winner_driver: 'ANT', pole_driver: 'ANT', winner_driver: 'ANT', second_driver: 'RUS', third_driver: 'NOR', fourth_driver: 'VER', fifth_driver: 'LEC', fastest_lap_driver: 'ANT', first_retirement_driver: 'HAM', safety_car: false };

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const report = [];
  try {
    for (const width of [320, 390, 1440]) {
      for (const variant of ['single', 'multiple', 'sprint', 'none', 'closed', 'setup']) {
        const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
        const errors = [];
        page.on('pageerror', e => errors.push(e.message));
        let saved = { ...core, championship: {} }, posted = null;
        const source = variant === 'closed' ? 'multiple' : variant === 'setup' ? 'single' : variant;
        const data = variant === 'none' ? { status: 'ok', drivers: [], constructors: [] } : JSON.parse(fs.readFileSync(`${root}/${source}.json`, 'utf8'));
        const now = Date.now();
        const current = () => ({ status: 'ok', season: 2026, round: data.round || 22, event_name: 'Гран-при · демонстрация', has_sprint: variant === 'sprint', is_open: variant !== 'closed',
          opens_at_utc: new Date(now - 7200000).toISOString(), deadline_utc: new Date(now + (variant === 'closed' ? -3600000 : 86400000)).toISOString(),
          profile: { display_name: 'Участник демо', completed: variant !== 'setup' }, prediction: saved, scoring_rules: [],
          drivers: codes.map((code, i) => ({ code, name: names[i], constructorName: ['Mercedes', 'Mercedes', 'McLaren', 'Red Bull', 'Ferrari', 'Ferrari'][i] })) });
        await page.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'skipped' })));
        await page.route('**/api/**', route => {
          const path = new URL(route.request().url()).pathname;
          if (path === '/api/auth/me') return route.fulfill({ json: { id: 1, display_name: 'Участник демо', telegram_id: 123, email_verified: true, role: 'user' } });
          if (path === '/api/predictions/championship') return route.fulfill({ json: data });
          if (path === '/api/predictions/current') {
            if (route.request().method() === 'POST') { posted = route.request().postDataJSON(); saved = { ...posted }; return route.fulfill({ json: { status: 'ok', prediction: saved } }); }
            return route.fulfill({ json: current() });
          }
          if (path === '/api/predictions/leaderboard') return route.fulfill({ json: { season: 2026, entries: [], rounds: [], current_user_id: 1 } });
          if (path === '/api/next-race') return route.fulfill({ json: { status: 'season_finished' } });
          if (path === '/api/predictions/personal-season') return route.fulfill({ json: { season: 2026, history: [], categories: [], achievements: [], latest: null, place: null, best_points: null, average_points: null } });
          if (path.includes('portrait') || path.includes('team-logo')) return route.fulfill({ status: 404 });
          return route.fulfill({ json: {} });
        });
        await page.goto(`${base}/predictions`);
        await page.getByRole('heading', { name: 'Гран-при · демонстрация' }).waitFor();
        const card = page.getByRole('region', { name: 'Прогноз на чемпионство' });
        const save = page.getByRole('button', { name: 'Обновить прогноз' });
        if (variant === 'closed' || variant === 'setup') {
          await card.waitFor();
          assert.equal(await card.getByRole('button', { name: 'Да', exact: true }).count(), 0);
          assert.equal(await card.getByRole('combobox').count(), 0, 'conditions visible without an editable forecast');
          await card.locator('.title-candidate details > summary').first().click();
          assert(await card.getByText('Все ограничения ниже', { exact: false }).first().isVisible());
        } else if (variant === 'none') {
          assert.equal(await card.count(), 0);
          assert.equal(await save.isDisabled(), false);
        } else {
          await card.waitFor();
          assert.equal(await save.isDisabled(), true, 'title answers must be explicit');
          if (variant === 'multiple') {
            assert.equal(await card.locator('.title-candidate-name').count(), 0, 'no automatic choice with multiple candidates');
            await card.getByRole('combobox', { name: 'Выберите пилота' }).click();
            await page.getByRole('option', { name: 'Джордж Расселл · 348 очк.' }).click();
            await card.getByRole('combobox', { name: 'Выберите команду' }).click();
            await page.getByRole('option', { name: 'McLaren · 695 очк.' }).click();
          } else {
            assert.equal(await card.getByRole('combobox', { name: /Выберите пилота|Выберите команду/ }).count(), 0);
          }
          await card.getByRole('group', { name: 'Титул пилота', exact: true }).getByRole('button', { name: 'Нет', exact: true }).click();
          await card.getByRole('group', { name: 'Титул команды', exact: true }).getByRole('button', { name: 'Да', exact: true }).click();
          assert.equal(await save.isDisabled(), false);
          await card.scrollIntoViewIfNeeded();
          if (width === 390 || width === 1440) await card.screenshot({ path: `${root}/form-${variant}-${width}.png` });
          await card.locator('summary').filter({ hasText: 'Условия титула' }).first().click();
          assert(await card.getByText('Все ограничения ниже', { exact: false }).first().isVisible());
          await card.getByRole('combobox', { name: /Очки за/ }).first().click();
          const options = page.getByRole('option').filter({ hasText: 'Набрать' });
          const last = options.last();
          await last.click();
          await card.locator('summary').filter({ hasText: 'Места, дающие' }).first().click();
          assert(await card.locator('.title-finishes li').count() > 0);
          if (width === 390 && variant === 'single') await card.locator('.title-candidate').first().screenshot({ path: `${root}/conditions-390.png` });
          await save.click();
          await page.getByText('Прогноз сохранён. Его можно изменить до начала квалификации.').waitFor();
          assert.equal(posted.championship.drivers.yes, false);
          assert.equal(posted.championship.constructors.yes, true);
          assert.equal(posted.championship.drivers.id, variant === 'multiple' ? 'RUS' : 'ANT');
          assert.equal(await card.getByRole('group', { name: 'Титул пилота', exact: true }).getByRole('button', { name: 'Нет', exact: true }).getAttribute('aria-pressed'), 'true');
        }
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
        assert.equal(overflow, false, `no horizontal overflow at ${width}`);
        assert.deepEqual(errors, []);
        report.push({ width, variant, saved: Boolean(posted) });
        await page.close();
      }
    }
    const notification = await browser.newPage({ viewport: { width: 450, height: 1000 } });
    await notification.setContent(fs.readFileSync(`${root}/notification.html`, 'utf8'));
    await notification.screenshot({ path: `${root}/notification-collapsed.png` });
    await notification.locator('summary').click();
    await notification.screenshot({ path: `${root}/notification-expanded.png`, fullPage: true });
    fs.writeFileSync(`${root}/ui-report.json`, JSON.stringify(report, null, 2));
    console.log(JSON.stringify({ passed: report.length, screenshots: root }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
