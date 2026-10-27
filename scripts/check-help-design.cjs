// Isolated design fixture: fetches, accounts and message delivery are local mocks.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { mkdirSync } = require('node:fs');
const base = process.env.HELP_UI_URL || 'http://127.0.0.1:5173';
const output = process.env.HELP_UI_OUTPUT || '.tmp/help-design';
const fixture = `${base}/tests/home-design-preview.html`;
mkdirSync(output, { recursive: true });
const noOverflow = page => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);
(async () => {
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true });
  try {
    for (const theme of ['light', 'dark']) {
      for (const width of [320, 390, 759, 760, 1199, 1200, 1440]) {
        const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(`${fixture}?page=contact-admin&theme=${theme}&state=contact-error`);
        await page.getByRole('heading', { name: 'Обратная связь', exact: true }).waitFor();
        assert.ok(await noOverflow(page), `${width} ${theme}: contact overflow`);
        await page.getByRole('button', { name: 'Отправить в Telegram', exact: true }).click();
        assert.equal(await page.locator('#contact-name').evaluate(node => node === document.activeElement), true);
        assert.equal(await page.locator('#contact-name').getAttribute('aria-invalid'), 'true');
        await page.getByLabel('Имя', { exact: true }).fill('Тестовый участник');
        await page.getByLabel('Контакт', { exact: true }).fill('test@example.test');
        await page.getByLabel('Сообщение', { exact: true }).fill('Проверка формы обратной связи.');
        await page.getByRole('button', { name: 'Отправить в Telegram', exact: true }).click();
        await page.getByRole('alert').filter({ hasText: 'Сообщение не отправлено' }).waitFor();
        assert.equal(await page.locator('textarea').inputValue(), 'Проверка формы обратной связи.');
        await page.getByRole('button', { name: 'Отправить в Telegram', exact: true }).click();
        await page.getByRole('status').filter({ hasText: 'доставлено' }).waitFor();
        assert.equal(await page.locator('textarea').inputValue(), '');
        assert.ok(await noOverflow(page));
        if ([390, 1440].includes(width)) {
          await page.goto(`${fixture}?page=contact-admin&theme=${theme}`);
          await page.getByRole('heading', { name: 'Обратная связь', exact: true }).waitFor();
          await page.screenshot({ path: `${output}/contact-${theme}-${width}.png`, fullPage: true });
        }
        assert.deepEqual(errors, []);
        await page.close();
      }
      for (const width of [320, 390, 399, 1440]) {
        const member = width !== 320;
        const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(`${fixture}?tour=1&theme=${theme}&auth=${member ? 'member' : 'guest'}&tier=0`);
        const guide = page.locator('.first-visit-guide');
        const titles = [];
        for (let index = 0; index < (member ? 15 : 13); index++) {
          try { await page.waitForFunction(() => document.documentElement.dataset.onboardingPhase === 'ready'); } catch (error) { console.error({theme,width,index,errors,body:(await page.locator('body').innerText()).slice(-1500)}); throw error; }
          const title = await guide.locator('h2').innerText();
          titles.push(title);
          assert.ok(await noOverflow(page), `${width} ${theme} ${title}: overflow`);
          const bounds = await page.evaluate(() => {
            const panel = document.querySelector('.first-visit-guide').getBoundingClientRect();
            const content = document.querySelector('.app-content').getBoundingClientRect();
            const frame = document.querySelector('.first-visit-target-frame').getBoundingClientRect();
            return { separate: content.right <= panel.left || content.bottom <= panel.top, frameVisible: frame.width > 0 && frame.height > 0, panelVisible: panel.x >= 0 && panel.y >= 0 && panel.bottom <= innerHeight + 1 };
          });
          assert.ok(bounds.separate && bounds.panelVisible && bounds.frameVisible, `${title}: ${JSON.stringify(bounds)}`);
          if (['Результаты', 'Пелотон'].includes(title)) {
            assert.ok(await page.locator('.first-visit-position').count() > 0, `${title}: ranks must be visibly marked`);
            if (width === 390 || width === 1440) await page.screenshot({ path: `${output}/tour-${title === 'Пелотон' ? 'standings' : 'results'}-${theme}-${width}.png` });
          }
          if (title === 'Ваш сезон в профиле') {
            assert.equal(await page.locator('.profile-season-block.first-visit-highlight').count(), 1);
            await guide.getByRole('button', { name: 'Назад', exact: true }).click();
            await guide.getByRole('heading', { name: 'Мой профиль', exact: true }).waitFor();
            await page.waitForFunction(() => document.documentElement.dataset.onboardingPhase === 'ready');
            await guide.getByRole('button', { name: 'Дальше', exact: true }).click();
            await guide.getByRole('heading', { name: title, exact: true }).waitFor();
            await page.waitForFunction(() => document.documentElement.dataset.onboardingPhase === 'ready');
          }
          if (title === 'Трофеи и избранное') {
            assert.equal(await page.locator('#profile-trophies.first-visit-highlight').count(), 1);
            await page.screenshot({ path: `${output}/tour-profile-${theme}-${width}.png` });
          }
          await guide.locator('.first-visit-primary').click();
          if (index < (member ? 14 : 12)) await page.waitForFunction(old => document.querySelector('.first-visit-guide h2')?.textContent !== old, title);
        }
        await guide.waitFor({ state: 'hidden' });
        assert.equal(await page.locator('.first-visit-target-frame, .first-visit-position').count(), 0);
        assert.equal(titles.includes('Ваш сезон в профиле'), member);
        assert.deepEqual(errors, []);
        await page.close();
      }
      for (const width of [390, 1440]) {
        const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
        await page.goto(`${fixture}?page=contact-admin&theme=${theme}&scale=2`);
        await page.getByRole('heading', { name: 'Обратная связь', exact: true }).waitFor();
        assert.ok(await noOverflow(page), `${width} ${theme}: contact 200% overflow`);
        await page.goto(`${fixture}?tour=1&theme=${theme}&auth=member&scale=2`);
        await page.waitForFunction(() => document.documentElement.dataset.onboardingPhase === 'ready');
        assert.ok(await noOverflow(page), `${width} ${theme}: tour 200% overflow`);
        await page.screenshot({ path: `${output}/tour-scaled-${theme}-${width}.png` });
        await page.keyboard.press('Escape');
        assert.equal(await page.locator('.first-visit-target-frame').count(), 0);
        await page.close();
      }
      {
        const page = await browser.newPage({viewport:{width:390,height:900},reducedMotion:'no-preference'});
        await page.goto(`${fixture}?page=contact-admin&theme=${theme}&state=contact-sending`);
        await page.getByLabel('Имя',{exact:true}).fill('Проверка ожидания');
        await page.getByLabel('Контакт',{exact:true}).fill('test@example.test');
        await page.getByLabel('Сообщение',{exact:true}).fill('Локальная проверка состояния отправки.');
        await page.getByRole('button',{name:'Отправить в Telegram',exact:true}).click();
        assert.equal(await page.getByRole('button',{name:'Отправляем…'}).isDisabled(),true);
        assert.equal(await page.locator('textarea').isDisabled(),true);
        await page.getByRole('status').filter({hasText:'доставлено'}).waitFor();
        await page.goto(`${fixture}?tour=1&theme=${theme}&auth=member`);
        await page.waitForFunction(()=>document.documentElement.dataset.onboardingPhase==='ready');
        await page.locator('.first-visit-primary').click();
        await page.waitForFunction(()=>document.documentElement.dataset.onboardingPhase==='ready' && document.querySelector('.first-visit-guide h2')?.textContent==='Календарь');
        await page.keyboard.press('Escape');
        assert.equal(await page.locator('.first-visit-target-frame').count(),0);
        await page.close();
      }
      console.log(`${theme}: contact validation/retry/success, full guest/member tours, profile steps, rank frames, 320–1440px and 200% passed`);
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
