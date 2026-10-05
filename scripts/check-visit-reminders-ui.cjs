// APIs are read-only fixtures. No messages, scores or forecasts are submitted.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.REMINDER_UI_URL || 'http://127.0.0.1:5174';
const now = Date.parse('2026-10-05T12:00:00Z');
const week = {track_id:'emerald-loop-v2',name:'Emerald Loop',start:'2026-10-05T00:00:00Z',end:'2026-10-12T00:00:00Z',entries:[]};
const weekly = {week:'2026-10-05',end:week.end,track_id:week.track_id,name:week.name,time_ms:70000,place:2,alert_id:14,
  rival:{name:'Очень длинное игровое имя быстрого соперника',time_ms:68000}};
const prediction = {status:'ok',season:2026,round:17,event_name:'Singapore Grand Prix',is_open:true,opens_at_utc:'2026-10-05T00:00:00Z',deadline_utc:'2026-10-10T00:00:00Z',prediction:null};
(async()=>{
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    for (const width of [320,390,1440]) {
      const context = await browser.newContext({viewport:{width,height:900}});
      await context.addInitScript(({now})=>{
        Date.now=()=>now;
        localStorage.setItem('turbotears-onboarding-v2',JSON.stringify({status:'completed'}));
      },{now});
      const page = await context.newPage();
      let kind = 'overtaken', unavailable = false, saved = false, userId = 1, delayed = false;
      const errors = [];
      page.on('pageerror',e=>errors.push(e.message));
      await page.route('**/api/**',async route=>{
        const path = new URL(route.request().url()).pathname;
        if (route.request().method()!=='GET') return route.fulfill({json:{ok:true}});
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
        return route.continue();
      });
      const banner = page.getByRole('complementary',{name:'Напоминание'});
      const clear = async()=>page.evaluate(()=>{sessionStorage.clear();localStorage.removeItem('f1hub-reminder:1:overtaken:2026-10-05:14')});
      await page.goto(base+'/drivers');
      await banner.getByText('Твоё время обошли',{exact:true}).waitFor();
      assert.equal(await banner.getByRole('link').getAttribute('href'),'/race-game?track=emerald-loop-v2&weekly=1');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      const bounds = await banner.boundingBox();
      assert.ok(bounds.y>=0 && bounds.y+bounds.height<900,'Reminder is immediately visible');
      await page.screenshot({path:`artifacts/usability-visit-reminder-${width}.png`});
      await banner.getByRole('button',{name:'Закрыть напоминание'}).click();
      assert.equal(await banner.count(),0);
      await page.reload();
      await page.waitForTimeout(700);
      assert.equal(await banner.count(),0,'Dismissal survives reload');
      await clear();
      kind = 'new'; await page.reload();
      await banner.getByText('Доступен новый прогноз',{exact:true}).waitFor();
      await banner.getByRole('link',{name:'Сделать прогноз →'}).click();
      await page.waitForURL('**/predictions');
      assert.equal(await banner.count(),0,'Action dismisses reminders for this visit');
      await clear();kind='missing';await page.goto(base+'/drivers');
      await banner.getByText('Не забудь сохранить прогноз',{exact:true}).waitFor();
      kind='session';await page.reload();
      await banner.getByText('Практика 1 через 1 ч',{exact:true}).waitFor();
      kind='week';await page.reload();
      await banner.getByText('Новая неделя — новая трасса',{exact:true}).waitFor();
      kind='new';saved=true;await page.reload();
      await page.waitForTimeout(700);
      assert.ok(!(await banner.innerText()).includes('прогноз'),'Saved prediction does not nag');
      unavailable=true;await page.reload();await page.waitForTimeout(700);
      assert.equal(await banner.count(),0,'Failed personal lookup does not invent a missing race');
      unavailable=false;kind='overtaken';saved=false;await page.reload();
      await banner.waitFor();
      delayed=true;
      await page.evaluate(async()=>{const {notifyAuthChanged}=await import('/src/helpers/auth.ts');notifyAuthChanged()});
      userId=2;
      await page.evaluate(async()=>{const {notifyAuthChanged}=await import('/src/helpers/auth.ts');notifyAuthChanged()});
      await page.waitForTimeout(800);
      await banner.getByRole('button',{name:'Закрыть напоминание'}).click();
      assert.equal(await page.evaluate(()=>sessionStorage.getItem('f1hub-reminders-closed:1')),null);
      assert.equal(await page.evaluate(()=>sessionStorage.getItem('f1hub-reminders-closed:2')),'1');
      assert.deepEqual(errors,[]);
      console.log(`${width}px: all five reminder types, visibility, dismissal, failure and account switch passed`);
      await context.close();
    }
  } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
