// Browser checks use mocked API responses and synthetic credentials only.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/sevag/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.PROFILE_UI_URL || 'http://127.0.0.1:5176';

(async () => {
  fs.mkdirSync('artifacts', { recursive: true });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const setup = async (width, reducedMotion = 'no-preference') => {
    const page = await browser.newPage({ viewport: { width, height: 1100 }, reducedMotion });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error' && /THREE|shader|WebGL/.test(message.text())) errors.push(message.text()); });
    await page.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'skipped' })));
    await page.route('**/api/**', route => route.fulfill({ status: new URL(route.request().url()).pathname === '/api/auth/me' ? 401 : 200, json: {} }));
    return { page, errors };
  };
  try {
    for (const width of [390, 1000]) {
      const { page, errors } = await setup(width);
      const sent = [];
      page.on('request', request => sent.push(request.url() + (request.postData() || '')));
      await page.goto(base + '/account');
      const scene = page.locator('.password-racer');
      await scene.locator('canvas').waitFor();
      await page.waitForFunction(() => document.querySelector('.password-racer')?.dataset.status === 'ready');
      assert.equal(await scene.locator('.password-racer-stage').getAttribute('data-scenery'), 'detailed');
      await scene.screenshot({ path: `artifacts/password-racer-idle-${width}.png` });
      const input = page.getByLabel('Пароль', { exact: true });
      let previousBlur = -1;
      for (const [password, level] of [['lap', 1], ['Fast-lap-72!', 2], ['Летний вираж 726', 3], ['Летний ветер над тихой рекой 72', 4]]) {
        await input.fill(password);
        await page.waitForFunction(level => {
          const stage = document.querySelector('.password-racer-stage');
          return document.querySelector('.password-racer')?.dataset.strength === String(level)
            && Number(stage?.dataset.speed) > [0, .17, .42, .71, .99][level];
        }, level);
        const blur = Number(await scene.locator('.password-racer-stage').getAttribute('data-blur'));
        assert(blur > previousBlur, 'Blur increases with strength'); previousBlur = blur;
        if (level === 2) await scene.screenshot({ path: `artifacts/password-racer-medium-${width}.png` });
      }
      await scene.screenshot({ path: `artifacts/password-racer-max-${width}.png` });
      await page.getByRole('button', { name: 'Показать пароль: Пароль', exact: true }).click();
      assert.equal(await input.getAttribute('type'), 'text');
      assert(await input.evaluate(element => element === document.activeElement));
      await page.waitForFunction(() => Number(document.querySelector('.password-racer-stage')?.dataset.reveal) > .99);
      assert(Number(await scene.locator('.password-racer-stage').getAttribute('data-speed')) > .99);
      await scene.screenshot({ path: `artifacts/password-racer-reveal-${width}.png` });
      await page.getByRole('button', { name: 'Скрыть пароль: Пароль', exact: true }).click();
      await page.waitForFunction(() => Number(document.querySelector('.password-racer-stage')?.dataset.reveal) < .01);
      assert.equal(await input.getAttribute('type'), 'password');
      // Rapid reversals must settle at the latest state.
      for (let i = 0; i < 4; i++) await scene.locator('..').getByRole('button', { name: /пароль: Пароль/ }).click();
      await input.fill('');
      await page.waitForFunction(() => Number(document.querySelector('.password-racer-stage')?.dataset.speed) < .01);
      assert.equal(await scene.getAttribute('data-strength'), '0');
      assert.equal(await scene.locator('[role=meter],.password-racer-heading,.password-racer-caption').count(), 0, 'No visible stages or score badges');
      assert(!sent.join('\n').includes('Летний ветер'), 'Password input must not leave the form');
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.getByRole('button', { name: 'Регистрация', exact: true }).click();
      await page.locator('.password-racer[data-status=ready]').waitFor();
      assert.equal(await page.locator('.password-racer canvas').count(), 1);
      assert.deepEqual(errors, []);
      console.log(`${width}px PASS: five levels, blur, reveal/hide, focus, quick reversals, resize and remount`);
      await page.close();
    }
    const { page, errors } = await setup(320, 'reduce');
    await page.goto(base + '/account');
    await page.locator('.password-racer[data-status=ready]').waitFor();
    await page.getByLabel('Пароль', { exact: true }).fill('Летний ветер над тихой рекой 72');
    await page.getByRole('button', { name: 'Показать пароль: Пароль', exact: true }).click();
    const stage = page.locator('.password-racer-stage');
    assert.equal(await stage.getAttribute('data-reveal'), '1.000');
    assert.equal(await stage.getAttribute('data-blur'), '0.00000');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.locator('.password-racer').screenshot({ path: 'artifacts/password-racer-reduced.png' });
    assert.deepEqual(errors, []); await page.close();
    const fallback = await setup(390);
    await fallback.page.route('**/password-racer.glb', route => route.abort());
    await fallback.page.goto(base + '/account');
    await fallback.page.locator('.password-racer[data-status=fallback] img').waitFor();
    await fallback.page.getByLabel('Пароль', { exact: true }).fill('Still usable');
    await fallback.page.getByRole('button', { name: 'Показать пароль: Пароль', exact: true }).click();
    assert.equal(await fallback.page.getByLabel('Пароль', { exact: true }).getAttribute('type'), 'text');
    assert.deepEqual(fallback.errors, []); await fallback.page.close();
    const trackOnly = await setup(390);
    await trackOnly.page.route('**/password-racer-track.glb', route => route.abort());
    await trackOnly.page.goto(base + '/account');
    await trackOnly.page.locator('.password-racer[data-status=ready]').waitFor();
    assert.equal(await trackOnly.page.locator('.password-racer-stage').getAttribute('data-scenery'), 'track-only');
    await trackOnly.page.getByLabel('Пароль', { exact: true }).fill('Scenery fallback 72');
    await trackOnly.page.getByRole('button', { name: 'Показать пароль: Пароль', exact: true }).click();
    await trackOnly.page.waitForFunction(() => Number(document.querySelector('.password-racer-stage')?.dataset.reveal) > .99);
    assert.deepEqual(trackOnly.errors, []); await trackOnly.page.close();
    console.log('PASS: reduced motion, 320px layout, detailed scenery and graceful fallback after either asset fails');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
