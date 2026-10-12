// Local browser QA with mocked API failures; no real registrations or mail.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/sevag/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.PROFILE_UI_URL || 'http://127.0.0.1:5177';

(async () => {
  fs.mkdirSync('.tmp/russian-errors-ui', { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const width of [320, 390, 768, 1440]) {
      const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'skipped' })));
      let failure = { status: 422, json: { detail: { message: 'Password must contain letters and numbers' } } };
      let offline = false;
      await page.route('**/api/**', route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/auth/me') return route.fulfill({ status: 401, json: { detail: 'Authentication required' } });
        if (path === '/api/auth/register') return offline ? route.abort('failed') : route.fulfill(failure);
        if (path === '/api/auth/password/reset') return route.fulfill({ status: 422, json: { detail: [
          { type: 'string_too_short', loc: ['body', 'new_password'], msg: 'String should have at least 15 characters', input: 'SECRET' },
        ] } });
        return route.fulfill({ json: path === '/api/next-race' ? { status: 'season_finished' } : {} });
      });
      await page.goto(base + '/account');
      await page.getByRole('button', { name: 'Регистрация', exact: true }).click();
      await page.getByLabel('Email', { exact: true }).fill('pilot@example.test');
      await page.getByLabel('Пароль', { exact: true }).fill('Unique long racing phrase');
      await page.getByLabel('Ник на сайте').fill('Турбо Пилот');
      const submit = page.getByRole('button', { name: 'Создать профиль', exact: true });
      await submit.click();
      await page.getByText('Пароль должен содержать буквы и цифры.', { exact: true }).waitFor();
      assert(!(await page.locator('body').innerText()).includes('Password must'));
      await page.getByText('Пароль должен содержать буквы и цифры.', { exact: true }).scrollIntoViewIfNeeded();
      await page.screenshot({ path: `.tmp/russian-errors-ui/registration-${width}.png`, fullPage: true });

      failure = { status: 422, json: { detail: [ { type: 'missing', loc: ['body', 'email'], msg: 'Field required' } ] } };
      await submit.click();
      await page.getByText('Заполните поле «Email».', { exact: true }).waitFor();
      failure = { status: 500, contentType: 'text/html', body: '<html>SECRET backend stack trace</html>' };
      await submit.click();
      await page.getByText('Сервис временно недоступен. Попробуйте повторить запрос позже.', { exact: true }).waitFor();
      assert(!(await page.locator('body').innerText()).includes('SECRET'));
      offline = true;
      await submit.click();
      await page.getByText('Нет соединения с сервером. Проверьте сеть и повторите запрос.', { exact: true }).waitFor();

      await page.goto(base + '/reset-password?token=' + 'x'.repeat(64));
      await page.getByLabel('Новый пароль', { exact: true }).fill('Новая секретная фраза гонщика');
      await page.getByLabel('Повторите новый пароль', { exact: true }).fill('Новая секретная фраза гонщика');
      await page.getByRole('button', { name: 'Сохранить новый пароль', exact: true }).click();
      await page.getByText('Поле «Новый пароль» должно содержать не менее 15 символов.', { exact: true }).waitFor();
      assert(!(await page.locator('body').innerText()).includes('SECRET'));
      assert.deepEqual(errors, []);
      console.log(`${width}px PASS: legacy password error, validation, server failure, offline, shared reset errors in Russian`);
      await page.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
