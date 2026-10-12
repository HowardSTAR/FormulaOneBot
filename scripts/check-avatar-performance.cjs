// Actual browser checks: cold/failing loads, offline edits, fixed geometry,
// bounded DOM, save/reopen, focus restoration and rendering under 6x CPU slowdown.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.PROFILE_UI_URL || 'http://127.0.0.1:5174';
require('node:child_process').execFileSync('.venv/Scripts/python.exe', ['scripts/render-avatar-fixtures.py']);
const initial = { helmet:'scarlet', suit:'scarlet', background:'garage' };
const avatarOptions = {helmet:{scarlet:'Алый / полоса',cobalt:'Кобальт / двойная полоса',mint:'Жемчуг / мята'},suit:{scarlet:'Алый / графит',cobalt:'Индиго / лайм',mint:'Графит / мята'},background:{garage:'Ночной бокс',scarlet:'Красный сектор',cobalt:'Синий час',mint:'Полярное сияние',gold:'Золотой подиум'}};
const options = {frame:{classic:0,red:2,gold:3},color:{white:0,red:2,gold:3},background:{carbon:0,grid:2,champion:3}};
const fixture = {user_id:1,display_name:'Turbo Racer',is_owner:true,profile_guide_seen:true,supporter:true,tier:3,tier_name:'Полный газ',style:{frame:'classic',color:'white',background:'carbon'},avatar_options:avatarOptions,options,season:2026,seasons:[2026],total_points:0,scored_rounds:0,best_prediction:null,predictions:[],records:[],favorites:{drivers:[],teams:[]}};
const portrait = page => page.locator('.avatar-editor-preview>.avatar-portrait');
const open = page => page.getByRole('button',{name:'Аватар и оформление',exact:true}).click();
const frames = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
async function geometry(page) {
  return page.locator('.avatar-editor').evaluate(dialog => [dialog.querySelector('.avatar-editor-preview>.avatar-image'),...dialog.querySelectorAll('.avatar-editor-options button')].map(el => [el.offsetLeft,el.offsetTop,el.offsetWidth,el.offsetHeight]));
}
async function expectAvatar(page, avatar) {
  for(const [part,value] of Object.entries(avatar)) assert.equal(await portrait(page).getAttribute(`data-${part}`),value);
  assert.equal(await page.locator('.avatar-editor-options button[aria-pressed="true"]').count(),3);
}
(async () => {
  fs.mkdirSync('.tmp/avatar-loading',{recursive:true});
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const reports = [];
  try {
    for(const [width,height] of [[320,640],[390,844],[768,1024],[844,390],[1440,1000]]) {
      const page = await browser.newPage({viewport:{width,height},deviceScaleFactor:width<800?3:1,hasTouch:width<900});
      const cdp = await page.context().newCDPSession(page);
      await cdp.send('Emulation.setCPUThrottlingRate',{rate:6});
      let saved={...initial},writes=0,spriteRequests=0,portraitRequests=0,failSprites=true,holdSprites=true,release;
      const gate=new Promise(resolve=>{release=resolve;});
      const errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.route('**/*-v1*.webp*',async route=>{
        if(route.request().resourceType()!=='image') return route.continue();
        spriteRequests++;
        if(holdSprites) await gate;
        if(failSprites) return route.fulfill({status:503,body:'Unavailable'});
        return route.continue();
      });
      await page.route('**/api/**',async route=>{
        const url=new URL(route.request().url()),path=url.pathname;
        if(path==='/api/profiles/avatar/v1.png') {
          portraitRequests++;
          const key=['helmet','suit','background'].map(part=>url.searchParams.get(part)).join('-');
          return route.fulfill({contentType:'image/png',body:fs.readFileSync(`.tmp/profile-avatar-fixtures/${key}.png`)});
        }
        if(path==='/api/profiles/me/avatar') {writes++;saved=route.request().postDataJSON();return route.fulfill({json:{saved:true}});}
        if(path.endsWith('/trophies')) return route.fulfill({json:{user_id:1,season:2026,families:[],earned:[],pending:[],badge:null}});
        if(path==='/api/auth/me') return route.fulfill({json:{id:1,email:'racer@example.test',email_verified:true,telegram_id:2099386,role:'user'}});
        if(path==='/api/profiles/supporters') return route.fulfill({json:{season:2026,current_user_id:1,entries:[]}});
        if(path==='/api/account/boosty') return route.fulfill({json:{can_check:true,active:false}});
        return route.fulfill({json:path.startsWith('/api/profiles/')?{...fixture,avatar:saved}:{}});
      });
      await page.goto(`${base}/profile`,{waitUntil:'domcontentloaded'});
      try { await open(page); } catch(error) {
        console.error('Browser errors:',errors,'Body:',await page.locator('body').innerText());
        throw error;
      }
      await page.getByAltText('Предпросмотр выбранного гонщика').waitFor();
      const before=await geometry(page);
      await page.getByRole('button',{name:'Жемчуг / мята',exact:true}).click();
      holdSprites=false;release();
      await page.getByRole('button',{name:'Повторить загрузку образов'}).waitFor();
      assert.equal(await portrait(page).count(),0,'Failed atlases retain the saved portrait');
      failSprites=false;
      await page.getByRole('button',{name:'Повторить загрузку образов'}).click();
      await portrait(page).waitFor();
      await expectAvatar(page,{...initial,helmet:'mint'});
      assert.deepEqual(await geometry(page),before,'Atlas loading retains image/control geometry');
      assert.equal(await page.locator('.avatar-editor').evaluate(dialog=>getComputedStyle(dialog,'::backdrop').backdropFilter),'none');
      assert.equal(await page.locator('html').evaluate(el=>el.style.overflow),'hidden');
      assert.equal(await page.locator('.avatar-editor').evaluate(dialog=>dialog.scrollWidth<=dialog.clientWidth),true,'No horizontal overflow');
      const requestsBefore={sprites:spriteRequests,portraits:portraitRequests};
      const timings=await page.evaluate(async()=>{
        const fieldsets=[...document.querySelectorAll('.avatar-editor-options fieldset')];
        const buttons=fieldsets.map(fieldset=>[...fieldset.querySelectorAll('button')]);
        const times=[];
        for(const helmet of buttons[0]) for(const suit of buttons[1]) for(const background of buttons[2]) {
          const start=performance.now();
          helmet.click();suit.click();background.click();
          await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
          const selected=fieldsets.map(fieldset=>fieldset.querySelector('button[aria-pressed="true"]'));
          if(selected[0]!==helmet||selected[1]!==suit||selected[2]!==background) throw new Error('Lost a rapid selection');
          if(document.querySelectorAll('.avatar-editor .avatar-portrait').length!==12) throw new Error('Portrait DOM grows while selecting');
          times.push(performance.now()-start);
        }
        return times;
      });
      await expectAvatar(page,{helmet:'mint',suit:'mint',background:'gold'});
      assert.deepEqual({sprites:spriteRequests,portraits:portraitRequests},requestsBefore,'45 combinations cause zero image requests');
      const interaction = await page.evaluate(async()=>{
        const choices=[...document.querySelectorAll('.avatar-editor-options fieldset:first-child button')];
        const clicks=[],scroll=[];
        for(let index=0;index<30;index++) {
          const start=performance.now();choices[index%choices.length].click();
          await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
          clicks.push(performance.now()-start);
        }
        const dialog=document.querySelector('.avatar-editor');
        for(let index=0;index<45;index++) {
          const start=performance.now();
          dialog.scrollTop=(dialog.scrollHeight-dialog.clientHeight)*index/44;
          await new Promise(resolve=>requestAnimationFrame(resolve));
          scroll.push(performance.now()-start);
        }
        dialog.scrollTop=0;
        return {clicks,scroll};
      });
      await page.context().setOffline(true);
      await page.getByRole('button',{name:'Кобальт / двойная полоса',exact:true}).click();
      await frames(page);
      await expectAvatar(page,{helmet:'cobalt',suit:'mint',background:'gold'});
      await page.context().setOffline(false);
      await page.locator('.avatar-editor').evaluate(dialog=>{dialog.scrollTop=dialog.scrollHeight;});
      await page.getByRole('button',{name:'Сохранить изменения',exact:true}).click();
      await page.getByRole('dialog').waitFor({state:'detached'});
      assert.equal(writes,1);
      assert.deepEqual(saved,{helmet:'cobalt',suit:'mint',background:'gold'});
      assert.equal(await page.locator('html').evaluate(el=>el.style.overflow),'');
      assert.equal(await page.getByRole('button',{name:'Аватар и оформление',exact:true}).evaluate(el=>el===document.activeElement),true);
      await page.emulateMedia({reducedMotion:'reduce'});
      await open(page);await portrait(page).waitFor();
      await expectAvatar(page,saved);
      assert.equal(await page.locator('.avatar-editor').evaluate(dialog=>getComputedStyle(dialog).animationName),'none');
      await page.screenshot({path:`.tmp/avatar-loading/editor-${width}.png`});
      await page.keyboard.press('Escape');
      await page.getByRole('dialog').waitFor({state:'detached'});
      assert.deepEqual(errors,[]);
      timings.sort((a,b)=>a-b);
      interaction.clicks.sort((a,b)=>a-b);interaction.scroll.sort((a,b)=>a-b);
      const singleClickP95Ms=Math.round(interaction.clicks[28]);
      const scrollFrameP95Ms=Math.round(interaction.scroll[42]);
      assert.ok(singleClickP95Ms<200,`Single-click response regressed to ${singleClickP95Ms}ms at ${width}px`);
      assert.ok(scrollFrameP95Ms<100,`Scroll response regressed to ${scrollFrameP95Ms}ms at ${width}px`);
      reports.push({viewport:`${width}x${height}`,cpuSlowdown:6,combinations:45,selectionImageRequests:0,threeClickBatchMedianMs:Math.round(timings[22]),threeClickBatchP95Ms:Math.round(timings[42]),singleClickP95Ms,scrollFrameP95Ms});
      await page.close();
    }
    fs.writeFileSync('.tmp/avatar-loading/performance.json',JSON.stringify(reports,null,2));
    console.log(JSON.stringify(reports,null,2));
    console.log('Avatar editor: cold load/retry, 45 combinations, offline selection, geometry, save, focus and reduced motion passed.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
