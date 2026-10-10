// Local profile UI checks with isolated fixture responses.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
require('node:child_process').execFileSync('.venv/Scripts/python.exe', ['scripts/render-avatar-fixtures.py']);
const options = {frame:{classic:0,red:2,silver:2,gold:3,neon:3},color:{white:0,red:2,blue:2,gold:3,mint:3},background:{carbon:0,grid:2,scarlet:2,aurora:3,champion:3}};
const avatarOptions={helmet:{scarlet:'Алый / полоса',cobalt:'Кобальт / двойная полоса',mint:'Жемчуг / мята'},suit:{scarlet:'Алый / графит',cobalt:'Индиго / лайм',mint:'Графит / мята'},background:{garage:'Ночной бокс',scarlet:'Красный сектор',cobalt:'Синий час',mint:'Полярное сияние',gold:'Золотой подиум'}};
const prediction = {round:2,event_name:'Гран-при Японии',points:30,max_points:40,winner_driver:'VER',second_driver:'NOR',third_driver:'PIA',fourth_driver:'LEC',fifth_driver:'HAM',pole_driver:'VER',fastest_lap_driver:'NOR',first_retirement_driver:'SAI',safety_car:1,sprint_pole_driver:null,sprint_winner_driver:null};
(async () => {
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    for (const width of [320,390,768,1440]) {
      const page = await browser.newPage({viewport:{width,height:1000}});
      const errors=[]; page.on('pageerror', e=>errors.push(e.message));
      let tier=3, owner=true, empty=false, saved=null, shareCount=0;
      let avatar={helmet:'scarlet',suit:'scarlet',background:'garage'}, avatarWrites=0, failAvatar=false;
      let favorites={drivers:['VER'],teams:['McLaren']}, settingsWrites=0, settingsPayload=null;
      const token='p'.repeat(32);
      const shared={token,kind:'profile',title:'Профиль Turbo Racer · TurboTears',subtitle:'Turbo Racer',headline:'30 баллов за сезон 2026',lines:['Лучший прогноз: 30 / 40'],cta:'Открыть профиль',provisional:false,web_url:`http://127.0.0.1:5174/share/${token}`,share_url:`http://127.0.0.1:5174/share/${token}`,mini_app_url:null,image_url:`/api/engagement/shares/${token}/image.jpg`,expires:Date.now()/1000+86400};
      await page.route('**/api/**', route => {
        const path=new URL(route.request().url()).pathname;
        if(path==='/api/drivers') return route.fulfill({json:{drivers:[{code:'VER',name:'Макс Ферстаппен'},{code:'NOR',name:'Ландо Норрис'}]}});
        if(path==='/api/constructors') return route.fulfill({json:{constructors:[{name:'McLaren',constructorId:'mclaren'}]}});
        if(path==='/api/favorites') return route.fulfill({json:favorites});
        if(path==='/api/account/boosty') return route.fulfill({json:{eligible:true,configured:true,active:false,checked_at:1791630000,premium_active:true,premium_override:true}});
        if(path==='/api/favorites/driver') {const code=route.request().postDataJSON().id;favorites={...favorites,drivers:favorites.drivers.includes(code)?favorites.drivers.filter(value=>value!==code):[...favorites.drivers,code]};return route.fulfill({json:{saved:true}});}
        if(path==='/api/account/settings') {
          if(route.request().method()==='POST') {settingsWrites++;settingsPayload=route.request().postDataJSON();}
          return route.fulfill({json:{timezone:'Etc/GMT-3',notify_before:60,notify_before_minutes:[60],notifications_enabled:false,reminder_sessions:31,results_spoiler:false}});
        }
        if(path==='/api/profiles/avatar/v1.png') {
          const query=new URL(route.request().url()).searchParams;
          return route.fulfill({contentType:'image/png',body:fs.readFileSync(`.tmp/profile-avatar-fixtures/${query.get('helmet')}-${query.get('suit')}-${query.get('background')}.png`)});
        }
        if(path==='/api/profiles/me/avatar') {
          if(failAvatar) return route.fulfill({status:503,json:{detail:'Попробуйте ещё раз'}});
          avatarWrites++; avatar=route.request().postDataJSON();return route.fulfill({json:{saved:true}});
        }
        if(path.endsWith('/image.jpg')) return route.fulfill({contentType:'image/jpeg',body:fs.readFileSync('artifacts/profile-share-card.jpg')});
        if(path==='/api/engagement/shares') {shareCount++;assert.equal(route.request().postDataJSON().kind,'profile');return route.fulfill({json:shared});}
        if(path===`/api/engagement/shares/${token}/destination`) return route.fulfill({json:{path:'/profile/1?season=2026'}});
        if(path===`/api/engagement/shares/${token}`) return route.fulfill({json:shared});
        if(path==='/api/profiles/me/style') {saved=route.request().postDataJSON();return route.fulfill({json:{saved:true}});}
        const person={user_id:1,display_name:'Turbo Racer',tier,tier_name:tier===3?'Полный газ':'Участник',supporter:tier>0,style:{frame:'classic',color:'white',background:'carbon'}};
        const data={...person,avatar,avatar_options:avatarOptions,favorites,is_owner:owner,season:2026,seasons:[2026,2025],total_points:empty?0:30,scored_rounds:empty?0:1,options,best_prediction:empty?null:prediction,predictions:empty?[]:[prediction],records:empty?[]:[{track_id:'emerald-loop-v2',track_name:'Emerald Loop',best_time_ms:98432,attempts:12}]};
        return route.fulfill({json:path==='/api/profiles/supporters'?{entries:[{...person,total_points:30,place:1}]}:path.startsWith('/api/profiles/')?data:path==='/api/auth/me'?{id:1,email:'racer@example.com',email_verified:true,telegram_id:2099386,role:'user'}:{}});
      });
      await page.goto('http://127.0.0.1:5174/profile');
      await page.getByRole('heading',{name:'Turbo Racer'}).waitFor();
      const personalNav=page.getByRole('navigation',{name:'Личный раздел'});
      assert.equal(await personalNav.getByRole('link').count(),2);
      await page.getByRole('button',{name:'Сменить аватар',exact:true}).click();
      await page.getByRole('dialog',{name:'Гараж аватаров'}).waitFor();
      await page.keyboard.press('Escape');
      await page.getByRole('dialog',{name:'Гараж аватаров'}).waitFor({state:'detached'});
      assert.ok(await personalNav.evaluate(el=>Array.from(el.querySelectorAll('a')).every(link=>link.getBoundingClientRect().right<=window.innerWidth)),`Personal tabs clipped at ${width}`);
      await personalNav.getByRole('link',{name:'Аккаунт',exact:true}).click();
      await page.locator('.account-hero h1').waitFor();
      await page.getByRole('heading',{name:'Подписка Boosty'}).waitFor();
      assert.ok(await personalNav.evaluate(el=>el.classList.contains('personal-hub-switch-account')));
      await page.waitForFunction(()=>{
        const nav=document.querySelector('.personal-hub-switch');
        const slider=nav.querySelector('.personal-hub-slider').getBoundingClientRect();
        const active=nav.querySelector('a.active').getBoundingClientRect();
        return Math.abs(slider.left-active.left)<1 && Math.abs(slider.width-active.width)<1;
      });
      if(width>820) assert.ok(await page.locator('.account-grid').evaluate(el=>{
        const left=el.querySelector('.account-overview').getBoundingClientRect();
        const right=el.querySelector('.account-details').getBoundingClientRect();
        const cards=el.querySelectorAll('.account-overview > section');
        return Math.abs(left.top-right.top)<2 && right.left>=left.right && cards[1].getBoundingClientRect().top-cards[0].getBoundingClientRect().bottom<=17;
      }), 'Account columns flow independently with a compact gap');
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),`Account overflow at ${width}`);
      await page.screenshot({path:`artifacts/personal-account-${width}.png`,fullPage:true});
      await personalNav.getByRole('link',{name:'Профиль',exact:true}).click();
      let following=page.locator('.profile-favorites');
      await following.getByRole('link',{name:'VER Макс Ферстаппен'}).waitFor();
      await following.getByRole('link',{name:'Изменить избранное'}).click();
      await page.getByRole('heading',{name:'Избранное',exact:true}).waitFor();
      await Promise.all([page.waitForResponse(response=>response.url().endsWith('/api/favorites/driver')),page.getByRole('button',{name:'Ландо Норрис NOR'}).click()]);
      await personalNav.getByRole('link',{name:'Профиль',exact:true}).click();
      following=page.locator('.profile-favorites');
      await following.getByRole('link',{name:'NOR Ландо Норрис'}).waitFor();
      await following.getByRole('link',{name:'McLaren'}).waitFor();
      assert.ok((await following.getByRole('link',{name:'McLaren'}).getAttribute('href')).includes('constructorId=mclaren'));
      await page.locator('.personal-hub-header').getByRole('link',{name:'Настройки',exact:true}).click();
      await page.getByRole('heading',{name:'Настройки',exact:true}).waitFor();
      await page.locator('label[aria-label="Скрывать фото результатов в Telegram"]').click();
      await page.getByRole('button',{name:'Сохранить настройки'}).click();
      await page.getByRole('status').filter({hasText:'Настройки сохранены ✅'}).waitFor();
      assert.equal(settingsPayload.results_spoiler,true);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),`Settings overflow at ${width}`);
      await page.screenshot({path:`artifacts/personal-settings-${width}.png`,fullPage:true});
      await personalNav.getByRole('link',{name:'Профиль',exact:true}).click();
      assert.equal(settingsWrites,1);
      await page.getByRole('button',{name:'Изменить аватар',exact:true}).click();
      let editor=page.getByRole('dialog',{name:'Гараж аватаров'});
      await editor.getByRole('button',{name:'Кобальт / двойная полоса'}).click();
      await editor.getByRole('button',{name:'Графит / мята'}).click();
      await editor.getByRole('button',{name:'Золотой подиум'}).click();
      assert.ok((await editor.getByAltText('Предпросмотр выбранного гонщика').getAttribute('src')).includes('helmet=cobalt&suit=mint&background=gold'));
      assert.ok(await editor.evaluate(el=>el.scrollWidth<=el.clientWidth),`Avatar dialog overflow at ${width}`);
      await page.screenshot({path:`artifacts/avatar-editor-${width}.png`});
      failAvatar=true;
      await editor.getByRole('button',{name:'Сохранить аватар'}).click();
      await editor.getByRole('alert').waitFor();
      failAvatar=false;
      await editor.getByRole('button',{name:'Сохранить аватар'}).click();
      await editor.waitFor({state:'detached'});
      assert.deepEqual(avatar,{helmet:'cobalt',suit:'mint',background:'gold'});
      assert.equal(avatarWrites,1);
      await page.getByRole('button',{name:'Изменить аватар',exact:true}).click();
      editor=page.getByRole('dialog',{name:'Гараж аватаров'});
      assert.equal(await editor.getByRole('button',{name:'Графит / мята'}).getAttribute('aria-pressed'),'true');
      await editor.getByRole('button',{name:'Алый / полоса'}).click();
      await page.keyboard.press('Escape');
      await editor.waitFor({state:'detached'});
      assert.equal(avatarWrites,1);
      assert.ok((await page.getByRole('button',{name:'Изменить аватар',exact:true}).locator('img').getAttribute('src')).includes('helmet=cobalt'));
      await page.getByRole('button',{name:'Поделиться профилем'}).click();
      await page.getByRole('dialog').locator('.share-preview').waitFor();
      assert.equal(shareCount,1);
      await page.screenshot({path:`artifacts/profile-sharing-${width}.png`,fullPage:true});
      await page.getByRole('button',{name:'Закрыть отправку'}).click();
      assert.equal(await page.locator('.profile-highlight strong').innerText(),'30 / 40 баллов');
      await page.getByRole('button',{name:'Неон',exact:true}).click();
      await page.getByRole('button',{name:'Мятный',exact:true}).click();
      await page.getByRole('button',{name:'Сияние',exact:true}).click();
      await page.getByRole('button',{name:'Сохранить оформление'}).click();
      await page.getByRole('status').filter({hasText:'Оформление сохранено'}).waitFor();
      assert.deepEqual(saved,{frame:'neon',color:'mint',background:'aurora'});
      await page.locator('.profile-prediction summary').click();
      assert.equal(await page.locator('.profile-answers dd').first().innerText(),'VER');
      await page.getByRole('button',{name:'Показать зачёт · 2026'}).click();
      await page.locator('.profile-league li').waitFor();
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),`Overflow at ${width}`);
      await page.screenshot({path:`artifacts/user-profile-${width}.png`,fullPage:true});
      tier=0;empty=true;
      await page.reload();
      await page.getByText('Первый результат ещё впереди').waitFor();
      assert.equal(await page.getByRole('button',{name:'Неон'}).isDisabled(),true);
      owner=false;
      await page.goto(`http://127.0.0.1:5174/share/${token}`);
      await page.getByRole('button',{name:'Открыть профиль',exact:true}).click();
      await page.getByText('Ответы показываются после начисления баллов.').waitFor();
      assert.ok(page.url().includes('/profile/1?season=2026'));
      await page.goto('http://127.0.0.1:5174/profile/2');
      await page.getByText('Ответы показываются после начисления баллов.').waitFor();
      assert.equal(await page.getByRole('heading',{name:'Твой стиль'}).count(),0);
      assert.equal(await page.getByRole('button',{name:'Изменить аватар',exact:true}).count(),0);
      await page.locator('.profile-favorites').getByRole('link',{name:'NOR Ландо Норрис'}).waitFor();
      assert.equal(await page.getByRole('link',{name:'Изменить избранное'}).count(),0);
      assert.deepEqual(errors,[]);
      await page.close();
    }
    console.log('Profiles: 4 viewport sizes; customization, save, predictions, league, empty and visitor states passed.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
