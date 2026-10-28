// Local UI checks. All APIs are intercepted; no records or messages are sent.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.COMMUNITY_UI_URL || 'http://127.0.0.1:5174';
const current = {track_id:'emerald-loop-v2', name:'Emerald Loop', start:'2026-10-05T00:00:00Z', end:'2099-10-12T00:00:00Z', entries:[]};
const previous = {track_id:'canyon-switchback-v1', name:'Прошлая трасса', start:'2026-09-28T00:00:00Z', end:'2026-10-05T00:00:00Z', entries:[
  {name:'Первый победитель с достаточно длинным игровым именем',time_ms:61001},
  {name:'Второй победитель',time_ms:61001}, {name:'Третий участник',time_ms:65000},
]};
(async () => {
  const browser = await chromium.launch({channel:process.env.PLAYWRIGHT_CHANNEL || 'chrome',headless:true});
  try {
    for (const theme of ['light','dark']) for (const width of [320,390,899,900,1440,1920,2560]) {
      const context = await browser.newContext({viewport:{width,height:1000},colorScheme:theme});
      await context.addInitScript(theme => localStorage.setItem('turbotears-theme',theme),theme);
      const page = await context.newPage();
      const errors = [];
      let fail = false, empty = false, weeklyFail = false, mineFail = false, revokeFail = true, revoked = false;
      const member = width === 1440;
      let expectedWeek = '2026-09-28';
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/api/**', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/auth/me') return route.fulfill(member ? {json:{id:1,email:'demo@example.test',telegram_id:null,email_verified:true,role:'user',display_name:'Демо',telegram_username:null}} : {status:401,json:{detail:'Guest'}});
        if (url.pathname.endsWith('/revoke')) {
          if (revokeFail) return route.fulfill({status:503,json:{detail:'Unavailable'}});
          revoked = true;
          return route.fulfill({json:{ok:true}});
        }
        if (url.pathname === '/api/engagement/weekly/me') return route.fulfill({json:{user_id:1,weekly:null}});
        if (url.pathname === '/api/predictions/leagues') return route.fulfill({json:{leagues:[{id:7,name:'Наша паддок-компания',mode:'cup',season:2025}]}});
        if (url.pathname === '/api/engagement/mine') return route.fulfill(mineFail ? {status:503,json:{detail:'Unavailable'}} : {json:{referrals:{arrived:4,activated:2,returned:1},badges:['Первый старт'],shares:[{token:'demo',title:'Мой результат с длинным названием трассы и участника',active:!revoked}]}});
        if (url.pathname === '/api/engagement/weekly') {
          if (url.searchParams.get('period') === 'previous') {
            assert.equal(url.searchParams.get('week'),expectedWeek);
            if (fail) return route.fulfill({status:503,json:{detail:'Unavailable'}});
            return route.fulfill({json:{...previous,entries:empty ? [] : previous.entries}});
          }
          return route.fulfill(weeklyFail ? {status:503,json:{detail:'Unavailable'}} : {json:current});
        }
        return route.fulfill({json:{status:'none',items:[],entries:[],unread:0}});
      });
      await page.goto(`${base}/community?weekly=previous&week=2026-09-28`);
      await page.getByRole('heading',{name:'Сообщество',exact:true}).waitFor();
      await page.getByText('Второй победитель',{exact:false}).waitFor();
      const results = page.locator('#previous-week-results');
      assert.equal(await results.locator('li').count(),3);
      assert.equal((await results.innerText()).split('🏆').length-1,2);
      assert.equal(await page.getByRole('link',{name:'Проехать три круга',exact:true}).getAttribute('href'),'/race-game?track=emerald-loop-v2&weekly=1');
      assert.equal(await page.getByRole('link',{name:/^Мой прогноз/}).getAttribute('href'),'/predictions');
      assert.equal(await page.getByRole('link',{name:'Создать лигу или мини-чемпионат',exact:true}).getAttribute('href'),member?'/predictions?tab=leagues':'/account?returnTo=leagues');
      await page.getByRole('img',{name:'Схема трассы Emerald Loop'}).waitFor();
      const titleBox=await page.getByRole('heading',{name:'Сообщество',exact:true}).boundingBox();
      assert.ok(titleBox.y < 112, 'Page title should share the top band with desktop tools');
      const pause=page.getByRole('button',{name:'Пауза демонстрации трассы',exact:true});
      await pause.click();
      const car=page.locator('.community-demo-car');
      const paused=await car.getAttribute('transform');
      await page.waitForTimeout(120);
      assert.equal(await car.getAttribute('transform'),paused);
      await page.getByRole('button',{name:'Продолжить демонстрацию трассы',exact:true}).click();
      await page.waitForTimeout(120);
      assert.notEqual(await car.getAttribute('transform'),paused);
      await page.getByRole('button',{name:'Пауза демонстрации трассы',exact:true}).click();
      await page.locator('.community-rules summary').click();
      await page.getByText('Завершите три круга и сохраните результат,', {exact:false}).waitFor();
      await page.locator('.community-rules summary').click();
      if(width >= 900) {
        assert.equal(await page.locator('.app-header a[aria-current="page"]').count(),1);
        const link=page.locator('.app-header a[aria-current="page"]');
        assert.equal(await link.innerText(),'Сообщество');
        assert.equal(await link.locator('xpath=..').getAttribute('class'),'app-header-section');
        assert.equal(await page.getByRole('button',{name:'С друзьями',exact:true}).count(),0);
        await page.keyboard.press('Tab');
        await link.focus();
        assert.ok(await link.evaluate(el=>getComputedStyle(el).outlineStyle !== 'none'));
        await link.hover();
        assert.equal(await link.evaluate(el=>getComputedStyle(el).textDecorationLine),'none');
      }
      assert.equal(await page.locator('.home-toolbar:visible').count(),1);
      assert.equal(await page.locator('.account-shortcut-bar:visible').count(),0);
      await page.getByRole('button',{name:'Скрыть итоги прошлой недели'}).click();
      assert.equal(await results.count(),0);
      await page.getByRole('button',{name:'Итоги прошлой недели',exact:true}).click();
      await page.getByText('Второй победитель',{exact:false}).waitFor();
      if (member) {
        await page.getByRole('link',{name:/Наша паддок-компания/}).waitFor();
        assert.equal(await page.getByRole('link',{name:/Наша паддок-компания/}).getAttribute('href'),'/predictions?tab=leagues&league=7&season=2025');
        await page.getByText('Первый старт',{exact:true}).waitFor();
        await page.locator('.community-shares summary').click();
        await page.getByRole('button',{name:'Отозвать ссылку',exact:true}).click();
        await page.getByRole('alert').filter({hasText:'Не удалось отозвать ссылку'}).waitFor();
        revokeFail=false;
        await page.getByRole('button',{name:'Отозвать ссылку',exact:true}).click();
        await page.getByText('Истекла или недоступна',{exact:true}).waitFor();
      }
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      if ([390,1440].includes(width)) {
        await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
        await page.screenshot({path:`/tmp/community-${theme}-${width}.png`,fullPage:true});
        await page.evaluate(()=>document.documentElement.style.fontSize='200%');
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),'200% text overflow');
        await page.screenshot({path:`/tmp/community-${theme}-${width}-200.png`,fullPage:true});
        await page.evaluate(()=>document.documentElement.style.fontSize='');
      }
      if (width === 390) {
        fail = true;
        await page.reload();
        await page.getByText('Не удалось загрузить итоги.',{exact:true}).waitFor();
        fail = false; empty = true;
        await results.getByRole('button',{name:'Повторить'}).click();
        await page.getByText('Сохранённых заездов не было — победителя нет.').waitFor();
        weeklyFail = true;
        await page.reload();
        const alert=page.getByRole('alert').filter({hasText:'Не удалось загрузить трассу недели.'});
        await alert.waitFor();
        assert.equal(await page.getByRole('status').filter({hasText:'Загружаем соревнование…'}).count(),0);
        weeklyFail=false;
        await alert.getByRole('button',{name:'Повторить'}).click();
        await page.getByRole('link',{name:'Проехать три круга',exact:true}).waitFor();
      }
      if (member) {
        mineFail=true;await page.reload();
        const alert=page.getByRole('alert').filter({hasText:'Личный раздел временно недоступен.'});
        await alert.waitFor();mineFail=false;
        await alert.getByRole('button',{name:'Повторить'}).click();
        await page.getByText('Первый старт',{exact:true}).waitFor();
      }
      if (width === 900) {
        expectedWeek = null;
        const direct = page.locator('.app-header a[aria-current="page"]');
        await direct.focus();await page.keyboard.press('Enter');
        await page.waitForURL(`${base}/community`);
        await page.getByRole('heading',{name:'Сообщество',exact:true}).waitFor();
      }
      assert.deepEqual(errors,[]);
      console.log(`Community: ${theme}, ${width}px passed`);
      await context.close();
    }
    // Real track geometry, competition ties, personal pace and league recovery.
    for (const theme of ['light','dark']) for (const [index,track] of require('../app/race_tracks.json').entries()) {
      const width=index%2 ? 390 : 1440;
      const context=await browser.newContext({viewport:{width,height:1000},colorScheme:theme});
      const page=await context.newPage();
      let paceFail=false,leaguesFail=false,stalePace=false;
      const entries=Array.from({length:8},(_,i)=>({name:i===0?'Лидер с длинным именем участника':`Гонщик ${i+1}`,time_ms:i<2?61001:61001+i*1300}));
      await page.route('**/api/**',route=>{
        const path=new URL(route.request().url()).pathname;
        if(path==='/api/auth/me')return route.fulfill({json:{id:1,email:null,telegram_id:55,email_verified:false,role:'user',display_name:'Демо',telegram_username:'demo'}});
        if(path==='/api/engagement/weekly')return route.fulfill({json:{...current,track_id:track.id,name:track.name,entries}});
        if(path==='/api/engagement/weekly/me')return route.fulfill(paceFail?{status:503,json:{detail:'Unavailable'}}:{json:{user_id:1,weekly:{week:stalePace?'2026-09-28':'2026-10-05',track_id:track.id,time_ms:65000,place:4,rival:{name:'Лидер',time_ms:61001},end:current.end}}});
        if(path==='/api/predictions/leagues')return route.fulfill(leaguesFail?{status:503,json:{detail:'Unavailable'}}:{json:{leagues:[{id:12,name:'Своя лига',mode:'season',season:null}]}});
        if(path==='/api/engagement/mine')return route.fulfill({json:{referrals:{arrived:0,activated:0,returned:0},badges:index===1?['Собрал первую лигу']:[],shares:[]}});
        return route.fulfill({json:{status:'none',items:[],entries:[],unread:0}});
      });
      await page.goto(`${base}/community`);
      const map=page.getByRole('img',{name:`Схема трассы ${track.name}`});await map.waitFor();
      assert.equal(await map.locator('.community-track-road').getAttribute('points'),[...track.centerLine,track.centerLine[0]].map(p=>p.join(',')).join(' '));
      assert.equal(await page.getByRole('link',{name:'Проехать три круга',exact:true}).getAttribute('href'),`/race-game?track=${track.id}&weekly=1`);
      await page.locator('.community-pace').waitFor();
      await page.getByRole('heading',{name:'Друзья и достижения',exact:true}).waitFor();
      assert.equal(await page.locator('.community-referrals').count(),0,'Hide empty referral counters');
      assert.equal(await page.locator('.community-achievements li').count(),3);
      assert.equal(await page.locator('.community-achievements li.is-earned').count(),index===1?1:0);
      assert.match(await page.locator('.community-pace').innerText(),/#4/);
      assert.equal(await page.locator('#community-current-results li').count(),5);
      assert.equal(await page.locator('#community-current-results .community-place').nth(1).innerText(),'1');
      assert.equal(await page.locator('#community-current-results .community-place').nth(2).innerText(),'3');
      const expand=page.getByRole('button',{name:'Показать ещё (3)',exact:true});await expand.focus();await page.keyboard.press('Enter');
      assert.equal(await page.locator('#community-current-results li').count(),8);
      await page.getByRole('button',{name:'Свернуть таблицу',exact:true}).click();
      assert.equal(await page.locator('#community-current-results li').count(),5);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0)});
      await page.screenshot({path:`/tmp/community-rich-${theme}-${index}.png`,fullPage:true});
      if(index===0){
        paceFail=true;leaguesFail=true;await page.reload();
        const paceError=page.getByRole('alert').filter({hasText:'Не удалось загрузить ваше время.'});
        const leagueError=page.getByRole('alert').filter({hasText:'Не удалось загрузить ваши лиги.'});
        await paceError.waitFor();await leagueError.waitFor();
        paceFail=false;leaguesFail=false;await leagueError.getByRole('button',{name:'Повторить'}).click();
        await page.locator('.community-pace').waitFor();await page.getByRole('link',{name:/Своя лига/}).waitFor();
        stalePace=true;await page.reload();await map.waitFor();await page.locator('.community-target').waitFor();
        assert.equal(await page.locator('.community-pace').count(),0);
      }
      console.log(`Community challenge: ${theme}, ${track.id} passed`);await context.close();
    }
    const motionContext=await browser.newContext({viewport:{width:390,height:1000},reducedMotion:'reduce'});
    const motionPage=await motionContext.newPage();
    await motionPage.route('**/api/**',route=>{
      const path=new URL(route.request().url()).pathname;
      return route.fulfill(path==='/api/auth/me'?{status:401,json:{detail:'Guest'}}:{json:path==='/api/engagement/weekly'?current:{status:'none',items:[],entries:[],unread:0}});
    });
    await motionPage.goto(`${base}/community`);
    await motionPage.getByRole('img',{name:'Схема трассы Emerald Loop'}).waitFor();
    const demoCar=motionPage.locator('.community-demo-car');
    const still=await demoCar.getAttribute('transform');await motionPage.waitForTimeout(200);
    assert.equal(await demoCar.getAttribute('transform'),still);
    assert.equal(await motionPage.locator('.community-demo-control').count(),0);
    await motionPage.emulateMedia({reducedMotion:'no-preference'});
    await motionPage.waitForTimeout(9500);
    assert.equal(await motionPage.getByRole('button',{name:'Пауза демонстрации трассы',exact:true}).count(),1);
    const afterLap=await demoCar.getAttribute('transform');
    await motionPage.waitForTimeout(180);
    assert.notEqual(await demoCar.getAttribute('transform'),afterLap);
    await motionPage.getByRole('button',{name:'Пауза демонстрации трассы',exact:true}).click();
    const pausedLap=await demoCar.getAttribute('transform');
    await motionPage.waitForTimeout(180);
    assert.equal(await demoCar.getAttribute('transform'),pausedLap);
    await motionPage.getByRole('button',{name:'Продолжить демонстрацию трассы',exact:true}).click();
    await motionPage.getByRole('button',{name:'Пауза демонстрации трассы',exact:true}).waitFor();
    await motionPage.waitForTimeout(150);
    assert.notEqual(await demoCar.getAttribute('transform'),still);
    await motionPage.emulateMedia({reducedMotion:'reduce',contrast:'more'});
    assert.ok(await motionPage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    console.log('Community: reduced motion, continuous laps, pause/resume and high contrast passed');
    await motionContext.close();
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exitCode=1;});
