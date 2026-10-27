// Router errors and recovery are simulated locally; no production requests.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { mkdirSync } = require('node:fs');
const base = process.env.ROUTE_ERROR_UI_URL || 'http://127.0.0.1:5173';
const fixture = `${base}/tests/route-error-preview.html`;
const output = '.tmp/route-error-design';
mkdirSync(output, { recursive: true });
(async () => {
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true });
  try {
    for (const theme of ['light', 'dark']) {
      for (const state of ['error', 'not-found']) {
        for (const width of [320, 390, 759, 760, 1440]) {
          const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
          await page.goto(`${fixture}?theme=${theme}&state=${state}`);
          await page.locator('.route-recovery h1').waitFor();
          await page.locator('.route-recovery-art img').evaluate(image => image.decode());
          assert.equal(await page.locator('h1').innerText(), state === 'not-found' ? 'Страница не найдена' : 'Не удалось открыть страницу');
          assert.equal(await page.locator('.route-recovery').innerText().then(text => /Private diagnostic|internal-preview-module/.test(text)), false);
          assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${theme} ${state} ${width}: overflow`);
          assert.equal(await page.locator('.route-recovery-secondary').getAttribute('href'), state === 'not-found' ? '/season' : '/');
          await page.keyboard.press('Tab');
          assert.equal(await page.locator('.route-recovery-brand').evaluate(node => node === document.activeElement), true);
          await page.keyboard.press('Tab');
          assert.equal(await page.locator('.theme-toggle').evaluate(node => node === document.activeElement), true);
          await page.keyboard.press('Tab');
          assert.equal(await page.locator('.route-recovery-primary').evaluate(node => node === document.activeElement), true);
          const focus = await page.locator('.route-recovery-primary').evaluate(node => { const style = getComputedStyle(node); return { width: parseFloat(style.outlineWidth), height: node.getBoundingClientRect().height }; });
          assert.ok(focus.width >= 3 && focus.height >= 44);
          if ([390, 1440].includes(width)) await page.screenshot({ path: `${output}/${state}-${theme}-${width}.png`, fullPage: true });
          await page.close();
        }
        for (const width of [390, 1440]) {
          const page = await browser.newPage({ viewport: { width, height: 900 } });
          await page.goto(`${fixture}?theme=${theme}&state=${state}&scale=2`);
          await page.locator('.route-recovery h1').waitFor();
          await page.locator('.route-recovery-art img').evaluate(image => image.decode());
          assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${state} ${width}: 200% overflow`);
          await page.screenshot({ path: `${output}/${state}-${theme}-${width}-scaled.png`, fullPage: true });
          await page.close();
        }
      }
      {
        const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
        const url = `${fixture}?theme=${theme}&state=chunk&retry=success&season=2026&round=19#classification`;
        await page.goto(url);
        await page.getByRole('button', { name: 'Повторить загрузку', exact: true }).waitFor();
        const themeButton = page.locator('.theme-toggle');
        await themeButton.click();
        await page.getByRole('button', { name: 'Повторить загрузку', exact: true }).click();
        await page.getByRole('heading', { name: 'Страница открыта', exact: true }).waitFor();
        assert.equal(page.url(), url, 'Retry must keep the full address');
        assert.equal(await page.locator('html').getAttribute('data-theme'), theme === 'light' ? 'dark' : 'light');
        await page.close();
      }
      {
        const page = await browser.newPage();
        await page.goto(`${fixture}?theme=${theme}`);
        await page.route(`${base}/`, route => route.fulfill({ contentType: 'text/html; charset=utf-8', body: '<h1>Главная открыта</h1>' }));
        await page.getByRole('link', { name: 'На главную', exact: true }).click();
        await page.getByRole('heading', { name: 'Главная открыта', exact: true }).waitFor();
        await page.close();
      }
      console.log(`${theme}: router error/404, 320–1440px, 200% text, keyboard focus, theme persistence, chunk retry and home recovery passed`);
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
