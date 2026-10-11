// Manual Boosty check inside the editor: unlocks, paid dates, errors and unsaved choices.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.PROFILE_UI_URL || 'http://127.0.0.1:5174';

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const width of [320, 390, 1440]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      let tier = 0, nextTier = 3, checks = 0, failCheck = false, failProfile = false;
      let avatarWrites = 0, styleWrites = 0;
      const initialStyle = { frame: 'classic', color: 'white', background: 'carbon' };
      const status = () => ({
        eligible: true, configured: true, active: tier > 0, blog_url: 'https://boosty.to/turbotears',
        level_name: tier ? 'Полный газ' : null, checked_at: checks ? Date.now() / 1000 : null,
        check_failed: false, premium_active: tier > 0, premium_override: null,
        expires_at: tier ? Date.parse('2027-11-11T12:00:00Z') / 1000 : null,
        can_check: true, check_unavailable_reason: null,
      });
      await page.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'skipped' })));
      await page.route('**/api/**', async route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/account/boosty/check') {
          checks++;
          await new Promise(resolve => setTimeout(resolve, 150));
          if (failCheck) return route.fulfill({ status: 503, json: { detail: 'Upstream offline' } });
          tier = nextTier;
          return route.fulfill({ json: status() });
        }
        if (path === '/api/account/boosty') return route.fulfill({ json: status() });
        if (path === '/api/auth/me') return route.fulfill({ json: { id: 1, email: 'racer@example.test', email_verified: true, telegram_id: 2099386, role: 'user' } });
        if (path === '/api/profiles/avatar/v1.png') return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="88" height="88"><rect width="88" height="88" fill="#394"/></svg>' });
        if (path.endsWith('/trophies')) return route.fulfill({ json: { user_id: 1, season: 2026, families: [], earned: [], pending: [], badge: null } });
        if (path === '/api/profiles/me/avatar') { avatarWrites++; return route.fulfill({ json: { saved: true } }); }
        if (path === '/api/profiles/me/style') { styleWrites++; return route.fulfill({ json: { saved: true } }); }
        if (path === '/api/profiles/me') {
          if (failProfile) return route.fulfill({ status: 503, json: {} });
          return route.fulfill({ json: {
            user_id: 1, display_name: 'Тестовый гонщик', is_owner: true, profile_guide_seen: true,
            tier, tier_name: tier ? 'Полный газ' : 'Участник', supporter: tier > 0, style: initialStyle,
            options: { frame: { classic: 0, red: 2, gold: 3 }, color: { white: 0, mint: 3 }, background: { carbon: 0, champion: 3 } },
            avatar: { helmet: 'scarlet', suit: 'scarlet', background: 'garage' },
            avatar_options: { helmet: { scarlet: 'Алый / полоса', cobalt: 'Кобальт / двойная полоса' }, suit: { scarlet: 'Алый / графит' }, background: { garage: 'Ночной бокс' } },
            season: 2026, seasons: [2026], total_points: 0, scored_rounds: 0,
            best_prediction: null, predictions: [], records: [], favorites: { drivers: [], teams: [] },
          } });
        }
        return route.fulfill({ json: {} });
      });
      await page.goto(base + '/profile');
      await page.getByRole('button', { name: 'Аватар и оформление', exact: true }).click();
      const editor = page.getByRole('dialog', { name: 'Аватар и оформление' });
      const check = editor.getByRole('button', { name: 'Проверить подписку', exact: true });
      await editor.getByText('Подписка ещё не проверена.', { exact: true }).waitFor();
      assert.equal(checks, 0, 'Opening the editor only reads the saved status');
      assert.equal(await editor.getByRole('button', { name: 'Золото · 🔒', exact: true }).isDisabled(), true);
      await editor.getByRole('button', { name: 'Кобальт / двойная полоса' }).click();
      await check.click();
      await editor.getByRole('button', { name: 'Проверяем подписку…' }).waitFor();
      assert.equal(await editor.getByRole('button', { name: 'Сохранить изменения' }).isDisabled(), true);
      await editor.getByText('Подписка «Полный газ» активна до 11.11.2027.', { exact: true }).waitFor();
      await check.waitFor({ state: 'visible' });
      await page.waitForFunction(() => !document.querySelector('.avatar-editor-subscription-check').disabled);
      assert.equal(checks, 1);
      assert.equal(await editor.getByRole('button', { name: 'Золото', exact: true }).isDisabled(), false);
      assert.equal(await editor.getByRole('button', { name: 'Кобальт / двойная полоса' }).getAttribute('aria-pressed'), 'true');
      assert.equal(avatarWrites + styleWrites, 0, 'A check does not save drafts');
      const styleSection = editor.locator('.avatar-editor-style');
      await styleSection.scrollIntoViewIfNeeded();
      assert.ok(await editor.evaluate(el => el.scrollWidth <= el.clientWidth), `Editor overflow at ${width}`);
      assert.ok(await editor.locator('.avatar-editor-subscription-actions').evaluate(el => [...el.children].every(child => {
        const bounds = child.getBoundingClientRect(), parent = el.getBoundingClientRect();
        return bounds.left >= parent.left - 1 && bounds.right <= parent.right + 1 && bounds.height >= 44;
      })), `Subscription actions fit and remain tappable at ${width}`);
      assert.ok(await editor.locator('.avatar-editor-subscription-status').evaluate(el => el.getBoundingClientRect().top >= document.querySelector('.avatar-editor-style .profile-customize').getBoundingClientRect().bottom));
      await page.screenshot({ path: `artifacts/profile-subscription-${width}.png` });
      await editor.evaluate(el => { el.scrollTop = el.scrollHeight; });
      assert.ok(await editor.locator('.avatar-editor-subscription-status').evaluate(el => {
        const bounds = el.getBoundingClientRect();
        const footer = document.querySelector('.avatar-editor footer').getBoundingClientRect();
        return bounds.bottom <= footer.top + 1;
      }), 'Paid end date can be read above the sticky footer');
      await page.screenshot({ path: `artifacts/profile-subscription-status-${width}.png` });
      failCheck = true;
      await check.click();
      await editor.getByRole('alert').waitFor();
      assert.equal(await editor.getByText('Подписка «Полный газ» активна до 11.11.2027.').count(), 1);
      assert.equal(await editor.getByRole('button', { name: 'Золото', exact: true }).isDisabled(), false);
      failCheck = false; failProfile = true;
      await check.click();
      await editor.getByRole('alert').filter({ hasText: 'Подписка проверена, но оформление не удалось обновить' }).waitFor();
      failProfile = false;
      await editor.getByRole('button', { name: 'Золото', exact: true }).click();
      nextTier = 0;
      await check.click();
      await page.waitForFunction(() => !document.querySelector('.avatar-editor-subscription-check').disabled);
      assert.equal(await editor.getByRole('button', { name: 'Золото · 🔒', exact: true }).isDisabled(), true);
      assert.equal(await editor.getByRole('button', { name: 'Классика', exact: true }).getAttribute('aria-pressed'), 'true');
      assert.equal(await editor.getByRole('button', { name: 'Кобальт / двойная полоса' }).getAttribute('aria-pressed'), 'true');
      await editor.getByRole('button', { name: 'Сохранить изменения' }).click();
      await editor.waitFor({ state: 'detached' });
      assert.equal(avatarWrites, 1);
      assert.equal(styleWrites, 0, 'Subscription changes do not rewrite the saved style');
      assert.deepEqual(errors, []);
      await page.close();
    }
    console.log('Manual subscription checks: 3 widths; activation, expiry text, drafts, downgrade and failure recovery passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
