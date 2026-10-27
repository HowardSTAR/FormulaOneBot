// Uses the isolated preview; no production accounts or records are modified.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { mkdirSync } = require('node:fs');
const base = process.env.GAMES_UI_URL || 'http://127.0.0.1:5173';
const output = process.env.GAMES_UI_OUTPUT || '.tmp/games-design';
const fixture = `${base}/tests/home-design-preview.html`;
mkdirSync(output, { recursive: true });
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  let checks = 0;
  try {
    for (const game of ['reaction-game', 'reflex-grid-game']) {
      for (const theme of ['light', 'dark']) {
        for (const width of [320, 390, 899, 900, 1440]) {
          const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
          const errors = [];
          page.on('pageerror', error => errors.push(error.message));
          await page.goto(`${fixture}?page=${game}&theme=${theme}&auth=member&state=games-save-error`);
          const prompt = page.getByRole('dialog');
          await prompt.waitFor();
          assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
          const bounds = await prompt.boundingBox();
          assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width + 1);
          assert.ok(await prompt.locator('h2').evaluate(e => getComputedStyle(e).textTransform === 'none'));
          await prompt.getByLabel('Участвовать', { exact: true }).check();
          await prompt.getByLabel('Имя в таблице', { exact: true }).fill('Новый игрок');
          await prompt.getByRole('button', { name: 'Продолжить', exact: true }).click();
          await prompt.getByRole('alert').waitFor();
          assert.equal(await prompt.getByLabel('Имя в таблице', { exact: true }).inputValue(), 'Новый игрок');
          await prompt.getByRole('button', { name: 'Продолжить', exact: true }).click();
          await prompt.waitFor({ state: 'detached' });
          await page.getByText('Сейчас: участвуешь • Новый игрок', { exact: true }).waitFor();
          assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
          if ([390, 1440].includes(width)) await page.screenshot({ path: `${output}/${game}-${theme}-${width}.png`, fullPage: true });
          await page.getByRole('link', { name: 'Лидеры', exact: true }).click();
          await page.locator('.reaction-row').first().waitFor();
          assert.equal(await page.locator('.reaction-row').count(), 3);
          assert.equal(await page.getByRole('link', { name: 'Лидеры', exact: true }).getAttribute('aria-current'), 'page');
          assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
          assert.deepEqual(errors, []);
          await page.getByRole('link', { name: 'Игра', exact: true }).click();
          const action = game === 'reaction-game' ? page.locator(width < 900 ? '.reaction-mobile-scene .reaction-button' : '.reaction-desktop-start') : page.locator('.reflex-tile.active');
          await action.click();
          assert.equal(await page.evaluate(() => document.body.style.position), 'fixed');
          const exit = page.getByRole('link', { name: 'Выйти из игры', exact: true });
          const exitBounds = await exit.boundingBox();
          assert.ok(exitBounds.y >= 0 && exitBounds.y + exitBounds.height <= 1000);
          await exit.click();
          await page.locator('.game-page').waitFor({ state: 'detached' });
          assert.notEqual(await page.evaluate(() => document.body.style.position), 'fixed');
          await page.locator('.home-screen').waitFor();
          await page.close(); checks++;
        }
        const page = await browser.newPage({ viewport: { width: 390, height: 900 }, reducedMotion: 'reduce' });
        await page.goto(`${fixture}?page=${game}&theme=${theme}&auth=member&state=games-onboarding&scale=2`);
        const prompt = page.getByRole('dialog'); await prompt.waitFor();
        assert.ok(await prompt.evaluate(e => e.scrollWidth <= e.clientWidth + 1));
        await prompt.getByRole('button', { name: 'Продолжить', exact: true }).focus();
        await page.keyboard.press('Tab');
        assert.equal(await prompt.evaluate(e => e.contains(document.activeElement)), true);
        await page.screenshot({ path: `${output}/${game}-prompt-${theme}-scale2.png` });
        await page.keyboard.press('Escape');
        await prompt.waitFor({ state: 'detached' });
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
        await page.close(); checks++;
      }
      const page = await browser.newPage({ viewport: { width: 390, height: 900 } });
      for (const state of ['games-error', 'games-empty', 'games-loading']) {
        await page.goto(`${fixture}?page=${game}&auth=guest&tab=leaderboard&state=${state}`);
        await page.locator('.game-page').waitFor();
        if (state === 'games-error') {
          await page.getByRole('button', { name: 'Повторить загрузку' }).click();
          await page.locator('.reaction-row').first().waitFor();
        } else if (state === 'games-empty') await page.locator('.reaction-leaderboard-empty').filter({hasText:'Пока нет результатов'}).waitFor();
        else { await page.getByText('Загрузка…', { exact: true }).waitFor(); await page.locator('.reaction-row').first().waitFor(); }
        checks++;
      }
      await page.goto(`${fixture}?page=${game}&auth=guest`);
      await page.locator('.game-page').waitFor();
      await page.locator('.reaction-settings-caption').filter({ hasText: 'Войдите' }).waitFor();
      if (game === 'reaction-game') {
        await page.locator('.reaction-mobile-scene .reaction-button').click();
        await page.locator('.reaction-mobile-scene .reaction-button').click();
        await page.getByText('Фальстарт. Нажми', { exact: false }).waitFor();
      } else {
        await page.clock.install();
        await page.locator('.reflex-tile.active').click();
        await page.waitForFunction(() => document.querySelector('.reflex-timer-card')?.getAttribute('data-state') === 'running');
        assert.equal(await page.evaluate(() => document.body.style.position), 'fixed');
        assert.equal(await page.evaluate(() => document.documentElement.style.overflow), 'hidden');
        await page.clock.runFor(11000);
        await page.getByRole('dialog', { name: 'Результат попытки' }).waitFor();
        assert.notEqual(await page.evaluate(() => document.body.style.position), 'fixed');
        await page.getByRole('button', { name: 'Сыграть снова', exact: true }).click();
        assert.equal(await page.locator('.reflex-timer-card').getAttribute('data-state'), 'idle');
      }
      await page.close(); checks++;
    }
    // Phone entry preserves the iframe after starting and changing orientation.
    for (const theme of ['light', 'dark']) {
      const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148' });
      await page.goto(`${fixture}?page=race-game&theme=${theme}`);
      await page.getByRole('heading', { name: 'Emerald Loop', exact: true }).waitFor();
      await page.screenshot({ path: `${output}/emerald-entry-${theme}.png` });
      await page.getByRole('button', { name: 'Играть сейчас', exact: true }).click();
      await page.locator('.race-game-frame').waitFor();
      await page.setViewportSize({ width: 844, height: 390 });
      assert.equal(await page.locator('.race-game-frame').count(), 1);
      await page.close(); checks++;
    }
    console.log(`Passed ${checks} game design and interaction scenarios.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
