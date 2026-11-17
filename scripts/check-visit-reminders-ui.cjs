// APIs are read-only fixtures. No messages, scores or forecasts are submitted.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.REMINDER_UI_URL || 'http://127.0.0.1:5174';
const now = Date.parse('2026-10-05T12:00:00Z');
const week = {track_id:'emerald-loop-v2',name:'Emerald Loop',start:'2026-10-05T00:00:00Z',end:'2026-10-12T00:00:00Z',entries:[]};
const weekly = {week:'2026-10-05',end:week.end,track_id:week.track_id,name:week.name,time_ms:70000,place:2,alert_id:14,
  rival:{name:'Очень длинное игровое имя быстрого соперника',time_ms:68000}};
const prediction = {status:'ok',season:2026,round:17,event_name:'Singapore Grand Prix',is_open:true,opens_at_utc:'2026-10-05T00:00:00Z',deadline_utc:'2026-10-10T00:00:00Z',prediction:null};
(async()=>{
  const browser = await chromium.launch({channel:process.env.BROWSER_CHANNEL || 'chrome',headless:true});
  try {
    for (const {width, theme, scale} of [
      {width:320,theme:'light'}, {width:390,theme:'dark'}, {width:899,theme:'dark'},
      {width:900,theme:'light'}, {width:900,theme:'dark',scale:2},
      {width:1440,theme:'dark'}, {width:1920,theme:'light'}, {width:2560,theme:'dark'},
    ]) {
      const context = await browser.newContext({viewport:{width,height:900}, reducedMotion:'reduce'});
      await context.addInitScript(({now,theme,scale})=>{
        Date.now=()=>now;
        localStorage.setItem('turbotears-onboarding-v2',JSON.stringify({status:'completed'}));
        localStorage.setItem('turbotears-theme',theme);
        if (scale) document.addEventListener('DOMContentLoaded',()=>{ document.documentElement.style.fontSize = `${scale * 100}%`; });
      },{now,theme,scale});
      const page = await context.newPage();
      page.setDefaultTimeout(8000);
      let kind = 'overtaken', unavailable = false, saved = false, userId = 1, delayed = false, unread = 3;
      const errors = [];
      page.on('pageerror',e=>errors.push(e.message));
      await page.route('**/api/**',async route=>{
        const path = new URL(route.request().url()).pathname;
        if (route.request().method()!=='GET') return route.fulfill({json:{ok:true}});
        if (path==='/api/auth/me') return userId
          ? route.fulfill({json:{id:userId,telegram_id:null,email_verified:true,role:'user'}})
          : route.fulfill({status:401,json:{}});
        if (path==='/api/web-notifications/unread-count') return route.fulfill({json:{unread}});
        if (path==='/api/engagement/weekly/me') {
          const account = userId;
          if (delayed) await new Promise(resolve=>setTimeout(resolve,600));
          return route.fulfill({status:unavailable?503:200,json:unavailable?{detail:'Unavailable'}:{user_id:account,weekly:kind==='overtaken'?weekly:null}});
        }
        if (path==='/api/engagement/weekly') return route.fulfill({json:week});
        if (path==='/api/predictions/current') return route.fulfill({json:{...prediction,prediction:saved?{}:null,
          deadline_utc:kind==='missing'?'2026-10-05T15:00:00Z':prediction.deadline_utc,is_open:kind!=='week'}});
        if (path==='/api/next-race') return route.fulfill({json:{status:'ok',event_name:'Singapore Grand Prix',season:2026,round:17,
          next_session_iso:kind==='session'?'2026-10-05T13:00:00Z':'2026-10-09T10:00:00Z',next_session_name:'Практика 1'}});
        if (path==='/api/weekend-schedule') return route.fulfill({json:{sessions:[]}});
        return route.fulfill({status:404,json:{}});
      });
      const banner = page.getByRole('complementary',{name:'Напоминание'});
      const bell = page.getByRole('button',{name:/Есть напоминание/});
      const open = async()=>{ await bell.click(); await banner.waitFor(); };
      const clear = async()=>page.evaluate(()=>{sessionStorage.clear();localStorage.removeItem('f1hub-reminder:1:overtaken:2026-10-05:14')});
      await page.goto(base+'/drivers');
      if (width < 900) {
        await page.getByRole('complementary',{name:'Актуальное напоминание'}).getByText('Твоё время обошли').waitFor();
        assert.equal(await bell.count(),0);
        if (process.env.REMINDER_UI_OUTPUT) await page.screenshot({path:`${process.env.REMINDER_UI_OUTPUT}/mobile-${width}.png`});
        await context.close();
        console.log(`${width}px: mobile dock reminder passed`);
        continue;
      }
      await bell.waitFor();
      await bell.getByText('3',{exact:true}).waitFor();
      assert.equal(await banner.count(),0,'Reminder opens on demand');
      await bell.focus();
      const content = page.locator('#page-content');
      const contentTop = (await content.boundingBox()).y;
      await bell.press('Enter');
      await banner.getByText('Твоё время обошли',{exact:true}).waitFor();
      assert.equal(await banner.getByRole('link',{name:/Перебить время/}).getAttribute('href'),'/race-game?track=emerald-loop-v2&weekly=1');
      assert.equal(await banner.getByRole('link',{name:'Все уведомления'}).getAttribute('href'),'/notifications');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      const bounds = await banner.boundingBox();
      const toolbar = await page.locator('.home-toolbar').boundingBox();
      const sidebar = await page.locator('.app-header').boundingBox();
      assert.ok(bounds.y >= toolbar.y + toolbar.height && bounds.y + bounds.height <= 900);
      assert.ok(Math.abs(bounds.x + bounds.width - toolbar.x - toolbar.width) <= 1);
      assert.ok(!sidebar || bounds.x >= sidebar.x + sidebar.width,'The popover leaves the sidebar clear');
      assert.equal((await content.boundingBox()).y,contentTop,'Opening never shifts the page');
      if (process.env.REMINDER_UI_OUTPUT) await page.screenshot({path:`${process.env.REMINDER_UI_OUTPUT}/${theme}-${width}${scale ? '-2x' : ''}.png`});
      await page.keyboard.press('Tab');
      assert.equal(await page.locator(':focus').getAttribute('href'),'/race-game?track=emerald-loop-v2&weekly=1');
      await page.keyboard.press('Escape');
      await banner.waitFor({state:'hidden'});
      assert.equal(await bell.evaluate(element => element === document.activeElement),true);
      await open();
      await page.mouse.click(5,5);
      await banner.waitFor({state:'hidden'});
      if (width !== 1440) {
        await context.close();
        console.log(`${width}px ${theme}${scale ? ' 200%' : ''}: popover fit, keyboard and no layout shift passed`);
        continue;
      }
      await open();
      await banner.getByRole('link',{name:'Все уведомления'}).click();
      await page.waitForURL('**/notifications');
      await banner.waitFor({state:'hidden'});
      await page.goBack();
      await open();
      await banner.getByRole('button',{name:'Скрыть напоминание'}).click();
      assert.equal(await banner.count(),0);
      assert.equal(await page.locator(':focus').getAttribute('href'),'/notifications');
      await page.reload();
      await page.waitForTimeout(700);
      assert.equal(await banner.count(),0,'Dismissal survives reload');
      await clear();
      kind = 'new'; await page.reload();
      await open();
      await banner.getByText('Доступен новый прогноз',{exact:true}).waitFor();
      await banner.getByRole('link',{name:/Сделать прогноз/}).click();
      await page.waitForURL('**/predictions');
      assert.equal(await banner.count(),0,'Action dismisses reminders for this visit');
      await clear();kind='missing';await page.goto(base+'/drivers');
      await open();
      await banner.getByText('Не забудь сохранить прогноз',{exact:true}).waitFor();
      kind='session';await page.reload();
      await open();
      await banner.getByText('Практика 1 через 1 ч',{exact:true}).waitFor();
      kind='week';await page.reload();
      await open();
      await banner.getByText('Новая неделя — новая трасса',{exact:true}).waitFor();
      kind='new';saved=true;await page.reload();
      await open();
      assert.ok(!(await banner.innerText()).includes('прогноз'),'Saved prediction does not nag');
      unavailable=true;await page.reload();await page.waitForTimeout(700);
      assert.equal(await bell.count(),0,'Failed personal lookup does not invent a missing race');
      unavailable=false;kind='overtaken';saved=false;await page.reload();
      await open();
      delayed=true;
      await page.evaluate(async()=>{const {notifyAuthChanged}=await import('/src/helpers/auth.ts');notifyAuthChanged()});
      userId=2;
      await page.evaluate(async()=>{const {notifyAuthChanged}=await import('/src/helpers/auth.ts');notifyAuthChanged()});
      await banner.waitFor({state:'hidden'});
      await open();
      await banner.getByRole('button',{name:'Скрыть напоминание'}).click();
      assert.equal(await page.evaluate(()=>sessionStorage.getItem('f1hub-reminders-closed:1')),null);
      assert.equal(await page.evaluate(()=>sessionStorage.getItem('f1hub-reminders-closed:2')),'1');
      userId = null; kind = 'week'; unread = 0; await page.reload();
      await bell.locator('.notification-reminder-dot').waitFor();
      await open();
      assert.equal(await banner.getByRole('link',{name:'Все уведомления'}).count(),0,'Guests can read public reminders');
      await banner.getByRole('button',{name:'Скрыть напоминание'}).click();
      assert.equal(await page.locator(':focus').getAttribute('class'),'theme-toggle');
      assert.deepEqual(errors,[]);
      console.log(`${width}px: all five reminder types, visibility, dismissal, failure and account switch passed`);
      await context.close();
    }
  } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
