// Isolated browser checks for registration, immediate profile access and email onboarding.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/sevag/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');
const base = process.env.PROFILE_UI_URL || 'http://127.0.0.1:5176';
const defaultAvatar = { helmet: 'scarlet', suit: 'scarlet', background: 'garage' };

(async () => {
  fs.mkdirSync('.tmp/registration-ui', { recursive: true });
  execFileSync(process.env.PYTHON_EXECUTABLE || '.venv/Scripts/python.exe', ['-c',
    "from pathlib import Path; from app.utils.portrait_render import render_head_crop_png_bytes; [Path(f'.tmp/registration-ui/{code}.png').write_bytes(render_head_crop_png_bytes(Path(f'app/assets/2026/pilots/{code}.webp'))) for code in ['NOR', 'LEC', 'ANT', 'VER', 'HAM', 'PIA', 'ALB']]"]);
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
        const url = new URL(route.request().url());
        const path = url.pathname;
        const season = new Date().getFullYear() - (width === 768 ? 1 : 0);
        if (width === 768 && Number(url.searchParams.get('season')) !== season && ['/api/drivers', '/api/constructors'].includes(path)) {
          return route.fulfill({ json: { drivers: [], constructors: [] } });
        }
        if (path === '/api/auth/me') return route.fulfill(signedIn ? { json: user } : { status: 401, json: { detail: 'Войдите' } });
        if (path === '/api/drivers') return route.fulfill({ json: { drivers: [
          { code: 'NOR', name: 'Ландо Норрис' }, { code: 'LEC', name: 'Шарль Леклер' },
          { code: 'ANT', name: 'Andrea Kimi Antonelli' }, { code: 'VER', name: 'Max Verstappen' },
          { code: 'HAM', name: 'Lewis Hamilton' }, { code: 'PIA', name: 'Oscar Piastri' }, { code: 'ALB', name: 'Alexander Albon' },
        ] } });
        if (path === '/api/constructors') return route.fulfill({ json: { constructors: [
          { name: 'McLaren', constructorId: 'mclaren' }, { name: 'Ferrari', constructorId: 'ferrari' },
          { name: 'Aston Martin', constructorId: 'aston_martin' }, { name: 'Red Bull Racing', constructorId: 'red_bull' },
          { name: 'Mercedes', constructorId: 'mercedes' },
        ] } });
        if (path === '/api/pilot-portrait') {
          assert.equal(Number(url.searchParams.get('season')), season, 'portraits match the loaded roster season');
          const code = new URL(route.request().url()).searchParams.get('code');
          if (width === 320 && code === 'ANT') return route.fulfill({ status: 404 });
          return route.fulfill({ contentType: 'image/png', body: fs.readFileSync(`.tmp/registration-ui/${code}.png`) });
        }
        if (path === '/api/team-logo') {
          assert.equal(Number(url.searchParams.get('season')), season, 'logos match the loaded roster season');
          const name = new URL(route.request().url()).searchParams.get('name');
          if (width === 320 && name === 'Aston Martin') return route.fulfill({ status: 404 });
          return route.fulfill({ contentType: 'image/png', body: fs.readFileSync(`app/assets/2026/team-logos/${name.toUpperCase()}.png`) });
        }
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
      const start = page.getByRole('button', { name: 'Продолжить регистрацию', exact: true });
      const setAutofilledPassword = value => passwordInput.evaluate((input, value) => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }, value);
      await passwordInput.fill('short');
      await page.getByLabel('Email', { exact: true }).focus();
      const passwordError = page.locator('#registration-password-error');
      await passwordError.getByText('Пароль должен содержать не менее 15 символов.', { exact: true }).waitFor();
      await start.click();
      assert.equal(await page.locator('.registration-wizard').count(), 0, 'short typed passwords cannot open the wizard');
      for (const password of ['autofilled1234', '😀'.repeat(8), 'x'.repeat(129)]) {
        await setAutofilledPassword(password);
        assert(await passwordInput.evaluate(input => input.checkValidity()), 'autofill bypasses native length validation');
        await start.click();
        await passwordError.getByText(password.length > 128 ? 'Пароль должен содержать не более 128 символов.' : 'Пароль должен содержать не менее 15 символов.', { exact: true }).waitFor();
        assert.equal(await page.locator('.registration-wizard').count(), 0, 'explicit length validation blocks invalid autofilled passwords');
        assert.equal(await passwordInput.getAttribute('aria-invalid'), 'true');
        assert(await passwordInput.evaluate(input => input === document.activeElement), 'invalid password receives focus');
        assert.equal(registered, null, 'invalid credentials never create an account');
      }
      await passwordInput.fill('Турбо Пилот #26');
      assert.equal(await passwordError.count(), 0, 'correcting a password clears its error immediately');
      await start.click();
      await page.getByRole('dialog', { name: 'Ваш ник', exact: true }).waitFor();
      await page.keyboard.press('Escape');
      await page.locator('.registration-wizard').waitFor({ state: 'detached' });
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
      assert.equal(await page.locator('.registration-step-avatar select').count(), 0);
      assert.equal(await page.locator('.registration-step-avatar input[type=radio]').count(), 11);
      assert.equal(await page.locator('.registration-avatar-check').count(), 0, 'avatar selection uses only highlighting');
      if (width !== 320) {
        const helmet = page.getByRole('radio', { name: 'Кобальт / двойная полоса', exact: true });
        await helmet.focus();
        await page.keyboard.press('Space');
        assert(await helmet.isChecked(), 'keyboard selects a helmet');
        await page.keyboard.press('ArrowRight');
        assert(await page.getByRole('radio', { name: 'Жемчуг / мята', exact: true }).isChecked());
        await page.keyboard.press('ArrowLeft');
        await page.locator('.registration-avatar-choice[title="Графит / мята"]').click();
        await page.locator('.registration-avatar-choice[title="Золотой подиум"]').click();
        assert(await page.getByRole('radio', { name: 'Графит / мята', exact: true }).isChecked());
        assert(await page.getByRole('radio', { name: 'Золотой подиум', exact: true }).isChecked());
        assert.match(await page.getByAltText('Выбранный аватар').getAttribute('src'), /helmet=cobalt.*suit=mint.*background=gold/);
      }
      await page.getByRole('button', { name: 'Назад', exact: true }).click();
      assert.equal(await page.getByLabel('Ник на сайте').inputValue(), 'Турбо Пилот');
      await next.click();
      await page.getByRole('dialog', { name: 'Ваш аватар', exact: true }).waitFor();
      assert.equal(await page.getByRole('radio', { name: width === 320 ? 'Алый / полоса' : 'Кобальт / двойная полоса', exact: true }).isChecked(), true);
      assert(await page.locator('.registration-step-avatar').evaluate(el => el.scrollWidth <= el.clientWidth), `avatar choices overflow at ${width}`);
      await page.screenshot({ path: `.tmp/registration-ui/avatar-step-${width}.png` });
      await next.click();
      await page.getByRole('dialog', { name: 'Избранные пилоты', exact: true }).waitFor();
      const verifyCards = async (kind, count) => {
        const grid = page.locator('.registration-favorites-grid');
        assert.equal(await grid.locator('label').count(), count);
        const boxes = await grid.locator('label').evaluateAll(cards => cards.map(card => {
          const rect = card.getBoundingClientRect();
          return { x: rect.x, y: rect.y, width: rect.width };
        }));
        assert.equal(boxes[0].y, boxes[1].y, `${kind}: first two cards share a row`);
        assert.equal(boxes[1].y, boxes[2].y, `${kind}: three cards share a row`);
        assert(boxes[3].y > boxes[0].y, `${kind}: fourth card starts the next row`);
        assert(boxes.every(box => box.width >= 44), `${kind}: cards remain touchable`);
        assert(await grid.evaluate(el => el.scrollWidth <= el.clientWidth), `${kind}: no overflow at ${width}`);
        assert(await grid.locator('input').evaluateAll(inputs => inputs.every(input => getComputedStyle(input).clipPath === 'inset(50%)')), `${kind}: checkbox marks are hidden`);
        assert(await grid.locator('label').evaluateAll(cards => cards.every(card =>
          getComputedStyle(card).backgroundColor === (card.querySelector('input').checked ? 'rgb(68, 35, 42)' : 'rgb(16, 18, 20)'))), `${kind}: selected cards use red highlighting`);
        await grid.locator('img').first().waitFor();
        await page.waitForFunction(() => {
          const image = document.querySelector('.registration-favorites-grid img');
          return image?.complete && image.naturalWidth > 0;
        });
        if (width === 320) await grid.locator('.registration-favorite-placeholder').waitFor();
        await grid.locator('img').evaluateAll(images => Promise.all(images.map(image => image.decode().catch(() => {}))));
        await page.screenshot({ path: `.tmp/registration-ui/${kind}-step-${width}.png` });
      };
      if (width !== 320) {
        const driver = page.getByRole('checkbox', { name: 'Ландо Норрис NOR' });
        await driver.focus();
        await page.keyboard.press('Space');
        assert(await driver.isChecked(), 'keyboard selects a driver card');
        const leclerc = page.getByRole('checkbox', { name: 'Шарль Леклер LEC' });
        await leclerc.locator('..').click();
        assert(await leclerc.isChecked(), 'clicking a card selects it');
        await leclerc.locator('..').click();
        assert.equal(await leclerc.isChecked(), false, 'clicking again clears selection');
        await leclerc.locator('..').click();
      }
      await verifyCards('drivers', 7);
      await next.click();
      await page.getByRole('dialog', { name: 'Избранные команды', exact: true }).waitFor();
      if (width !== 320) {
        await page.getByRole('checkbox', { name: 'McLaren' }).locator('..').click();
        await page.getByRole('checkbox', { name: 'Ferrari', exact: true }).locator('..').click();
      }
      await verifyCards('teams', 5);
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
      console.log(`${width}px PASS: three-column photo cards, favorites selection, registration, email tour, resend countdown, cooldown after reload, unverified login`);
      await page.close();
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
