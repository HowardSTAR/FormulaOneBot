// Local profile UI checks with isolated fixture responses.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const options = {frame:{classic:0,red:2,silver:2,gold:3,neon:3},color:{white:0,red:2,blue:2,gold:3,mint:3},background:{carbon:0,grid:2,scarlet:2,aurora:3,champion:3}};
const prediction = {round:2,event_name:'Гран-при Японии',points:30,max_points:40,winner_driver:'VER',second_driver:'NOR',third_driver:'PIA',fourth_driver:'LEC',fifth_driver:'HAM',pole_driver:'VER',fastest_lap_driver:'NOR',first_retirement_driver:'SAI',safety_car:1,sprint_pole_driver:null,sprint_winner_driver:null};
(async () => {
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    for (const width of [320,390,768,1440]) {
      const page = await browser.newPage({viewport:{width,height:1000}});
      const errors=[]; page.on('pageerror', e=>errors.push(e.message));
      let tier=3, owner=true, empty=false, saved=null, shareCount=0;
      const token='p'.repeat(32);
      const shared={token,kind:'profile',title:'Профиль Turbo Racer · TurboTears',subtitle:'Turbo Racer',headline:'30 баллов за сезон 2026',lines:['Лучший прогноз: 30 / 40'],cta:'Открыть профиль',provisional:false,web_url:`http://127.0.0.1:5174/share/${token}`,share_url:`http://127.0.0.1:5174/share/${token}`,mini_app_url:null,image_url:`/api/engagement/shares/${token}/image.jpg`,expires:Date.now()/1000+86400};
      await page.route('**/api/**', route => {
        const path=new URL(route.request().url()).pathname;
        if(path.endsWith('/image.jpg')) return route.fulfill({contentType:'image/jpeg',body:fs.readFileSync('artifacts/profile-share-card.jpg')});
        if(path==='/api/engagement/shares') {shareCount++;assert.equal(route.request().postDataJSON().kind,'profile');return route.fulfill({json:shared});}
        if(path===`/api/engagement/shares/${token}/destination`) return route.fulfill({json:{path:'/profile/1?season=2026'}});
        if(path===`/api/engagement/shares/${token}`) return route.fulfill({json:shared});
        if(path==='/api/profiles/me/style') {saved=route.request().postDataJSON();return route.fulfill({json:{saved:true}});}
        const person={user_id:1,display_name:'Turbo Racer',tier,tier_name:tier===3?'Полный газ':'Участник',supporter:tier>0,style:{frame:'classic',color:'white',background:'carbon'}};
        const data={...person,is_owner:owner,season:2026,seasons:[2026,2025],total_points:empty?0:30,scored_rounds:empty?0:1,options,best_prediction:empty?null:prediction,predictions:empty?[]:[prediction],records:empty?[]:[{track_id:'emerald-loop-v2',track_name:'Emerald Loop',best_time_ms:98432,attempts:12}]};
        return route.fulfill({json:path==='/api/profiles/supporters'?{entries:[{...person,total_points:30,place:1}]}:path.startsWith('/api/profiles/')?data:path==='/api/auth/me'?{id:1,telegram_id:2099386,role:'user'}:{}});
      });
      await page.goto('http://127.0.0.1:5174/profile');
      await page.getByRole('heading',{name:'Turbo Racer'}).waitFor();
      const personalNav=page.getByRole('navigation',{name:'Личный раздел'});
      await personalNav.getByRole('link',{name:'Аккаунт',exact:true}).click();
      await page.locator('.account-hero h1').waitFor();
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),`Account overflow at ${width}`);
      await page.screenshot({path:`artifacts/personal-account-${width}.png`,fullPage:true});
      await personalNav.getByRole('link',{name:'Профиль',exact:true}).click();
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
      assert.deepEqual(errors,[]);
      await page.close();
    }
    console.log('Profiles: 4 viewport sizes; customization, save, predictions, league, empty and visitor states passed.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
