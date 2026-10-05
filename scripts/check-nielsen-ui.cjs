// Run Vite against tests/ux_preview_server.py. Additional fixtures stay in RAM;
// write requests are intercepted, so this audit never sends messages or changes accounts.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const base = process.env.NIELSEN_UI_URL || 'http://127.0.0.1:5174';
const paths = [...readFileSync('front/src/router.tsx','utf8').matchAll(/path:\s*["']([^"']+)["']/g)].map(match => match[1]);
const query = {'/driver-details':'?driverId=alonso&season=2026','/constructor-details':'?constructorId=ferrari&season=2026','/team-principal':'?constructorId=ferrari&season=2026','/race-details':'?season=2026&round=17'};
const routes = [...new Set(paths.map(path => path === '*' ? '/missing-page' : path.replace(':token','A'.repeat(32)) + (query[path] || '')))];
routes.push(...['leaderboard','history','leagues'].map(tab=>`/predictions?tab=${tab}`), ...['recovery','notifications','recap-news','users','overview','games','audit','tools'].map(section=>`/admin?section=${section}`));
const fixtures = {
  '/api/engagement/weekly': {track_id:'emerald-loop-v2',name:'Трасса недели',start:'2026-10-05T00:00:00Z',end:'2026-10-12T00:00:00Z',entries:[]},
  '/api/engagement/mine': {referrals:{arrived:0,activated:0,returned:0},badges:[],shares:[]},
  '/api/reaction-leaderboard': {entries:[],me:null},
  '/api/race-game-leaderboard': {entries:[],me:null,ghost:null,track_id:'emerald-loop-v2'},
  '/api/admin/users': {items:[],page:1,pages:1,total:0,page_size:20,sort_by:'created_at',sort_order:'desc'},
  '/api/admin/game-records': {games:[],total_records:0,total_players:0},
  '/api/admin/tools/notifications': {items:[]},
  '/api/admin/tools/recap-news': {sources:[],items:[]},
  '/api/admin/prediction-analytics': {events:[],snapshots:[],warning:null},
  '/api/predictions/leagues': {leagues:[]},
};
(async()=>{
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const failures = [];
  try {
    for (const width of [320,390,1440]) {
      const context = await browser.newContext({viewport:{width,height:900}});
      await context.addInitScript(()=>localStorage.setItem('turbotears-onboarding-v2',JSON.stringify({status:'completed'})));
      await context.route('**/api/**', async route=>{
        const path = new URL(route.request().url()).pathname;
        if (route.request().method() !== 'GET') return route.fulfill({json:{ok:true}});
        if (Object.hasOwn(fixtures,path)) return route.fulfill({json:fixtures[path]});
        return route.continue();
      });
      const page = await context.newPage();
      let errors = [];
      page.on('pageerror',e=>errors.push(e.message));
      for (const path of routes) {
        errors = [];
        await page.goto(base+path);
        await page.waitForTimeout(650);
        const state = await page.evaluate(()=>{
          const visible = el=>el.getBoundingClientRect().width>0 && el.getBoundingClientRect().height>0 && getComputedStyle(el).visibility!=='hidden';
          return {overflow:document.documentElement.scrollWidth>innerWidth+1,
            native:[...document.querySelectorAll('select')].filter(visible).length,
            unlabelled:[...document.querySelectorAll('button')].filter(visible).filter(el=>!el.getAttribute('aria-label')&&!el.getAttribute('aria-labelledby')&&!el.textContent.trim()&&!el.querySelector('img[alt]')).map(el=>el.className),
            text:document.body.innerText.slice(0,350)};
        });
        if (state.overflow || state.native || state.unlabelled.length || errors.length) {
          failures.push({width,path,...state,errors:[...errors]});
          await page.screenshot({path:`artifacts/usability-nielsen-${width}-${path.split('?')[0].replace(/\W/g,'_')}.png`,fullPage:true});
        }
        console.log(JSON.stringify({width,path,overflow:state.overflow,unlabelled:state.unlabelled,errors}));
      }
      // Guests must retain their destination after the sign-in redirect.
      await context.route('**/api/auth/me',route=>route.fulfill({status:401,json:{detail:'Guest'}}));
      for (const path of ['/favorites','/settings','/notifications','/voting']) {
        await page.goto(base+path);
        await page.waitForURL('**/account?**');
        assert.equal(new URL(page.url()).searchParams.get('returnPath'),path);
      }
      await context.close();
    }
    assert.deepEqual(failures,[]);
    console.log(`Nielsen route audit: ${routes.length} routes/states × 3 widths and guest redirects passed`);
  } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
