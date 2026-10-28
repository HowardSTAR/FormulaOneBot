// Local fixture only: no backend writes, notification permission prompts or delivery.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { mkdirSync } = require('node:fs');
const base = process.env.NOTIFICATIONS_UI_URL || 'http://127.0.0.1:5173';
const output = process.env.NOTIFICATIONS_UI_OUTPUT || '/tmp/notifications-design';
mkdirSync(output, { recursive: true });
const fixture = `${base}/tests/home-design-preview.html?page=notifications&auth=member`;
const overflow = page => page.evaluate(() => ({ page: document.documentElement.scrollWidth > innerWidth + 1,
  content: [...document.querySelectorAll('.notifications-page, .notifications-inbox, .notifications-controls')].some(el => el.scrollWidth > el.clientWidth + 1) }));
async function ready(page, extra = '') {
  page.setDefaultTimeout(10000);
  console.log('Preview', extra || 'default');
  await page.goto(`${fixture}${extra}`);
  await page.locator('.notification-item').first().waitFor();
}
async function mockPush(page, permission = 'default') {
  await page.addInitScript(permission => {
    let subscription = null;
    window.previewPush = { requested: 0, unsubscribed: 0 };
    Object.defineProperty(window, 'Notification', { configurable: true, value: { permission,
      requestPermission: async () => { window.previewPush.requested++; return 'granted'; } } });
    const sub = { endpoint: 'https://push.example.test/local-preview', toJSON: () => ({ keys: { p256dh: 'preview', auth: 'preview' } }),
      unsubscribe: async () => { subscription = null; window.previewPush.unsubscribed++; return true; } };
    const reg = { pushManager: { getSubscription: async () => subscription, subscribe: async () => (subscription = sub) } };
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: { getRegistration: async () => reg, register: async () => reg, ready: Promise.resolve(reg) } });
  }, permission);
}
(async () => {
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true });
  try {
    for (const theme of ['light', 'dark']) {
      for (const width of [320, 390, 700, 899, 900, 1213, 1214, 1440, 1920]) {
        const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
        const errors = []; page.on('pageerror', e => errors.push(e.message));
        await ready(page, `&theme=${theme}`);
        assert.deepEqual(await overflow(page), {page: false, content: false}, `${theme} ${width}: overflow`);
        assert.equal(await page.locator('.notification-destination').first().getAttribute('href'), '/race-results?season=2026&round=19');
        assert.equal(await page.locator('.notification-destination :is(button,a,summary)').count(), 0);
        assert.equal(await page.locator('.notification-shortcut:visible').getAttribute('aria-current'), 'page');
        for (const control of ['.theme-toggle', '.notification-shortcut', '.account-shortcut']) {
          assert.equal(await page.locator(`${control}:visible`).count(), 1, `${width}: duplicate toolbar controls`);
        }
        const tools = await page.locator('.home-toolbar').boundingBox();
        assert.ok(tools && tools.x >= 0 && tools.x + tools.width <= width + 1, `${width}: toolbar clipped`);
        if (width >= 900) assert.ok(tools.x + tools.width > width - 60, `${width}: toolbar must be at trailing edge`);

        const select = page.getByRole('combobox', {name:'Тип уведомлений'});
        await select.focus(); await page.keyboard.press('Enter'); await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter');
        await page.waitForFunction(() => document.querySelectorAll('.notification-item').length === 1);
        assert.equal(await select.innerText(), 'Результаты');
        assert.deepEqual(await overflow(page), {page:false,content:false});
        await ready(page, `&theme=${theme}`);
        const summary = page.locator('.notification-full summary');
        await summary.focus(); await page.keyboard.press('Enter');
        assert.equal(await page.locator('.notification-full').getAttribute('open'), '');
        assert.deepEqual(await overflow(page), {page:false,content:false});
        await summary.press('Enter');
        if ([390,1440].includes(width)) {
          await page.evaluate(() => scrollTo(0,0));
          await page.screenshot({ path: `${output}/${theme}-${width}.png`, fullPage: true });
          await page.screenshot({ path: `${output}/${theme}-${width}-viewport.png` });
        }
        assert.deepEqual(errors, []); await page.close();
      }
      for (const width of [320,390,1440]) {
        const page = await browser.newPage({viewport:{width,height:1000}});
        await ready(page, `&theme=${theme}&scale=2`);
        assert.deepEqual(await overflow(page), {page:false,content:false}, `200% ${theme} ${width}`);
        await page.getByRole('combobox').click();
        assert.deepEqual(await overflow(page), {page:false,content:false});
        if(width === 390) await page.screenshot({path:`${output}/${theme}-390-text200.png`});
        await page.close();
      }
    }
    console.log('Responsive checks passed; testing states');
    const page = await browser.newPage({viewport:{width:390,height:900}}); page.setDefaultTimeout(10000);
    await page.goto(`${fixture}&state=notifications-error`);
    await page.getByRole('alert').waitFor();
    await page.getByRole('button',{name:'Повторить загрузку'}).click();
    await page.locator('.notification-item').first().waitFor();
    await ready(page, '&state=notifications-read-error');
    await page.getByRole('button',{name:'Отметить прочитанными',exact:true}).click();
    await page.getByRole('alert').filter({hasText:'Не удалось отметить'}).waitFor();
    assert.equal(await page.locator('.notification-new').count(),2);
    await page.getByRole('button',{name:'Отметить прочитанными',exact:true}).click();
    await page.getByRole('status').filter({hasText:'Всё прочитано'}).waitFor();
    assert.equal(await page.locator('.notification-new').count(),0);
    await page.waitForFunction(() => document.querySelector('.notification-shortcut').getAttribute('aria-label').includes('непрочитанных 0'));
    await ready(page, '&state=notifications-reading');
    await page.getByRole('button',{name:'Отметить прочитанными',exact:true}).click();
    assert.ok(await page.getByRole('button',{name:'Отмечаем…'}).isDisabled());
    await page.getByRole('status').filter({hasText:'Всё прочитано'}).waitFor();
    await ready(page, '&state=notifications-more-error');
    await page.getByRole('button',{name:'Показать ещё',exact:true}).click();
    await page.getByRole('alert').filter({hasText:'Не удалось загрузить историю'}).waitFor();
    await page.getByRole('button',{name:'Показать ещё',exact:true}).click();
    await page.getByRole('heading',{name:'Добро пожаловать в TurboTears'}).waitFor();
    assert.equal(await page.locator('.notification-item').count(),6);
    await ready(page, '&state=notifications-duplicates');
    assert.equal(await page.locator('.notification-item').count(),1);
    await page.getByText('Объединено сообщений: 2').waitFor();
    await page.goto(`${fixture}&state=notifications-empty`);
    await page.getByRole('heading',{name:'Новых событий пока нет'}).waitFor();
    await page.goto(`${fixture}&state=notifications-loading`);
    await page.getByRole('status').filter({hasText:'Загружаем уведомления…'}).waitFor();
    await page.close();
    for(const state of ['', 'notifications-push-error']) {
      const push = await browser.newPage({viewport:{width:390,height:900}}); await mockPush(push);
      await ready(push, `&state=${state}`);
      await push.getByRole('button',{name:'Включить push',exact:true}).click();
      if(state) {
        await push.locator('.notifications-controls [role="alert"]').waitFor();
        assert.equal(await push.evaluate(()=>window.previewPush.unsubscribed),1);
        assert.ok(await push.getByRole('button',{name:'Включить push',exact:true}).isEnabled());
      } else {
        await push.getByRole('button',{name:'Отключить push',exact:true}).click();
        await push.getByRole('button',{name:'Включить push',exact:true}).waitFor();
        assert.equal(await push.evaluate(()=>window.previewPush.unsubscribed),1);
      }
      assert.equal(await push.evaluate(()=>window.previewPush.requested),1); await push.close();
    }
    const denied = await browser.newPage(); await mockPush(denied,'denied'); await ready(denied);
    await denied.getByRole('heading',{name:'Разрешите уведомления в браузере'}).waitFor();
    await denied.getByRole('button',{name:'Включить push',exact:true}).click();
    await denied.getByRole('alert').filter({hasText:'Уведомления заблокированы'}).waitFor();
    assert.equal(await denied.evaluate(()=>window.previewPush.requested),0); await denied.close();
    const unsupported=await browser.newPage(); await unsupported.addInitScript(()=>{delete window.PushManager;}); await ready(unsupported);
    assert.ok(await unsupported.getByRole('button',{name:'Включить push',exact:true}).isDisabled()); await unsupported.close();
    const ios=await browser.newPage({userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1',viewport:{width:390,height:844}});
    await ready(ios); await ios.getByRole('heading',{name:'На iPhone нужно приложение'}).waitFor();
    assert.deepEqual(await overflow(ios),{page:false,content:false}); await ios.close();
    const guest=await browser.newPage(); await guest.goto(`${base}/tests/home-design-preview.html?page=notifications`);
    await guest.getByRole('heading',{name:'Аккаунт',exact:true}).waitFor();
    assert.equal(await guest.locator('.notifications-page').count(),0); await guest.close();
    console.log('Notifications: both themes, responsive/text reflow, keyboard filter/details, links, read/error/retry/pending, pagination, duplicates, empty/loading, mocked push states and guest access passed.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
