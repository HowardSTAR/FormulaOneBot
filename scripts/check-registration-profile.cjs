// Isolated browser checks for registration, immediate profile access and email onboarding.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/sevag/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.PROFILE_UI_URL || 'http://127.0.0.1:5176';
const defaultAvatar = { helmet: 'scarlet', suit: 'scarlet', background: 'garage' };

(async () => {
  fs.mkdirSync('.tmp/registration-ui', { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const width of [320, 390, 768, 1440]) {
      const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
      await page.clock.install();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      let user = null, registered = null, seen = false, resent = 0, signedIn = false;
      let cooldownSeconds = width === 320 ? 0 : 60;
      await page.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'skipped' })));
      await page.route('**/api/**', route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/auth/me') return route.fulfill(signedIn ? { json: user } : { status: 401, json: { detail: 'Войдите' } });
        if (path === '/api/drivers') return route.fulfill({ json: { drivers: [{ code: 'NOR', name: 'Ландо Норрис' }, { code: 'LEC', name: 'Шарль Леклер' }] } });
        if (path === '/api/constructors') return route.fulfill({ json: { constructors: [{ name: 'McLaren' }, { name: 'Ferrari' }] } });
        if (path === '/api/auth/register') {
          registered = route.request().postDataJSON();
          signedIn = true;
          user = { id: 71, email: registered.email, display_name: registered.display_name, email_verified: false, telegram_id: null, role: 'user' };
          return route.fulfill({ status: 202, json: { user, csrf_token: 'registration-csrf', email_sent: width !== 320 } });
        }
        if (path === '/api/auth/login') { signedIn = true; return route.fulfill({ json: { user, csrf_token: 'login-csrf' } }); }
        if (path === '/api/auth/verification-status') return route.fulfill({ json: { retry_after: cooldownSeconds } });
        if (path === '/api/auth/resend-verification') { resent++; cooldownSeconds = 60; return route.fulfill({ status: 202, json: { email: user.email, retry_after: 60 } }); }
        if (path === '/api/auth/verify-email') {
          assert.equal(route.request().postDataJSON().email, user.email);
          if (route.request().postDataJSON().code !== '123456') return route.fulfill({ status: 401, json: { detail: { message: 'Неверный код из письма' } } });
          user = { ...user, email_verified: true };
          return route.fulfill({ json: { user, csrf_token: 'verified-csrf' } });
        }
        if (path === '/api/profiles/me/guide') { seen = true; return route.fulfill({ json: { saved: true } }); }
        if (path === '/api/profiles/avatar/v1.png') return route.fulfill({ contentType: 'image/png', body: fs.readFileSync('app/profile_avatar_assets/cobalt-v1.png') });
        if (path === '/api/profiles/me') return route.fulfill({ json: {
          user_id: user.id, display_name: user.display_name, email: user.email, email_verified: user.email_verified,
          is_owner: true, profile_guide_seen: seen, tier: 0, tier_name: 'Участник', supporter: false,
          style: { frame: 'classic', color: 'white', background: 'carbon' },
          options: { frame: { classic: 0 }, color: { white: 0 }, background: { carbon: 0 } },
          avatar: registered.avatar, avatar_options: { helmet: { scarlet: 'Алый' }, suit: { scarlet: 'Алый' }, background: { garage: 'Бокс' } },
          season: 2026, seasons: [2026], best_prediction: null, predictions: [], records: [], total_points: 0, scored_rounds: 0,
          favorites: { drivers: registered.favorite_drivers, teams: registered.favorite_teams },
        } });
        if (path.endsWith('/trophies')) return route.fulfill({ json: { user_id: 71, season: 2026, families: [], pending: [], earned: [], badge: null } });
        return route.fulfill({ json: path === '/api/next-race' ? { status: 'season_finished' } : {} });
      });
      await page.goto(base + '/account?returnTo=predictions');
      const passwordInput = page.getByLabel('Пароль', { exact: true });
      await passwordInput.fill('FormulaOne-2026-Secure');
      await page.getByRole('button', { name: 'Показать пароль: Пароль', exact: true }).click();
      assert.equal(await passwordInput.getAttribute('type'), 'text');
      assert.equal(await passwordInput.inputValue(), 'FormulaOne-2026-Secure');
      await page.getByRole('button', { name: 'Регистрация', exact: true }).click();
      assert.equal(await passwordInput.getAttribute('type'), 'password', 'switching forms masks the password again');
      await page.getByLabel('Email', { exact: true }).fill('racer@example.test');
      await page.getByLabel('Пароль', { exact: true }).fill('FormulaOne-2026-Secure');
      await page.getByRole('button', { name: 'Показать пароль: Пароль', exact: true }).click();
      assert.equal(await passwordInput.getAttribute('type'), 'text');
      await page.keyboard.type('7');
      assert.equal(await passwordInput.inputValue(), 'FormulaOne-2026-Secure7', 'typing continues in the password field');
      await page.keyboard.press('Backspace');
      await page.getByRole('button', { name: 'Скрыть пароль: Пароль', exact: true }).click();
      assert.equal(await passwordInput.getAttribute('type'), 'password');
      assert.equal(await passwordInput.inputValue(), 'FormulaOne-2026-Secure');
      assert.equal(await page.getByLabel('Ник на сайте').count(), 0, 'profile fields are not underneath the credentials');
      const start = page.getByRole('button', { name: 'Продолжить регистрацию', exact: true });
      await start.click();
      const wizard = page.getByRole('dialog', { name: 'Ваш ник', exact: true });
      await wizard.waitFor();
      await page.getByLabel('Ник на сайте').fill('  ');
      await wizard.getByRole('button', { name: 'Продолжить', exact: true }).click();
      await wizard.getByRole('alert').getByText('Введите ник от 2 до 32 символов.').waitFor();
      await page.getByLabel('Ник на сайте').fill('Турбо Пилот');
      await page.keyboard.press('Escape');
      await wizard.waitFor({ state: 'detached' });
      assert.equal(await start.evaluate(el => el === document.activeElement), true, 'closing returns focus');
      assert.equal(await passwordInput.inputValue(), 'FormulaOne-2026-Secure');
      await start.click();
      assert.equal(await page.getByLabel('Ник на сайте').inputValue(), 'Турбо Пилот', 'draft survives closing');
      const next = page.getByRole('button', { name: 'Продолжить', exact: true });
      await next.click();
      await page.getByRole('dialog', { name: 'Ваш аватар', exact: true }).waitFor();
      if (width !== 320) {
        await page.getByLabel('Шлем', { exact: true }).selectOption('cobalt');
        await page.getByLabel('Комбинезон', { exact: true }).selectOption('mint');
        await page.getByLabel('Фон', { exact: true }).selectOption('gold');
      }
      await page.getByRole('button', { name: 'Назад', exact: true }).click();
      assert.equal(await page.getByLabel('Ник на сайте').inputValue(), 'Турбо Пилот');
      await next.click();
      await page.getByRole('dialog', { name: 'Ваш аватар', exact: true }).waitFor();
      assert.equal(await page.getByLabel('Шлем', { exact: true }).inputValue(), width === 320 ? 'scarlet' : 'cobalt');
      await page.screenshot({ path: `.tmp/registration-ui/avatar-step-${width}.png` });
      await next.click();
      await page.getByRole('dialog', { name: 'Избранные пилоты', exact: true }).waitFor();
      if (width !== 320) {
        await page.getByRole('checkbox', { name: 'Ландо Норрис NOR' }).check();
        await page.getByRole('checkbox', { name: 'Шарль Леклер LEC' }).check();
      }
      await next.click();
      await page.getByRole('dialog', { name: 'Избранные команды', exact: true }).waitFor();
      if (width !== 320) {
        await page.getByRole('checkbox', { name: 'McLaren' }).check();
        await page.getByRole('checkbox', { name: 'Ferrari', exact: true }).check();
      }
      assert.equal(registered, null, 'no account is created before the final confirmation');
      await page.getByRole('button', { name: 'Назад', exact: true }).click();
      assert.equal(await page.getByRole('checkbox', { name: 'Ландо Норрис NOR' }).isChecked(), width !== 320, 'favorites survive returning to a step');
      await next.click();
      const dialog = page.locator('.registration-wizard');
      assert(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth), `registration overflow at ${width}`);
      const bounds = await dialog.boundingBox();
      assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= 901, 'dialog fits the viewport');
      await page.keyboard.press('Tab');
      assert(await dialog.evaluate(el => el.contains(document.activeElement)), 'focus stays in the modal');
      await page.screenshot({ path: `.tmp/registration-ui/form-${width}.png`, fullPage: true });
      await page.getByRole('button', { name: 'Создать профиль', exact: true }).click();
      await page.waitForURL('**/profile');
      await page.getByRole('heading', { name: 'Профиль готов — подтвердите email', exact: true }).waitFor();
      const guide = page.getByRole('complementary', { name: 'Знакомство с профилем' });
      await guide.getByRole('heading', { name: 'Добро пожаловать в профиль', exact: true }).waitFor();
      assert.equal(registered.display_name, 'Турбо Пилот');
      assert.deepEqual(registered.avatar, width === 320 ? defaultAvatar : { helmet: 'cobalt', suit: 'mint', background: 'gold' });
      assert.deepEqual(registered.favorite_drivers, width === 320 ? [] : ['NOR', 'LEC']);
      assert.deepEqual(registered.favorite_teams, width === 320 ? [] : ['McLaren', 'Ferrari']);
      if (width === 320) await page.getByText('Письмо пока не удалось отправить.', { exact: false }).waitFor();
      await page.screenshot({ path: `.tmp/registration-ui/onboarding-${width}.png` });
      const emailCard = page.locator('.profile-email-verification');
      assert(await emailCard.evaluate(el => el.scrollWidth <= el.clientWidth), `verification overflow at ${width}`);
      await page.getByLabel('Код из письма', { exact: true }).fill('000000');
      await emailCard.getByRole('button', { name: 'Подтвердить email', exact: true }).click();
      await emailCard.getByRole('alert').getByText('Неверный код из письма').waitFor();
      const resendButton = emailCard.getByRole('button', { name: /Прислать письмо заново/ });
      if (width !== 320) {
        assert(await resendButton.isDisabled(), 'initial delivery starts the one-minute countdown');
        assert.match(await resendButton.textContent(), /01:00|00:5\d/);
        await page.clock.fastForward(60_000);
        cooldownSeconds = 0;
      }
      await resendButton.click();
      await emailCard.getByRole('status').getByText('Новый код отправлен.', { exact: false }).waitFor();
      assert.equal(resent, 1);
      assert(await resendButton.isDisabled(), 'resend is disabled after delivery');
      assert.match(await resendButton.textContent(), /01:00|00:5\d/);
      await page.clock.fastForward(1000);
      assert.match(await resendButton.textContent(), /00:5\d/, 'countdown decreases');
      await guide.getByRole('button', { name: 'Закрыть знакомство с профилем' }).click();
      await guide.waitFor({ state: 'detached' });
      await page.reload();
      await emailCard.waitFor();
      assert(await resendButton.isDisabled(), 'reload retains the server cooldown');
      assert.equal(await guide.count(), 0, 'skipping the tour persists independently of verification');
      signedIn = false;
      await page.goto(base + '/account?returnTo=predictions');
      await page.getByLabel('Email', { exact: true }).fill(user.email);
      await page.getByLabel('Пароль', { exact: true }).fill('FormulaOne-2026-Secure');
      await page.getByRole('button', { name: 'Войти', exact: true }).click();
      await page.waitForURL('**/profile');
      await emailCard.waitFor();
      await page.getByLabel('Код из письма', { exact: true }).fill('123456');
      await emailCard.getByRole('button', { name: 'Подтвердить email', exact: true }).click();
      await emailCard.waitFor({ state: 'detached' });
      await page.getByRole('heading', { name: 'Турбо Пилот', exact: true }).waitFor();
      assert.equal(await page.evaluate(() => sessionStorage.getItem('turbotears_csrf')), 'verified-csrf');
      assert.deepEqual(errors, []);
      console.log(`${width}px PASS: password visibility and retained input, registration, email tour, resend countdown, cooldown after reload, unverified login`);
      await page.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
