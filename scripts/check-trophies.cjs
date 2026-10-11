const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/sevag/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const assertProfileLayout=require('./assert-profile-layout.cjs');
const base=process.env.PROFILE_UI_URL || 'http://127.0.0.1:5174';
const ids=['oracle','podium','rhythm','lights','ghost','atlas','grid','heart'];
const names=['Оракул паддока','Идеальная тройка','В ритме сезона','Пять огней','Быстрее своей тени','Без границ','Дирижёр сетки','Сердце проекта'];
const tiers=['Бронза','Серебро','Золото'];
function award(family,level){return{id:`${family}:${family==='rhythm'?2026:0}:${level}`,family,season:family==='rhythm'?2026:0,level,name:names[ids.indexOf(family)],tier:tiers[level],earned_at:'2026-10-11 12:00:00'};}
const earned=[award('rhythm',0),award('ghost',0),award('grid',0),award('grid',1)];
const targets=[[1,5,15],[1,3,7],[3,12,24],[3,3,3],[3,10,25],[1,2,3],[10,15,20],[30,90,365]];
(async()=>{
  fs.mkdirSync('.tmp/trophy-ui',{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
    for(const width of [320,390,768,1440]){
      const page=await browser.newPage({viewport:{width,height:900},reducedMotion:width===320?'reduce':'no-preference'});
      const errors=[];page.on('pageerror',e=>errors.push(e.message));
      let pending=[...earned],badge=null,ackFail=true,owner=true;
      let ackCount=0,badgeCount=0;
      const collection=()=>({user_id:1,season:2026,calendar_known:true,season_closed:false,earned,pending:owner?pending:[],badge,
        families:ids.map((id,i)=>({id,name:names[i],group:i===2?'Участие':i===4?'Гонка':i===6?'Reflex Grid':'Прогнозы',levels:tiers.map((tier,l)=>({id:award(id,l).id,level:l,tier,season:id==='rhythm'?2026:0,target:targets[i][l],progress:i===2?11:i===4?4:i===6?18:0,condition:id==='ghost'?`Завершить ${targets[i][l]} заездов не более чем на 5% медленнее личного рекорда.`:id==='rhythm'?`Сделать прогноз на ${targets[i][l]} Гран-при сезона 2026.`:`Набрать ${targets[i][l]} результатов.`,rule:'Только подтверждённые результаты. Полученные награды сохраняются.',earned_at:earned.some(a=>a.id===award(id,l).id)?'2026-10-11 12:00:00':null})).filter(l=>owner||l.earned_at)})).filter(f=>owner||f.levels.length)});
      await page.addInitScript(()=>localStorage.setItem('turbotears-onboarding-v2',JSON.stringify({status:'skipped'})));
      await page.route('**/api/**',async route=>{
        const path=new URL(route.request().url()).pathname;
        if(path==='/api/auth/me')return route.fulfill({json:{id:1,email:'test@example.com',telegram_id:7777,email_verified:true,role:'user'}});
        if(path==='/api/profiles/me/trophies/seen'){
          ackCount++;
          if(ackFail)return route.fulfill({status:503,json:{detail:'offline'}});
          const ids=route.request().postDataJSON().ids;pending=pending.filter(a=>!ids.includes(a.id));
          return route.fulfill({json:{saved:true}});
        }
        if(path==='/api/profiles/me/trophy-badge'){badgeCount++;badge=earned.find(a=>a.id===route.request().postDataJSON().id)||null;return route.fulfill({json:{saved:true}});}
        if(path.endsWith('/trophies'))return route.fulfill({json:collection()});
        if(path.startsWith('/api/profiles/'))return route.fulfill({json:{user_id:1,display_name:'Turbo Racer',is_owner:owner,profile_guide_seen:true,tier:0,tier_name:'Участник',supporter:false,style:{frame:'classic',color:'white',background:'carbon'},options:{frame:{classic:0},color:{white:0},background:{carbon:0}},avatar:{helmet:'scarlet',suit:'scarlet',background:'garage'},avatar_options:{helmet:{scarlet:'Алый'},suit:{scarlet:'Алый'},background:{garage:'Гараж'}},season:2026,seasons:[2026,2025],total_points:30,scored_rounds:11,best_prediction:null,predictions:[],records:[],favorites:{drivers:[],teams:[]}}});
        return route.fulfill({json:path==='/api/next-race'?{status:'season_finished'}:{}});
      });
      await page.goto(base+'/profile');
      let dialog=page.getByRole('dialog',{name:'В ритме сезона'});
      await dialog.waitFor();
      await page.waitForTimeout(width===320?100:1300);
      assert(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth));
      assert(await dialog.evaluate(el=>el.getBoundingClientRect().left>=0&&el.getBoundingClientRect().right<=innerWidth));
      if(width===320)assert.equal(await dialog.locator('.trophy-unlock-medal').evaluate(el=>getComputedStyle(el).animationName),'none');
      await page.screenshot({path:`.tmp/trophy-ui/unlock-${width}.png`});
      await dialog.getByRole('button',{name:'Следующий трофей →'}).click();
      await dialog.getByRole('alert').waitFor();
      assert.equal(pending.length,4,'failed acknowledgment must retain reward');
      ackFail=false;
      await dialog.getByRole('button',{name:'Следующий трофей →'}).click();
      dialog=page.getByRole('dialog',{name:'Быстрее своей тени'});await dialog.waitFor();
      await page.keyboard.press('Escape');
      dialog=page.getByRole('dialog',{name:'Дирижёр сетки'});await dialog.waitFor();
      await dialog.getByRole('button',{name:'Забрать все · 2'}).click();
      await page.locator('.trophy-unlock').waitFor({state:'detached'});
      assert.equal(pending.length,0);assert.equal(ackCount,4);
      await page.reload();
      await page.locator('.trophy-card').first().waitFor();
      assert.equal(await page.locator('.trophy-unlock').count(),0,'viewed awards never replay on reload');
      assert.equal(await page.locator('.trophy-card').count(),8);
      await assertProfileLayout(page);
      const columns=await page.locator('.trophy-card').evaluateAll(cards=>cards.slice(0,3).map(c=>c.getBoundingClientRect().top));
      assert(columns.every(y=>Math.abs(y-columns[0])<1));
      const rhythm=page.locator('[data-family="rhythm"]');
      await rhythm.locator('.trophy-art').click();
      const details=width<=900?page.locator('.trophy-details-mobile'):rhythm;
      await details.getByRole('button',{name:'Золото',exact:true}).click();
      assert(await details.getByRole('button',{name:'Сначала откройте трофей'}).isDisabled());
      await page.getByRole('button',{name:'Бейдж профиля',exact:true}).click();
      await page.locator('.trophy-badge-picks button').filter({hasText:'Дирижёр сетки'}).filter({hasText:'Бронза'}).click();
      await page.getByRole('button',{name:'Сохранить бейдж'}).click();
      await page.getByRole('status').filter({hasText:'Бейдж профиля сохранён'}).waitFor();
      assert.equal(badgeCount,1);assert.equal(badge.id,'grid:0:0');
      await page.getByRole('img',{name:'Дирижёр сетки, Бронза'}).waitFor();
      await page.getByRole('button',{name:'Коллекция',exact:true}).click();
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow at ${width}`);
      await page.screenshot({path:`.tmp/trophy-ui/collection-${width}.png`,fullPage:true});
      owner=false;await page.goto(base+'/profile/1');
      await page.locator('.trophy-card').first().waitFor();
      assert.equal(await page.locator('.trophy-card').count(),3);
      await assertProfileLayout(page);
      assert.equal(await page.locator('.trophy-equip').count(),0);
      assert.deepEqual(errors,[]);
      console.log(`${width}px PASS: reward queue, failed ack/retry, Escape, bulk receipt, no replay, badge, locked tiers, public collection, reduced motion/layout`);
      await page.close();
    }
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
