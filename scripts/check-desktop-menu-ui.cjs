// Local read-only fixtures: this navigation check never contacts a real account.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.DESKTOP_MENU_UI_URL || 'http://127.0.0.1:5174';

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const values of [
      { width: 900, height: 640, user: null },
      { width: 1024, height: 768, user: { role: 'user', telegram_id: null } },
      { width: 1440, height: 1000, user: { role: 'user', telegram_id: 777 } },
      { width: 1440, height: 900, user: { role: 'admin', telegram_id: 777 } },
      { width: 1440, height: 900, user: { role: 'superadmin', telegram_id: 777 } },
    ]) {
      const context = await browser.newContext({ viewport: { width: values.width, height: values.height }, reducedMotion: 'reduce' });
      await context.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'completed' })));
      await context.route('https://telegram.org/**', route => route.abort());
      const errors = [], mutations = [];
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/api/**', route => {
        const path = new URL(route.request().url()).pathname;
        if (route.request().method() !== 'GET' && !path.startsWith('/api/analytics/')) mutations.push(path);
        if (path === '/api/auth/me') return route.fulfill(values.user ? { json: { id: 777, email: 'local@example.test', email_verified: true, display_name: 'Local member', ...values.user } } : { status: 401, json: { detail: 'Guest' } });
        const json = {
          '/api/settings': { timezone: 'Europe/Moscow' }, '/api/next-race': { status: 'none' },
          '/api/season': { races: [] }, '/api/drivers': { drivers: [] }, '/api/constructors': { constructors: [] },
        }[path] || { status: 'none', items: [], entries: [], results: [], unread: 0 };
        return route.fulfill({ json });
      });
      await page.goto(`${base}/privacy`);
      const header = page.locator('.app-header');
      await header.getByRole('heading', { name: 'Гонки', exact: true }).waitFor();
      if (values.user) {
        const personal = header.getByRole('button', { name: 'Мой профиль', exact: true });
        await personal.click();
        await header.getByRole('link', { name: 'Настройки', exact: true }).waitFor();
        assert.equal(await header.getByRole('link', { name: 'Избранное', exact: true }).count(), values.user.telegram_id ? 1 : 0);
        assert.equal(await header.getByRole('link', { name: 'Уведомления', exact: true }).count(), values.user.telegram_id ? 1 : 0);
        await personal.click();
      } else await header.getByText('Гостевой режим', { exact: true }).waitFor();
      assert.deepEqual(await header.locator('.app-header-section-label').allTextContents(), ['Гонки','Прогнозы и статистика','Сообщество','Личное и справка']);
      assert.equal(await header.locator('a .app-header-link-arrow').count(), 0);
      assert.equal(await header.locator('button[aria-expanded] .app-header-link-arrow').count(), await header.locator('button[aria-expanded]').count());
      for (const icon of ['social','games','help']) {
        const image = header.locator(`.is-${icon} img`);
        await image.evaluate(el => el.decode());
        assert.equal(await image.evaluate(el => el.naturalWidth), 128);
      }
      const social = header.getByRole('button', { name: 'С друзьями', exact: true });
      await social.click();
      assert.equal(await header.getByRole('link', { name: 'Голосование', exact: true }).count(), values.user?.telegram_id ? 1 : 0);
      await social.click();
      const management = header.getByRole('button', { name: 'Управление', exact: true });
      const isAdmin = ['admin','superadmin'].includes(values.user?.role);
      assert.equal(await management.count(), isAdmin ? 1 : 0);
      if (isAdmin) {
        await management.click();
        assert.equal(await header.getByRole('link', { name: 'Админ-панель', exact: true }).count(), 1);
        assert.equal(await header.getByRole('link', { name: 'Аналитика предсказаний', exact: true }).count(), 1);
        await management.click();
      }
      await page.goto(`${base}/history`);
      const comparison = header.getByRole('button', { name: 'Сравнение', exact: true });
      await header.getByRole('link', { name: 'История сезонов', exact: true }).waitFor();
      assert.equal(await comparison.getAttribute('aria-expanded'), 'true');
      assert.equal(await header.getByRole('link', { name: 'История сезонов', exact: true }).getAttribute('aria-current'), 'page');
      assert.equal(await header.locator('[aria-current="page"]').count(), 1);
      await comparison.click();
      assert.equal(await comparison.getAttribute('aria-expanded'), 'false', 'Even the active group must be collapsible');
      assert.equal(await header.getByRole('link', { name: 'История сезонов', exact: true }).count(), 0);
      await comparison.press('Space');
      assert.equal(await comparison.getAttribute('aria-expanded'), 'true');
      await page.goto(`${base}/drivers`);
      await header.getByRole('link', { name: 'Пилоты', exact: true }).waitFor();
      assert.equal(await header.getByRole('button', { name: 'Пелотон', exact: true }).getAttribute('aria-expanded'), 'true');
      assert.equal(await header.locator('[aria-current="page"]').count(), 1);
      await header.getByRole('link', { name: 'Уик-энд', exact: true }).click();
      await page.waitForURL(`${base}/next-race`);
      await header.locator('a[href="/next-race"][aria-current="page"]').waitFor();
      assert.equal(await header.getByRole('link', { name: 'Уик-энд', exact: true }).getAttribute('aria-current'), 'page');
      assert.equal(await header.getByRole('link', { name: 'Календарь', exact: true }).getAttribute('aria-current'), null);
      const help = header.getByRole('button', { name: 'Помощь', exact: true });
      await help.click();
      await header.getByRole('button', { name: 'Короткое знакомство', exact: true }).waitFor();
      assert.equal(await header.getByRole('link', { name: 'Обратная связь', exact: true }).count(), 1);
      const layout = await header.evaluate(el => {
        const clipped = [...el.querySelectorAll('a,button,h2')].filter(control => {
          const r = control.getBoundingClientRect(), boundary = el.getBoundingClientRect();
          return r.width && (r.left < boundary.left - 1 || r.right > boundary.right + 1 || control.scrollWidth > control.clientWidth + 1);
        });
        return { overflow: document.documentElement.scrollWidth > innerWidth, clipped: clipped.map(el => el.textContent) };
      });
      assert.deepEqual(layout, { overflow: false, clipped: [] });
      if (values.width === 1440 && values.user?.role === 'user') await header.screenshot({ path: 'artifacts/desktop-menu-balanced.png' });
      assert.deepEqual(errors, []);
      assert.deepEqual(mutations, []);
      console.log(`${values.width}x${values.height} ${values.user?.role || 'guest'}: grouping, icons, permissions, active state, collapse/keyboard, help and layout passed`);
      await context.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
