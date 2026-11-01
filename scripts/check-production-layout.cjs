// Local visual and interaction regression for the new.f1hub.ru fixes.
// Uses Vite-only fictional data; never writes to a production API.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const base = process.env.UI_BASE_URL || 'http://127.0.0.1:5174';
const out = process.env.UI_ARTIFACTS || '/tmp/f1hub-layout';
fs.mkdirSync(out, { recursive: true });
const url = params => `${base}/tests/home-design-preview.html?${new URLSearchParams({ auth: 'member', ...params })}`;
async function fit(page) { assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Document must fit the viewport'); }
async function capture(page, selector, filename) {
  const target = page.locator(selector).first();
  await target.scrollIntoViewIfNeeded();
  await page.evaluate(() => document.fonts.ready);
  await target.locator('img').evaluateAll(images => Promise.all(images.filter(i => i.getBoundingClientRect().bottom > 0 && i.getBoundingClientRect().top < innerHeight).map(i => Promise.race([i.decode().catch(() => {}), new Promise(resolve => setTimeout(resolve, 2000))]))));
  await page.screenshot({ path: path.join(out, `${filename}.png`) });
}
(async () => {
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true });
  try {
    for (const theme of process.env.UI_FLOWS_ONLY ? [] : ['light','dark']) for (const width of [320,390,900,1200,1440,2560]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
      const page = await context.newPage();
      page.setDefaultTimeout(10000);
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      const cases = [
        ['driver', {page:'driver-details',code:'HAM'}, '.entrant-hero'],
        ['team', {page:'constructor-details',constructorId:'mercedes'}, '.entrant-hero'],
        ['table', {page:'predictions',tab:'leaderboard',state:'production-layout'}, '.prediction-leaderboard'],
        ['season', {page:'predictions',tab:'history',state:'production-layout'}, '.season-progress'],
        ['titles', {page:'predictions',state:'prediction-closed',championship:'both',saved:'1'}, '.championship-forecast'],
        ['profile', {page:'profile',state:'production-layout'}, '.profile-favorites'],
        ['community', {page:'community'}, '.community-spotlight'],
      ];
      for (const [name, params, selector] of cases) {
        await page.goto(url({theme,...params}), { waitUntil:'domcontentloaded' });
        await page.locator(selector).first().waitFor();
        await fit(page);
        if (name === 'profile') {
          assert.equal(await page.locator('.profile-favorites-portraits .entrant-portrait').count(),7);
          assert.equal(await page.locator('.profile-favorites-teams .team-logo').count(),5);
        }
        if (name === 'community') assert.equal(await page.locator('.community-backdrop').count(),0);
        if ([390,1440].includes(width)) await capture(page,selector,`${name}-${theme}-${width}`);
      }
      if ([390,1440].includes(width)) {
        await page.goto(url({theme,view:'season',spotlight:'team'}),{waitUntil:'domcontentloaded'});
        const card = page.locator('.home-spotlight-slide[data-slide-index="3"] .home-favorite-card--team');
        await card.waitFor(); await card.scrollIntoViewIfNeeded(); await fit(page);
        await capture(page,'.home-spotlight-slide[data-slide-index="3"] .home-favorite-card--team',`home-team-${theme}-${width}`);
        const [logo,car] = await Promise.all([card.locator('.home-team-logo').boundingBox(),card.locator('.home-team-car').boundingBox()]);
        assert.ok(logo.y + logo.height <= car.y + 1,'Car and logo must have separate space');
      }
      assert.deepEqual(errors,[]);
      await context.close(); console.log(`${theme} ${width}px: rendered layouts fit; favorite artwork and community passed`);
    }
    const context=await browser.newContext({viewport:{width:390,height:1000}});
    const page=await context.newPage(); page.setDefaultTimeout(10000);
    await page.goto(url({page:'predictions',tab:'leaderboard',state:'production-layout'}),{waitUntil:'domcontentloaded'});
    await page.locator('.prediction-leaderboard tbody tr').first().waitFor();
    const search=page.getByRole('searchbox',{name:'Найти участника'});
    await search.fill('Позднее'); assert.equal(await page.locator('.prediction-leaderboard tbody tr').count(),1);
    await search.fill('Никого'); await page.getByRole('status').filter({hasText:'Участник не найден'}).waitFor();
    await page.getByRole('button',{name:'Моя строка',exact:true}).click();
    await page.waitForFunction(()=>document.activeElement?.id==='prediction-my-row');
    assert.equal(await search.inputValue(),'');
    await page.locator('.prediction-sort').getByRole('combobox').click();
    await page.getByRole('option',{name:'По победам',exact:true}).click();
    assert.match(await page.locator('.prediction-leaderboard tbody tr').nth(1).textContent(),/Участник 4/);
    await page.getByRole('button',{name:'Статистика',exact:true}).click();
    await page.getByRole('columnheader',{name:'Средний',exact:true}).waitFor();
    await page.getByRole('button',{name:'Показать все этапы',exact:true}).click();
    assert.equal(await page.locator('.prediction-leaderboard thead th abbr').count(),7);
    await page.locator('#prediction-my-row .prediction-own-score').first().click();
    await page.getByRole('dialog').waitFor(); await page.keyboard.press('Escape');
    await page.goto(url({page:'predictions',championship:'multiple'}),{waitUntil:'domcontentloaded'});
    const titleChoice=page.locator('.title-candidate').getByRole('combobox');
    await titleChoice.click(); await page.getByRole('option',{name:'Оскар Пиастри · 355 очк.',exact:true}).click();
    assert.equal(await page.locator('.title-contender h5').textContent(),'Оскар Пиастри');
    const portrait=page.locator('.title-contender .entrant-portrait img');
    assert.match(await portrait.getAttribute('src'),/2026.*PIA\.webp/);
    await page.locator('.title-answer').getByRole('button',{name:'Нет',exact:true}).click();
    assert.equal(await page.locator('.title-answer').getByRole('button',{name:'Нет',exact:true}).getAttribute('aria-pressed'),'true');
    await titleChoice.click(); await page.getByRole('option',{name:'Ландо Норрис · 390 очк.',exact:true}).click();
    assert.equal(await page.locator('.title-answer [aria-pressed="true"]').count(),0,'Changing candidate requires a new explicit answer');
    for (const name of ['calendar','weekend']) {
      const params=name==='calendar'?{page:name,round:'20',filter:'all'}:{page:name,venue:'mexico'};
      await page.goto(url(params),{waitUntil:'domcontentloaded'});
      const route=page.locator('.calendar-track-svg .track-route-border, .weekend-track-svg .track-route-border').first();
      await route.waitFor({state:'attached'});
      assert.ok(await route.evaluate(p=>p.getAnimations().length>0),'Contour should draw on first reveal');
      await page.waitForFunction(()=>document.querySelector('.calendar-track-svg .animation-complete, .weekend-track-svg .animation-complete'));
      assert.equal(await page.locator('.calendar-track-svg, .weekend-track-svg').first().textContent(),'');
      if(name==='weekend') {
        await page.locator('.circuit-map-launcher').hover();
        assert.equal(await page.locator('.circuit-map-launcher').evaluate(e=>getComputedStyle(e).backgroundColor),'rgba(0, 0, 0, 0)');
        await page.getByRole('button',{name:/Статистика трассы:/}).click();
        await page.getByRole('dialog').waitFor(); await page.keyboard.press('Escape');
      }
      await capture(page,name==='calendar'?'.calendar-track-map':'.weekend-track-map',`${name}-drawn`);
      await page.goto(url({...params,state:'track-map-error'}),{waitUntil:'domcontentloaded'});
      await page.getByText('Схема трассы недоступна',{exact:true}).first().waitFor();
      assert.equal(await page.getByText('&#x20;',{exact:true}).count(),0);
    }
    // A real production route with local mock API responses, so native avatar
    // URLs are checked without the preview's image-substitution observer.
    const {profilePreview}=await import(pathToFileURL(path.resolve('front/tests/fixtures/profile.ts')).href);
    const fixture=profilePreview(new URLSearchParams({auth:'member',state:'profile-save-error'}));
    await page.route('**/api/**',async route=>{
      const u=new URL(route.request().url());
      if(u.pathname.endsWith('/avatar/v1.png')) return route.fulfill({path:'front/tests/fixtures/profile-avatar.png',contentType:'image/png'});
      if(u.pathname.startsWith('/api/profiles/')) {
        const response=await fixture(u,{method:route.request().method(),body:route.request().postData()});
        if(response) return route.fulfill({status:response.status,body:await response.text(),contentType:'application/json'});
      }
      const value=u.pathname==='/api/auth/me'?{id:1,role:'user',email_verified:true}:u.pathname==='/api/web-notifications/unread-count'?{unread:0}:{};
      return route.fulfill({json:value});
    });
    await page.goto(`${base}/profile`,{waitUntil:'domcontentloaded'});
    const avatar=page.locator('.account-shortcut-avatar:visible'); await avatar.waitFor();
    assert.match(await avatar.getAttribute('src'),/helmet=scarlet/);
    await page.getByRole('button',{name:'Аватар и оформление',exact:true}).click();
    await page.getByRole('button',{name:'Кобальт / двойная полоса',exact:true}).click();
    await page.getByRole('button',{name:'Сохранить изменения',exact:true}).click();
    await page.getByRole('alert').filter({hasText:'Сервис временно недоступен'}).waitFor();
    assert.match(await avatar.getAttribute('src'),/helmet=scarlet/,'Failed save must preserve the old avatar');
    await page.getByRole('button',{name:'Сохранить изменения',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.account-shortcut-avatar')?.getAttribute('src')?.includes('helmet=cobalt'));
    await page.reload(); await avatar.waitFor(); assert.match(await avatar.getAttribute('src'),/helmet=cobalt/);
    await context.close();
    console.log('Search, own-row focus, table details, personal review, contour animation/error, weekend disclosure and avatar failure/save/reload passed');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
