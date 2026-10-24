// Read-only UI regression against Vite fixtures and mocked API responses.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const base = process.env.HOME_UI_URL || 'http://127.0.0.1:5173';
const screenshots = process.env.HOME_SCREENSHOT_DIR;
async function inspect(page) {
  return page.evaluate(() => {
    const root = document.querySelector('.home-screen, .menu-page');
    const rgb = value => (value.match(/[\d.]+/g)||[]).map(Number);
    const luminance = v => v.slice(0,3).map(x=>x/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
    const issues = [], lowContrast = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while(walker.nextNode()) {
      const text = walker.currentNode.textContent.trim(), el=walker.currentNode.parentElement;
      if(!text || el.closest('[aria-hidden="true"],[inert],.home-sr-only')) continue;
      const s=getComputedStyle(el), rect=el.getBoundingClientRect();
      if(!rect.width || !rect.height || !el.checkVisibility()) continue;
      const foreground=rgb(s.color); let bg=null;
      for(let node=el;node;node=node.parentElement) { const c=rgb(getComputedStyle(node).backgroundColor); if(c.length===3 || c[3]===1){bg=c;break;} }
      if(bg){const a=luminance(foreground),b=luminance(bg),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05),minimum=parseFloat(s.fontSize)>=24 || (parseFloat(s.fontSize)>=18.66&&Number(s.fontWeight)>=700)?3:4.5;if(ratio<minimum) lowContrast.push({text,ratio:ratio.toFixed(2),color:s.color,bg});}
      if(rect.left < -1 || rect.right > innerWidth+1) issues.push({text, left:rect.left, right:rect.right});
    }
    return {overflow:document.documentElement.scrollWidth>innerWidth,issues,lowContrast,headingCount:root.querySelectorAll('h1').length};
  });
}
async function fixture(browser, width, theme, extra = '', time = '2026-10-23T12:00:00Z') {
  const page = await browser.newPage({ viewport: { width, height: 1000 }, timezoneId: 'Europe/Moscow', reducedMotion: 'reduce' });
  await page.clock.install({ time: new Date(time) });
  await page.route('https://telegram.org/**', route => route.abort());
  await page.route('https://media.formula1.com/**', route => route.abort());
  await page.goto(`${base}/tests/home-design-preview.html?theme=${theme}${extra}`);
  if (extra.includes('page=menu')) await page.locator('.menu-page').waitFor();
  else await page.waitForFunction(() => document.querySelector('.home-championship') && !document.querySelector('.home-championship')?.textContent.includes('Загружаем') && !document.querySelector('.home-race[aria-busy]'));
  return page;
}
async function verifyLabels(page) {
  const wrapped = await page.evaluate(() => {
    const selectors = '.home-race h2,.home-race-meta > span,.home-race-location,.home-race-date > span,.home-race-date strong,.home-schedule summary strong,.home-schedule summary small,.home-session-name,.home-entrant strong,.home-entrant small,.home-championship-head h2,.home-full-standing,.home-heading h1,.home-heading > div > span,.home-season-link,.menu-sections a > span';
    const failures = [];
    for (const el of document.querySelectorAll(selectors)) {
      if (el.closest('[inert]') || !el.checkVisibility() || !el.getBoundingClientRect().width) continue;
      for (const node of el.childNodes) {
        if (node.nodeType !== Node.TEXT_NODE || !node.textContent.trim()) continue;
        const range = document.createRange(); range.selectNodeContents(node);
        if (new Set([...range.getClientRects()].map(rect => Math.round(rect.top))).size > 1) failures.push(node.textContent);
      }
    }
    return failures;
  });
  assert.deepEqual(wrapped, [], `Unwanted wrapping: ${JSON.stringify(wrapped)}`);
}
async function verify(page, label) {
  const result = await inspect(page);
  assert.deepEqual(result, { overflow: false, issues: [], lowContrast: [], headingCount: 1 }, `${label}: ${JSON.stringify(result)}`);
}
(async () => {
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true });
  let checks = 0;
  try {
    for (const theme of ['light', 'dark']) for (const width of [320, 360, 390, 430, 699, 820, 1024, 1440, 1920]) {
      const page = await fixture(browser, width, theme);
      assert.equal(await page.locator('.home-race-date strong').textContent(), '23:00');
      assert.match(await page.locator('.home-race-countdown').innerText(), /2 д 8 ч/);
      assert.equal(await page.locator('.home-standing-table tbody tr').count(), 5);
      assert.equal(await page.locator('.home-gap').nth(1).textContent(), '−15');
      assert.equal(await page.locator('.home-schedule').getAttribute('open'), null);
      await verify(page, `${theme} ${width} collapsed`);
      assert.equal(await page.locator('.mobile-primary-nav, .mobile-menu-dialog, .legal-footer').count(), 0);
      if (width < 900) {
        await verifyLabels(page);
        assert.equal(await page.locator('.home-circuit').isVisible(), false);
        if (width <= 430) assert.ok(await page.locator('.home-race').evaluate(el => el.getBoundingClientRect().height) < 250, 'Mobile race card must stay compact alongside favorites');
      } else assert.ok(await page.locator('.home-circuit').evaluate(el => el.getBoundingClientRect().height) >= 180);
      await page.locator('.home-schedule > summary').focus();
      assert.equal(await page.locator('.home-schedule > summary').evaluate(el => getComputedStyle(el).outlineStyle), 'solid');
      await page.keyboard.press('Enter');
      assert.notEqual(await page.locator('.home-schedule').getAttribute('open'), null);
      assert.equal(await page.locator('.home-sessions li').count(), 5);
      await verify(page, `${theme} ${width} expanded`);
      if (width < 900) await verifyLabels(page);
      await page.keyboard.press('Enter');
      await page.getByRole('link', { name: 'Команды', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('.home-standing-switch a[aria-current]')?.textContent === 'Команды');
      assert.equal(await page.locator('.home-standing-table tbody th').first().innerText(), 'McLaren');
      assert.equal(await page.locator('.home-points').first().textContent(), '559');
      assert.equal(await page.locator('.home-full-standing').getAttribute('href'), '/constructors?year=2026');
      await verify(page, `${theme} ${width} teams`);
      await page.getByRole('link', { name: 'Пилоты', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('.home-standing-switch a[aria-current]')?.textContent === 'Пилоты');
      if (screenshots && [390, 1440].includes(width)) {
        await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0); });
        await page.screenshot({ path: path.join(screenshots, `turbotears-alt-${theme}-${width}.png`), fullPage: true });
      }
      await page.close(); checks++;
    }
    for (const theme of ['light', 'dark']) for (const state of ['error', 'empty', 'cancelled', 'finished', 'schedule-error', 'past', 'untimed', 'race-untimed']) {
      const page = await fixture(browser, 390, theme, `&state=${state}`);
      await page.locator('.home-schedule > summary').click();
      await verify(page, `${theme} ${state}`);
      if (['cancelled', 'finished'].includes(state)) {
        assert.equal(await page.locator('.home-race time').count(), 0);
        assert.equal(await page.locator('.home-race-cta').getAttribute('href'), '/season');
      }
      if (state === 'race-untimed') { assert.equal(await page.locator('.home-race-date').count(), 0); assert.match(await page.locator('.home-race-countdown').innerText(), /Время старта уточняется/); }
      if (state === 'untimed') assert.match(await page.locator('.home-sessions li').last().innerText(), /Практика 1.*Время уточняется/s);
      if (state === 'past') assert.match(await page.locator('.home-race-countdown').innerText(), /Плановое время старта прошло/);
      if (state === 'error') assert.equal(await page.getByRole('button', { name: 'Повторить загрузку зачёта' }).count(), 1);
      await page.close(); checks++;
    }
    for (const width of [320, 390, 1440]) {
      const page = await fixture(browser, width, 'light', '&scale=2&auth=member');
      await page.locator('.home-schedule > summary').click();
      await page.locator('.personal-home-details > summary').click();
      await verify(page, `200% ${width}`);
      if (screenshots && width === 390) await page.screenshot({ path: path.join(screenshots, 'turbotears-alt-large-text.png'), fullPage: true });
      await page.close(); checks++;
    }
    const countdownPage = await fixture(browser, 320, 'dark', '', '2026-10-24T07:17:00Z');
    await verify(countdownPage, 'long countdown at 320px');
    assert.match(await countdownPage.locator('.home-race-countdown').innerText(), /1 д 12 ч 4[23] мин/);
    assert.equal(await countdownPage.locator('.home-race-countdown > span').evaluate(el => {
      const range = document.createRange(); range.selectNodeContents(el);
      return new Set([...range.getClientRects()].map(rect => Math.round(rect.top))).size;
    }), 1);
    await countdownPage.close(); checks++;

    for (const theme of ['light', 'dark']) for (const width of [320, 390, 820, 1440]) {
      const page = await fixture(browser, width, theme, '&page=menu');
      await verify(page, `menu ${theme} ${width}`);
      await verifyLabels(page);
      assert.match(await page.title(), /^Меню/);
      assert.equal(await page.locator('.mobile-primary-nav, dialog, .visit-reminder').count(), 0);
      assert.equal(await page.getByRole('link', { name: 'Админ-панель', exact: true }).count(), 0);
      assert.equal(await page.getByRole('link', { name: 'Мой профиль', exact: true }).getAttribute('href'), '/account');
      await page.getByText('О проекте и документы', { exact: true }).click();
      assert.equal(await page.getByRole('link', { name: 'Конфиденциальность', exact: true }).isVisible(), true);
      await verify(page, `menu documents ${theme} ${width}`);
      await page.getByText('О проекте и документы', { exact: true }).click();
      await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0); });
      if (screenshots && width === 390) await page.screenshot({ path: path.join(screenshots, `turbotears-menu-${theme}-${width}.png`), fullPage: true });
      await page.getByRole('button', { name: 'Назад из меню' }).click();
      await page.locator('.home-standing-table').waitFor();
      if (width < 900) {
        const menu = page.getByRole('navigation', { name: 'Основная навигация', exact: true }).getByRole('link', { name: 'Меню', exact: true });
        await menu.focus(); await page.keyboard.press('Enter');
        await page.locator('.menu-page').waitFor();
        assert.equal(await page.locator('.menu-page h1').evaluate(el => el === document.activeElement), true);
        await page.getByRole('button', { name: 'Назад из меню' }).click();
        await page.locator('.home-standing-table').waitFor();
      }
      await page.close(); checks++;
    }
    for (const width of [320, 390]) {
      const page = await fixture(browser, width, 'light', '&page=menu&scale=2&auth=member');
      await verify(page, `menu 200% ${width}`);
      assert.equal(await page.locator('.menu-page').getByRole('link', { name: 'Мой профиль', exact: true }).getAttribute('href'), '/profile');
      await page.close(); checks++;
    }

    // Real browser router: query persistence, Back, and a successful retry after failures.
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, timezoneId: 'Europe/Moscow', reducedMotion: 'reduce' });
    await page.clock.install({ time: new Date('2026-10-23T12:00:00Z') });
    await page.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'skipped' })));
    await page.route('https://telegram.org/**', route => route.abort());
    let fail = false;
    const drivers = [{ position: 1, name: 'Pilot One', points: 100, constructorName: 'Team One' }, { position: 2, name: 'Pilot Two', points: 85, constructorName: 'Team Two' }];
    await page.route('**/api/**', route => {
      const url = new URL(route.request().url());
      if (route.request().method() !== 'GET') return route.fulfill({ status: 405, json: {} });
      if (url.pathname === '/api/auth/me') return route.fulfill({ status: 401, json: {} });
      if (fail && ['/api/drivers', '/api/constructors'].includes(url.pathname)) return route.fulfill({ status: 503, json: {} });
      const data = url.pathname === '/api/next-race' ? { status: 'ok', event_name: 'United States Grand Prix', season: 2026, round: 19, race_start_utc: '2026-10-25T20:00:00Z' }
        : url.pathname === '/api/weekend-schedule' ? { sessions: [{ name: 'Гонка', utc_iso: '2026-10-25T20:00:00Z' }] }
        : url.pathname === '/api/drivers' ? { drivers, round: 18 }
        : url.pathname === '/api/constructors' ? { constructors: [{ position: 1, name: 'Team One', points: 185 }], round: 18 } : {};
      return route.fulfill({ json: data });
    });
    await page.goto(`${base}/`);
    await page.locator('.home-standing-table').waitFor();
    await page.getByRole('link', { name: 'Команды', exact: true }).click();
    await page.waitForURL(url => url.searchParams.get('standing') === 'teams');
    assert.equal(new URL(page.url()).searchParams.get('standing'), 'teams');
    await page.reload();
    await page.locator('.home-standing-table').waitFor();
    assert.equal(await page.locator('.home-standing-table tbody th').first().innerText(), 'Team One');
    await page.getByRole('link', { name: 'Пилоты', exact: true }).click();
    await page.waitForURL(url => !url.searchParams.has('standing'));
    await page.goBack();
    await page.waitForURL(url => url.searchParams.get('standing') === 'teams');
    assert.equal(new URL(page.url()).searchParams.get('standing'), 'teams');
    fail = true;
    await page.reload();
    await page.getByRole('button', { name: 'Повторить загрузку зачёта' }).waitFor();
    fail = false;
    await page.getByRole('button', { name: 'Повторить загрузку зачёта' }).click();
    await page.locator('.home-standing-table').waitFor();
    assert.match(await page.locator('.home-championship-head p').innerText(), /после этапа 18/);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('navigation', { name: 'Основная навигация', exact: true }).getByRole('link', { name: 'Меню', exact: true }).click();
    await page.waitForURL(`${base}/menu`);
    await page.locator('.menu-page').waitFor();
    await page.reload(); await page.locator('.menu-page').waitFor();
    await page.goBack();
    await page.waitForURL(url => url.pathname === '/' && url.searchParams.get('standing') === 'teams');
    await page.locator('.home-standing-table').waitFor();
    await page.getByRole('navigation', { name: 'Основная навигация', exact: true }).getByRole('link', { name: 'Меню', exact: true }).click();
    await page.locator('.menu-page').waitFor();
    await page.getByRole('button', { name: 'Назад из меню' }).click();
    await page.waitForURL(url => url.pathname === '/' && url.searchParams.get('standing') === 'teams');
    await page.close(); checks++;
    console.log(`${checks} browser scenarios passed: themes, nine widths, compact card, unwrapped mobile labels, keyboard disclosure, standings, contrast, 200% text, errors, menu routes/documents/permissions, URL reload/Back and retry recovery.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
