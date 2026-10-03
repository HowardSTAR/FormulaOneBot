// Local UI checks. All APIs are intercepted; no Telegram messages are sent.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.COMMUNITY_UI_URL || 'http://127.0.0.1:5174';
const current = {track_id:'emerald-loop', name:'Новая трасса', start:'2026-10-05T00:00:00Z', end:'2099-10-12T00:00:00Z', entries:[]};
const previous = {track_id:'canyon-switchback', name:'Прошлая трасса', start:'2026-09-28T00:00:00Z', end:'2026-10-05T00:00:00Z', entries:[
  {name:'Первый победитель с достаточно длинным игровым именем',time_ms:61001},
  {name:'Второй победитель',time_ms:61001}, {name:'Третий участник',time_ms:65000},
]};
(async () => {
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    for (const width of [320,390,1440]) {
      const context = await browser.newContext({viewport:{width,height:900}});
      const page = await context.newPage();
      const errors = [];
      let fail = false, empty = false;
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/api/**', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/auth/me') return route.fulfill({status:401,json:{detail:'Guest'}});
        if (url.pathname === '/api/engagement/weekly') {
          if (url.searchParams.get('period') === 'previous') {
            assert.equal(url.searchParams.get('week'),'2026-09-28');
            if (fail) return route.fulfill({status:503,json:{detail:'Unavailable'}});
            return route.fulfill({json:{...previous,entries:empty ? [] : previous.entries}});
          }
          return route.fulfill({json:current});
        }
        return route.fulfill({json:{status:'none',items:[],entries:[],unread:0}});
      });
      await page.goto(`${base}/community?weekly=previous&week=2026-09-28`);
      await page.getByRole('heading',{name:'Итоги недели · Закончилась'}).waitFor();
      await page.getByText('Второй победитель',{exact:false}).waitFor();
      const results = page.locator('#previous-week-results');
      assert.equal(await results.locator('li').count(),3);
      assert.equal((await results.innerText()).split('🏆').length-1,2);
      assert.equal(await page.getByRole('link',{name:'Проехать три круга →'}).getAttribute('href'),'/race-game?track=emerald-loop&weekly=1');
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.getByRole('button',{name:'Скрыть итоги прошлой недели'}).click();
      assert.equal(await results.count(),0);
      await page.getByRole('button',{name:'Итоги прошлой недели',exact:true}).click();
      await page.getByText('Второй победитель',{exact:false}).waitFor();
      if (width === 390) {
        await page.screenshot({path:'artifacts/community-weekly-mobile.png',fullPage:true});
        fail = true;
        await page.reload();
        await page.getByText('Не удалось загрузить итоги.',{exact:false}).waitFor();
        fail = false; empty = true;
        await results.getByRole('button',{name:'Повторить'}).click();
        await page.getByText('Сохранённых заездов не было — победителя нет.').waitFor();
      }
      assert.deepEqual(errors,[]);
      console.log(`Community weekly: ${width}px passed`);
      await context.close();
    }
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exitCode=1;});
