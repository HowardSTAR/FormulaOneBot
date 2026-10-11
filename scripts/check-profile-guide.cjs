const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/sevag/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.env.PROFILE_UI_URL || 'http://127.0.0.1:5174';
const titles=['Твой образ','Сезон в цифрах','Твои прогнозы','Рекорды на трассах','Твоя коллекция','Любимые пилоты и команды','Клуб TurboTears','Покажи свой профиль','Аккаунт и настройки'];
(async()=>{
  fs.mkdirSync('.tmp/profile-guide-ui',{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
    for(const [width,height] of [[320,640],[390,844],[768,1024],[1440,1000],[844,390]]){
      const page=await browser.newPage({viewport:{width,height},reducedMotion:width===320?'reduce':'no-preference'});
      const errors=[];page.on('pageerror',e=>errors.push(e.message));
      let userId=1,owner=true,serverSeen=false,guideWrites=0,failGuide=false,pending=[];
      const earned={id:'oracle:0:0',family:'oracle',season:0,level:0,name:'Оракул паддока',tier:'Бронза',earned_at:'2026-10-11 12:00:00'};
      await page.addInitScript(()=>localStorage.setItem('turbotears-onboarding-v2',JSON.stringify({status:'skipped'})));
      await page.route('**/api/**',async route=>{
        const url=new URL(route.request().url()),path=url.pathname;
        if(path==='/api/auth/me')return route.fulfill({json:{id:userId,email:'test@example.com',telegram_id:7777,email_verified:true,role:'user'}});
        if(path==='/api/profiles/me/guide'){
          guideWrites++;
          if(failGuide)return route.fulfill({status:503,json:{detail:'offline'}});
          serverSeen=true;return route.fulfill({json:{saved:true}});
        }
        if(path.endsWith('/trophies'))return route.fulfill({json:{user_id:userId,season:2026,calendar_known:true,season_closed:false,pending,earned:pending,badge:null,families:[{id:'oracle',name:'Оракул паддока',group:'Прогнозы',levels:[{id:'oracle:0:0',level:0,tier:'Бронза',season:0,earned_at:null,target:1,progress:0,condition:'Угадать победителя основной гонки.',rule:'Только рассчитанные прогнозы.'}]}]}});
        if(path==='/api/profiles/me/trophies/seen'){pending=[];return route.fulfill({json:{saved:true}});}
        if(path.startsWith('/api/profiles/'))return route.fulfill({json:{user_id:userId,is_owner:owner,profile_guide_seen:serverSeen,display_name:'Turbo Racer',tier:0,tier_name:'Участник',supporter:false,style:{frame:'classic',color:'white',background:'carbon'},options:{frame:{classic:0},color:{white:0},background:{carbon:0}},avatar:{helmet:'scarlet',suit:'scarlet',background:'garage'},avatar_options:{helmet:{scarlet:'Алый'},suit:{scarlet:'Алый'},background:{garage:'Гараж'}},season:Number(url.searchParams.get('season'))||2026,seasons:[2026,2025],best_prediction:null,predictions:[],records:[],total_points:0,scored_rounds:0,favorites:{drivers:[],teams:[]}}});
        return route.fulfill({json:path==='/api/next-race'?{status:'season_finished'}:{}});
      });
      await page.goto(base+'/profile');
      const guide=page.getByRole('complementary',{name:'Знакомство с профилем'});
      await guide.waitFor();
      let completion;
      for(let step=0;step<titles.length;step++){
        await guide.getByRole('heading',{name:titles[step],exact:true}).waitFor();
        await page.waitForTimeout(width===320?80:380);
        assert(await guide.evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight+1;}),`guide clipped: ${width}x${height} step ${step}`);
        assert(await guide.evaluate(el=>el.scrollWidth<=el.clientWidth),'text horizontally clipped');
        assert.equal(await page.locator('.first-visit-highlight').count(),1);
        if(step===1){
          pending=[earned];
          await page.evaluate(()=>window.dispatchEvent(new Event('turbotears:trophy-check')));
          await page.waitForTimeout(150);
          assert.equal(await page.locator('.trophy-unlock').count(),0,'reward waits for tour');
          await page.screenshot({path:`.tmp/profile-guide-ui/trophies-${width}x${height}.png`});
        }
        if(titles[step]==='Сезон в цифрах'){
          await page.getByRole('combobox',{name:'Сезон профиля'}).selectOption('2025');
          await page.getByRole('heading',{name:'Прогнозы · 2025',exact:true}).waitFor();
          await guide.getByRole('heading',{name:titles[step],exact:true}).waitFor();
          assert.equal(await page.locator('.profile-season.first-visit-highlight').count(),1,'season switch retains the current step and highlight');
        }
        if(step===titles.length-1)completion=page.waitForResponse(response=>response.url().endsWith('/api/profiles/me/guide')&&response.status()===200);
        await guide.getByRole('button',{name:step===titles.length-1?'Готово, это мой профиль':'Дальше →',exact:true}).click();
      }
      await guide.waitFor({state:'detached'});
      await completion;
      assert(serverSeen);assert.equal(guideWrites,1);
      const reward=page.getByRole('dialog',{name:'Оракул паддока'});await reward.waitFor();
      await reward.getByRole('button',{name:'Забрать трофей',exact:true}).click();
      await reward.waitFor({state:'detached'});
      await page.reload();await page.getByRole('heading',{name:'Turbo Racer',exact:true}).waitFor();
      assert.equal(await guide.count(),0,'completed introduction stays closed');
      assert.equal(await page.locator('html').getAttribute('data-onboarding-active'),null);
      await page.getByRole('button',{name:'Возможности профиля'}).click();await guide.waitFor();
      await page.keyboard.press('Escape');await guide.waitFor({state:'detached'});
      assert.equal(await page.locator('.first-visit-highlight').count(),0);
      owner=false;await page.goto(base+'/profile/99');await page.getByRole('heading',{name:'Turbo Racer',exact:true}).waitFor();
      assert.equal(await guide.count(),0);assert.equal(await page.getByRole('button',{name:'Возможности профиля'}).count(),0);
      owner=true;userId=2;serverSeen=false;failGuide=true;
      await page.goto(base+'/profile');await guide.waitFor();
      await guide.getByRole('button',{name:'Закрыть знакомство с профилем'}).click();await guide.waitFor({state:'detached'});
      await page.reload();await page.getByRole('heading',{name:'Turbo Racer',exact:true}).waitFor();
      assert.equal(await guide.count(),0,'local fallback survives a failed receipt');
      failGuide=false;await page.reload();await page.getByRole('heading',{name:'Turbo Racer',exact:true}).waitFor();
      await page.waitForTimeout(150);assert(serverSeen,'pending receipt retries on next visit');
      userId=3;serverSeen=false;
      await page.evaluate(()=>window.dispatchEvent(new Event('turbotears-auth-changed')));
      await guide.waitFor();
      assert.equal(await guide.getByRole('heading',{name:titles[0],exact:true}).count(),1,'switching account on the same page starts its own introduction');
      await guide.getByRole('button',{name:'Закрыть знакомство с профилем'}).click();
      await guide.waitFor({state:'detached'});
      assert.deepEqual(errors,[]);
      console.log(`${width}x${height} PASS: nine steps, highlights, season changes, reward deferral, persisted completion, replay/Escape, public view, account isolation, offline receipt retry`);
      await page.close();
    }
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
