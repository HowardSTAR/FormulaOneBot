// Exercise the same Vite-only demo the user sees, without replacing its API fixture.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const tracks = require('../app/race_tracks.json');
const base = process.env.COMMUNITY_UI_URL || 'http://127.0.0.1:5178';
const demo = `${base}/tests/home-design-preview.html?page=community`;
(async () => {
  const browser = await chromium.launch({ channel:process.env.PLAYWRIGHT_CHANNEL || 'chrome', headless:true });
  try {
    for (const theme of ['light','dark']) for (const [index,track] of tracks.entries()) {
      const width=index%2 ? 390 : 1440, auth=index<2 ? 'guest' : 'member';
      const context=await browser.newContext({viewport:{width,height:1000},colorScheme:theme});
      const page=await context.newPage(), errors=[], backend=[];
      page.on('pageerror',e=>errors.push(e.message));
      page.on('request',request=>{if(new URL(request.url()).pathname.startsWith('/api/'))backend.push(request.url());});
      await page.goto(`${demo}&theme=${theme}&auth=${auth}&track=${track.id}`);
      await page.getByRole('heading',{name:'Сообщество',exact:true}).waitFor();
      const map=page.getByRole('img',{name:`Схема трассы ${track.name}`,exact:true});await map.waitFor();
      assert.deepEqual(await page.evaluate(async()=>{const week=await(await fetch('/api/engagement/weekly')).json();return [week.track_id,week.name];}),[track.id,track.name]);
      const source=await map.locator('.community-track-scene').getAttribute('href');
      assert.ok(source.includes(track.id));
      assert.ok(await page.evaluate(async source=>{const image=new Image();image.src=source;await image.decode();return image.naturalWidth>0&&image.naturalHeight>0;},source));
      const box=await map.boundingBox();assert.ok(box.width>100&&box.height>100);
      const mask=await map.evaluate(element=>getComputedStyle(element).maskImage);
      assert.ok(mask.includes('90deg')&&(mask.match(/linear-gradient/g)||[]).length===2,`Both horizontal and vertical edge masks are present: ${mask}`);
      assert.equal(await page.locator('.community-track-unavailable').count(),0);
      assert.equal(await page.getByRole('link',{name:'Проехать три круга',exact:true}).getAttribute('href'),`/race-game?track=${track.id}&weekly=1`);
      const car=map.locator('.community-demo-car'), initial=await car.getAttribute('transform');
      await page.waitForTimeout(150);assert.notEqual(await car.getAttribute('transform'),initial);
      await page.getByRole('button',{name:'Пауза демонстрации трассы',exact:true}).click();
      if(auth==='member')assert.equal(await page.getByRole('status').filter({hasText:'Загружаем ваши лиги…'}).count(),0);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      await page.evaluate(()=>window.scrollTo(0,0));
      await page.screenshot({path:`/tmp/community-preview-${theme}-${track.id}.png`,fullPage:true});
      if(index===0)await page.locator('.community-spotlight').screenshot({path:`/tmp/community-fade-${theme}.png`});
      assert.deepEqual(errors,[]);assert.deepEqual(backend,[]);
      console.log(`Community demo: ${theme}, ${width}px, ${track.id} passed`);await context.close();
    }
    const context=await browser.newContext({viewport:{width:1440,height:1000}});
    const broken=await context.newPage();
    await broken.route('**/*.webp*',route=>route.request().resourceType()==='image'&&route.request().url().includes('canyon-switchback-v1')?route.abort():route.continue());
    await broken.goto(`${demo}&track=canyon-switchback-v1&theme=dark`);
    await broken.locator('.community-track-preview--outline').waitFor();
    const outline=broken.getByRole('img',{name:'Схема трассы Canyon Switchback',exact:true});
    assert.ok(Number(await outline.locator('.community-track-road').getAttribute('stroke-width'))>3);
    assert.equal(await broken.locator('.community-track-unavailable').count(),0);
    await broken.screenshot({path:'/tmp/community-preview-image-fallback.png',fullPage:true});
    console.log('Community demo: image failure preserves the selected track geometry');
    const unknown=await context.newPage();
    await unknown.route('**/api/**',route=>{
      const path=new URL(route.request().url()).pathname;
      return route.fulfill(path==='/api/auth/me'?{status:401,json:{detail:'Guest'}}:{json:path==='/api/engagement/weekly'?{track_id:'unknown-track',name:'Новая трасса',start:'2026-10-26',end:'2026-11-02',entries:[]}:{status:'none',entries:[],items:[],unread:0}});
    });
    await unknown.goto(`${base}/community`);
    await unknown.getByRole('status').filter({hasText:'Схема этой трассы пока недоступна.'}).waitFor();
    assert.equal(await unknown.locator('.community-track-scene').count(),0);
    assert.equal(await unknown.getByRole('link',{name:'Проехать три круга',exact:true}).getAttribute('href'),'/race-game?track=unknown-track&weekly=1');
    console.log('Community: unknown ID has an explicit state, never another track');
    const rollover=await context.newPage();
    await rollover.clock.install({time:new Date('2026-10-28T12:00:00Z')});
    let nextWeek=false;
    await rollover.route('**/api/**',route=>{
      const path=new URL(route.request().url()).pathname;
      const track=nextWeek?tracks[3]:tracks[0];
      return route.fulfill(path==='/api/auth/me'?{status:401,json:{detail:'Guest'}}:{json:path==='/api/engagement/weekly'?{track_id:track.id,name:track.name,start:nextWeek?'2026-11-02T00:00:00Z':'2026-10-26T00:00:00Z',end:nextWeek?'2026-11-09T00:00:00Z':'2026-11-02T00:00:00Z',entries:[]}:{status:'none',entries:[],items:[],unread:0}});
    });
    await rollover.goto(`${base}/community`);
    await rollover.getByRole('img',{name:`Схема трассы ${tracks[0].name}`,exact:true}).waitFor();
    nextWeek=true;await rollover.clock.fastForward(5*24*60*60*1000);
    const newMap=rollover.getByRole('img',{name:`Схема трассы ${tracks[3].name}`,exact:true});await newMap.waitFor();
    assert.ok((await newMap.locator('.community-track-scene').getAttribute('href')).includes(tracks[3].id));
    assert.equal(await newMap.locator('.community-track-road').getAttribute('points'),[...tracks[3].centerLine,tracks[3].centerLine[0]].map(p=>p.join(',')).join(' '));
    assert.equal(await rollover.getByRole('link',{name:'Проехать три круга',exact:true}).getAttribute('href'),`/race-game?track=${tracks[3].id}&weekly=1`);
    assert.equal(await rollover.getByRole('img',{name:`Схема трассы ${tracks[0].name}`,exact:true}).count(),0);
    console.log('Community: week rollover updates scenery, driving line and game link together');
    await context.close();
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
