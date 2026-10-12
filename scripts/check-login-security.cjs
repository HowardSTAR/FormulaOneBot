// Browser regressions for login throttling and recovery-token privacy. No real accounts/mail.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/sevag/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.PROFILE_UI_URL || 'http://127.0.0.1:5177';

(async () => {
  fs.mkdirSync('.tmp/login-security', { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const width of [320, 390, 768, 1440]) {
      const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
      const start = new Date('2026-10-12T12:00:00Z').getTime();
      await page.clock.install({ time: new Date(start) });
      await page.clock.setFixedTime(new Date(start));
      let elapsed = 0;
      const advance = async milliseconds => {
        elapsed += milliseconds;
        await page.clock.setFixedTime(new Date(start + elapsed));
        await page.clock.fastForward(1000);
      };
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'skipped' })));
      let attempts = 0, recovery = 0, reset = null;
      await page.route('**/api/**', route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/auth/me') return route.fulfill({ status: 401, json: { detail: 'Войдите' } });
        if (path === '/api/auth/login') {
          attempts++;
          return route.fulfill(attempts >= 8
            ? { status: 429, headers: { 'Retry-After': '900' }, json: { detail: { code: 'rate_limit_exceeded', message: 'Вход временно заблокирован', retry_after: 900, scope: attempts === 9 ? 'ip' : 'account' } } }
            : { status: 401, json: { detail: { message: 'Неверный email или пароль' } } });
        }
        if (path === '/api/auth/password/forgot') { recovery++; return route.fulfill({ status: 202, json: { message: 'Если аккаунт существует, письмо отправлено.' } }); }
        if (path === '/api/auth/password/reset') { reset = route.request().postDataJSON(); return route.fulfill({ json: { message: 'Пароль изменён' } }); }
        return route.fulfill({ json: path === '/api/next-race' ? { status: 'season_finished' } : {} });
      });
      await page.goto(base + '/account');
      await page.getByLabel('Email', { exact: true }).fill('locked@example.test');
      await page.getByLabel('Пароль', { exact: true }).fill('wrong password');
      for (let attempt = 1; attempt <= 8; attempt++) {
        await page.getByRole('button', { name: 'Войти', exact: true }).click();
        if (attempt < 8) await page.getByText('Неверный email или пароль', { exact: true }).waitFor();
        await page.getByRole('button', { name: attempt < 8 ? 'Войти' : 'Войти через 15:00', exact: true }).waitFor();
      }
      const blocked = page.getByRole('button', { name: /^Войти через/ });
      assert(await blocked.isDisabled());
      await page.getByLabel('Пароль', { exact: true }).press('Enter');
      assert.equal(attempts, 8);
      assert(await page.getByRole('button', { name: 'Забыли пароль?', exact: true }).isEnabled());
      await page.getByRole('button', { name: 'Забыли пароль?', exact: true }).click();
      await page.getByRole('button', { name: 'Отправить ссылку', exact: true }).click();
      await page.getByText('Если аккаунт существует, письмо отправлено.', { exact: true }).waitFor();
      assert.equal(recovery, 1);
      await page.getByRole('button', { name: 'Вернуться ко входу', exact: true }).click();
      await advance(60000);
      assert.equal(await blocked.textContent(), 'Войти через 14:00');
      await page.reload();
      await page.getByLabel('Email', { exact: true }).fill('  LOCKED@example.test  ');
      assert.equal(await blocked.textContent(), 'Войти через 14:00');
      assert.equal(await page.getByLabel('Пароль', { exact: true }).inputValue(), '');
      await page.getByLabel('Email', { exact: true }).fill('other@example.test');
      assert(await page.getByRole('button', { name: 'Войти', exact: true }).isEnabled());
      await page.getByLabel('Email', { exact: true }).fill('locked@example.test');
      await advance(839000);
      assert.equal(await blocked.textContent(), 'Войти через 00:01');
      assert(await blocked.isDisabled());
      assert(await page.locator('.account-auth-card').evaluate(el => el.scrollWidth <= el.clientWidth));
      await page.screenshot({ path: `.tmp/login-security/cooldown-${width}.png`, fullPage: true });
      await advance(1000);
      assert(await page.getByRole('button', { name: 'Войти', exact: true }).isEnabled());
      await page.getByLabel('Пароль', { exact: true }).fill('correct password');
      await page.getByRole('button', { name: 'Войти', exact: true }).click();
      await blocked.waitFor();
      await page.getByLabel('Email', { exact: true }).fill('other@example.test');
      assert(await blocked.isDisabled(), 'IP cooldown covers different email addresses');

      const token = 'reset-token-secret-' + 'x'.repeat(48);
      await page.goto(base + '/reset-password?token=' + token);
      await page.getByLabel('Новый пароль', { exact: true }).waitFor();
      assert(!page.url().includes('token='));
      assert.equal(await page.locator('meta[name=referrer]').getAttribute('content'), 'no-referrer');
      await page.getByLabel('Новый пароль', { exact: true }).fill('Новая секретная фраза гонщика');
      await page.getByLabel('Повторите новый пароль', { exact: true }).fill('Новая секретная фраза гонщика');
      await page.getByRole('button', { name: 'Сохранить новый пароль', exact: true }).click();
      await page.getByRole('heading', { name: 'Пароль изменён', exact: true }).waitFor();
      assert.equal(reset.token, token, 'Removing URL token must not lose it before submission');
      assert.equal(reset.new_password, 'Новая секретная фраза гонщика');
      assert.deepEqual(errors, []);
      console.log(`${width}px PASS: cooldown, Enter guard, reload, account/IP scope, recovery, expiry, token privacy`);
      await page.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
