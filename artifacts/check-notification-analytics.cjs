// Local browser verification; API traffic is mocked and external requests are blocked.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');

(async () => {
  const root = path.resolve(__dirname, '../front/dist');
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, 'http://127.0.0.1').pathname;
    const file = path.resolve(root, '.'+(path.extname(pathname) ? pathname : '/index.html'));
    if (!file.startsWith(root+path.sep) || !fs.existsSync(file)) {response.writeHead(404).end(); return;}
    response.setHeader('Content-Type', {'.js':'text/javascript', '.css':'text/css', '.html':'text/html', '.png':'image/png', '.svg':'image/svg+xml'}[path.extname(file)] || 'application/octet-stream');
    fs.createReadStream(file).pipe(response);
  });
  await new Promise(resolve => server.listen(4181, '127.0.0.1', resolve));
  const browser = await chromium.launch({channel:'msedge', headless:true});
  const output = path.resolve(__dirname, '../.tmp/notification-analytics');
  fs.mkdirSync(output, {recursive:true});
  try {
    for (const width of [1280, 390]) {
      const context = await browser.newContext({viewport:{width, height:1000}, acceptDownloads:true});
      const page = await context.newPage();
      const errors = [], entries = [], periods = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', '{"status":"skipped"}'));
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.hostname !== '127.0.0.1') return route.abort();
        if (!url.pathname.startsWith('/api/')) return route.continue();
        let response = {};
        const user = {id:1, email:'admin@example.test', role:'superadmin', telegram_id:101, display_name:'Admin', email_verified:true};
        if (['/api/auth/me', '/api/admin/me'].includes(url.pathname)) response = user;
        if (url.pathname === '/api/admin/users') response = {items:[], total:0, page:1, page_size:20};
        if (url.pathname === '/api/admin/audit-log') response = [];
        if (url.pathname === '/api/admin/tools/insights') response = {accounts:{total:6,new_users:0}, visitors:{unique_browsers:12,returning_browsers:2}, inbox:{total:6,read_count:3}, queue:{pending:0,exhausted:0}, reach:{members:6,push_users:2}};
        if (url.pathname === '/api/admin/tools/product-analytics') {
          periods.push(url.searchParams.get('days'));
          response = {funnel:{opened:6,started:4,saved:3}, interaction_first:null, screens:[], actions:[], retention:[], errors:[], quality:[], notification_buttons:{first_tracked:1791150000, summary:{interactions:17,unique_users:9,callbacks:7,arrivals:10}, items:[
            {campaign:'prediction:results:2026:16',caption:'Итоги прогнозов · 2026, этап 16',channel:'telegram',button:'leaderboard',label:'Таблица прогнозов',sent_at:1791150000,clicks:8,unique_users:6,metric:'arrival'},
            {campaign:'prediction:results:2026:16',caption:'Итоги прогнозов · 2026, этап 16',channel:'telegram',button:'review',label:'Мой разбор',sent_at:1791150000,clicks:7,unique_users:5,metric:'callback'},
            {campaign:'prediction:results:2026:16',caption:'Итоги прогнозов · 2026, этап 16',channel:'telegram',button:'leagues',label:'Мои лиги',sent_at:1791150000,clicks:0,unique_users:0,metric:'callback'},
            {campaign:'weekly-race:2026-10-05',caption:'Заезд недели · 2026-10-05',channel:'web',button:'community',label:'С друзьями · итоги и новый заезд',sent_at:1791150000,clicks:2,unique_users:2,metric:'arrival'},
          ]}};
        }
        if (url.pathname === '/api/engagement/weekly') response = {track_id:'harbor',name:'Harbor Sprint',start:'2026-10-05',end:'2026-10-12',entries:[]};
        if (url.pathname === '/api/engagement/mine') response = {badges:[],shares:[],referrals:{arrived:0,activated:0,returned:0}};
        if (url.pathname === '/api/analytics/notification-entry') {entries.push(route.request().postDataJSON()); response = {ok:true};}
        await route.fulfill({contentType:'application/json', body:JSON.stringify(response)});
      });
      await page.goto('http://127.0.0.1:4181/admin?section=overview');
      await page.getByRole('button', {name:'Кнопки рассылок', exact:true}).click();
      const panel = page.locator('.product-analytics');
      await panel.locator('tbody tr').filter({hasText:'С друзьями · итоги и новый заезд'}).waitFor();
      assert.equal(await panel.locator('tbody tr').count(), 4);
      assert.equal(await panel.locator('tbody tr').filter({hasText:'Мои лиги'}).locator('td').nth(1).innerText(), '0');
      assert.match(await panel.innerText(), /Нажатие без загрузки страницы не видно/);
      await panel.locator('select').selectOption('7');
      await panel.locator('tbody tr').filter({hasText:'С друзьями · итоги и новый заезд'}).waitFor();
      const downloaded = page.waitForEvent('download');
      await panel.getByRole('button', {name:'Скачать CSV'}).click();
      const download = await downloaded;
      const csv = fs.readFileSync(await download.path(), 'utf8');
      assert.match(csv, /Кнопки рассылок/);
      assert.match(csv, /Мой разбор · telegram · нажатия";"7"/);
      assert.equal(download.suggestedFilename(), 'analytics-7d.csv');
      assert.ok(periods.includes('7'));
      await panel.scrollIntoViewIfNeeded();
      await page.screenshot({path:path.join(output, `dashboard-${width}.png`), fullPage:true});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      const target = `http://127.0.0.1:4181/community?weekly=previous&week=2026-09-28&nb=${'a'.repeat(32)}#previous-week-results`;
      await page.goto(target);
      await page.waitForURL(url => !url.searchParams.has('nb'));
      assert.equal(entries.length, 1);
      assert.equal(entries[0].path, '/community');
      assert.equal(entries[0].token, 'a'.repeat(32));
      assert.equal(new URL(page.url()).searchParams.get('week'), '2026-09-28');
      assert.equal(new URL(page.url()).searchParams.get('weekly'), 'previous');
      assert.equal(new URL(page.url()).hash, '#previous-week-results');
      await page.reload();
      await page.getByRole('heading', {name:'С друзьями', exact:true}).waitFor();
      assert.equal(entries.length, 1);
      assert.deepEqual(errors, []);
      console.log(JSON.stringify({width, report:true, period:true, csv:true, arrival:true, queryPreserved:true, reloadDedup:true, overflow:false}));
      await context.close();
    }
  } finally {await browser.close(); await new Promise(resolve => server.close(resolve));}
})().catch(error => {console.error(error); process.exitCode = 1;});
