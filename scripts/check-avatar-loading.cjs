// Exercise actual image loading, decoded transitions and delayed/out-of-order responses.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.PROFILE_UI_URL || 'http://127.0.0.1:5174';
require('node:child_process').execFileSync('.venv/Scripts/python.exe', ['scripts/render-avatar-fixtures.py']);
const avatar = {helmet:'scarlet',suit:'scarlet',background:'garage'};
const avatarOptions = {helmet:{scarlet:'Алый / полоса',cobalt:'Кобальт / двойная полоса',mint:'Жемчуг / мята'},suit:{scarlet:'Алый / графит',cobalt:'Индиго / лайм',mint:'Графит / мята'},background:{garage:'Ночной бокс',scarlet:'Красный сектор',cobalt:'Синий час',mint:'Полярное сияние',gold:'Золотой подиум'}};
const options = {frame:{classic:0,red:2,gold:3},color:{white:0,red:2,gold:3},background:{carbon:0,grid:2,champion:3}};
const fixture = {user_id:1,display_name:'Turbo Racer',is_owner:true,profile_guide_seen:true,supporter:true,tier:3,tier_name:'Полный газ',style:{frame:'classic',color:'white',background:'carbon'},avatar,avatar_options:avatarOptions,options,season:2026,seasons:[2026,2025],total_points:0,scored_rounds:0,best_prediction:null,predictions:[],records:[],favorites:{drivers:[],teams:[]}};
const preview = page => page.getByAltText('Предпросмотр выбранного гонщика');
async function waitPortrait(page, key) {
  await page.waitForFunction(key => {
    const image = document.querySelector('.avatar-editor-preview img[alt="Предпросмотр выбранного гонщика"]');
    const params = image && new URL(image.src).searchParams;
    return image?.complete && image.naturalWidth > 0 && ['helmet','suit','background'].map(k=>params.get(k)).join('-') === key;
  }, key);
}
async function geometry(page) {
  return page.locator('.avatar-editor').evaluate(dialog => [dialog,dialog.querySelector('header'),dialog.querySelector('.avatar-editor-preview'),dialog.querySelector('.avatar-editor-options'),dialog.querySelector('footer'),...dialog.querySelectorAll('.avatar-editor-options button')].map(el=>[el.offsetLeft,getComputedStyle(el).position==='sticky'?0:el.offsetTop,el.offsetWidth,el.offsetHeight]));
}
(async()=>{
  fs.mkdirSync('.tmp/avatar-loading',{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try {
    for(const [width,height] of [[390,1000],[1440,1000],[320,640],[844,390]]) {
      const page=await browser.newPage({viewport:{width,height}});
      const errors=[];page.on('pageerror',e=>errors.push(e.message));
      const gates=new Map();const failures=new Set();let hold=true;
      function gate(key) {if(!gates.has(key)){let release;const promise=new Promise(resolve=>{release=resolve});gates.set(key,{promise,release});}return gates.get(key);}
      await page.route('**/api/**',async route=>{
        const url=new URL(route.request().url());const path=url.pathname;
        if(path==='/api/profiles/avatar/v1.png') {
          const key=['helmet','suit','background'].map(k=>url.searchParams.get(k)).join('-');
          if(hold && key!=='scarlet-scarlet-garage') await gate(key).promise;
          if(failures.has(key)) return route.fulfill({status:503,body:'Unavailable'});
          return route.fulfill({contentType:'image/png',body:fs.readFileSync(`.tmp/profile-avatar-fixtures/${key}.png`)});
        }
        if(path.endsWith('/trophies')) return route.fulfill({json:{user_id:1,season:2026,families:[],earned:[],pending:[],badge:null}});
        if(path==='/api/auth/me') return route.fulfill({json:{id:1,email:'racer@example.test',email_verified:true,telegram_id:2099386,role:'user'}});
        if(path==='/api/profiles/supporters') return route.fulfill({json:{season:2026,current_user_id:1,entries:[]}});
        return route.fulfill({json:path.startsWith('/api/profiles/')?fixture:{}});
      });
      const prefetch=page.waitForRequest(request=>request.url().includes('avatar/v1.png?helmet=cobalt'));
      await page.goto(`${base}/profile`);
      await page.getByRole('heading',{name:'Turbo Racer'}).waitFor();
      await prefetch; // Alternative portraits start warming before the editor opens.
      await page.getByRole('button',{name:'Аватар и оформление',exact:true}).click();
      await waitPortrait(page,'scarlet-scarlet-garage');
      await page.waitForFunction(()=>document.querySelector('.avatar-editor').getAnimations().every(a=>a.playState==='finished'));
      const before=await geometry(page);
      await page.getByRole('button',{name:'Кобальт / двойная полоса'}).click();
      assert.ok((await preview(page).getAttribute('src')).includes('helmet=scarlet'));
      assert.equal(await page.locator('.avatar-editor-preview>.avatar-image').getAttribute('aria-busy'),'true');
      assert.deepEqual(await geometry(page),before,'Pending images keep every control in place');
      gate('cobalt-scarlet-garage').release();
      await waitPortrait(page,'cobalt-scarlet-garage');
      assert.deepEqual(await geometry(page),before,'Decoded images do not change the layout');
      await page.getByRole('button',{name:'Жемчуг / мята'}).click();
      await page.getByRole('button',{name:'Золотой подиум'}).click();
      gate('mint-scarlet-gold').release();
      await waitPortrait(page,'mint-scarlet-gold');
      const late=page.waitForResponse(response=>response.url().includes('helmet=mint&suit=scarlet&background=garage'));
      gate('mint-scarlet-garage').release();
      await late;
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      assert.ok((await preview(page).getAttribute('src')).includes('background=gold'),'A late response cannot replace the latest selection');
      assert.deepEqual(await geometry(page),before,'Rapid selections keep fixed geometry');
      failures.add('mint-mint-gold');
      await page.getByRole('button',{name:'Графит / мята'}).click();
      gate('mint-mint-gold').release();
      await page.getByRole('button',{name:'Образ не загрузился · Повторить'}).waitFor();
      assert.ok((await preview(page).getAttribute('src')).includes('suit=scarlet'),'A failed request keeps the last good portrait');
      failures.clear();
      await page.getByRole('button',{name:'Образ не загрузился · Повторить'}).click();
      await waitPortrait(page,'mint-mint-gold');
      assert.deepEqual(await geometry(page),before);
      hold=false;for(const value of gates.values())value.release();
      await page.waitForFunction(()=>[...document.querySelectorAll('.avatar-editor-options .avatar-image')].every(el=>el.getAttribute('aria-busy')==='false'));
      await page.waitForFunction(()=>[...document.querySelectorAll('.avatar-image img')].every(el=>el.getAnimations().every(a=>a.playState==='finished')));
      assert.ok(await page.locator('.avatar-editor-options button[aria-pressed="true"] .avatar-image').evaluateAll(elements=>elements.every(el=>el.querySelector('img:last-of-type').src.includes('helmet=mint&suit=mint&background=gold'))),'Retry refreshes the selected thumbnails too');
      await page.screenshot({path:`.tmp/avatar-loading/editor-${width}.png`});
      await page.keyboard.press('Escape');
      await page.getByRole('dialog',{name:'Аватар и оформление'}).waitFor({state:'detached'});
      assert.equal(await page.getByRole('button',{name:'Аватар и оформление',exact:true}).evaluate(el=>el===document.activeElement),true,'Closing restores keyboard focus');
      await page.emulateMedia({reducedMotion:'reduce'});
      await page.getByRole('button',{name:'Аватар и оформление',exact:true}).click();
      await waitPortrait(page,'scarlet-scarlet-garage');
      assert.equal(await page.locator('.avatar-editor').evaluate(el=>getComputedStyle(el).animationName),'none');
      await page.getByRole('button',{name:'Жемчуг / мята'}).click();
      await waitPortrait(page,'mint-scarlet-garage');
      assert.equal(await preview(page).evaluate(el=>getComputedStyle(el).animationName),'none');
      await page.keyboard.press('Escape');
      await page.getByRole('dialog').waitFor({state:'detached'});
      assert.deepEqual(errors,[]);
      await page.close();
    }
    console.log('Avatar loading: background prefetch, stable geometry, latest selection, retry, focus and reduced motion passed at 320/390/844/1440px.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
