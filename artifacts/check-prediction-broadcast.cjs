// Local UI verification with fully mocked API responses; never contacts production.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');

(async () => {
  const root = path.resolve(__dirname, '../front/dist');
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, 'http://127.0.0.1').pathname;
    const file = path.resolve(root, '.' + (path.extname(pathname) ? pathname : '/index.html'));
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) {response.writeHead(404).end(); return;}
    const types = {'.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.png': 'image/png', '.svg': 'image/svg+xml'};
    response.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream');
    fs.createReadStream(file).pipe(response);
  });
  await new Promise(resolve => server.listen(4180, '127.0.0.1', resolve));
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const output = path.resolve(__dirname, '../.tmp/prediction-broadcast');
  fs.mkdirSync(output, { recursive: true });
  try {
    for (const width of [1280, 390]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } });
      const page = await context.newPage();
      const errors = [];
      let posts = 0;
      let sent = false;
      let changed = false;
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', '{"status":"skipped"}'));
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.hostname !== '127.0.0.1') return route.abort();
        if (!url.pathname.startsWith('/api/')) return route.continue();
        let response = {};
        let status = 200;
        const user = { id: 1, email: 'admin@example.test', role: 'superadmin', telegram_id: 101, display_name: 'Admin', email_verified: true };
        if (url.pathname === '/api/auth/me' || url.pathname === '/api/admin/me') response = user;
        if (url.pathname === '/api/admin/users') response = {items: [], total: 0, page: 1, page_size: 20};
        if (url.pathname === '/api/admin/audit-log' || url.pathname === '/api/admin/tools/prediction-recovery') response = [];
        if (url.pathname === '/api/admin/tools/control') response = {as_of: Date.now()/1000, counts: {}, recoveries: {}, incomplete: [], push_configured: true};
        if (url.pathname === '/api/admin/tools/prediction-recovery/rounds') response = {rounds: [
          {season: 2026, round: 16, event_name: 'Italian Grand Prix', missing: ['first_retirement_driver'], current: {}, first_retirement_drivers: []},
          {season: 2026, round: 17, event_name: 'Azerbaijan Grand Prix', missing: [], current: {}, first_retirement_drivers: []},
        ]};
        if (url.pathname === '/api/race-results') response = {season: 2026, round: Number(url.searchParams.get('round')), results: []};
        if (url.pathname === '/api/admin/tools/prediction-results/preview') {
          const round = Number(url.searchParams.get('round'));
          response = {season: 2026, round, event_name: round === 16 ? 'Italian Grand Prix' : 'Azerbaijan Grand Prix',
            fingerprint: (changed ? 'b' : 'a').repeat(64), body: '🏆 ' + (round === 16 ? 'Предварительные итоги прогнозов этапа' : 'Итоги прогнозов этапа') + '\n\n🏁 Grand Prix · 2026, этап ' + round + '\n\n🥇 Racer — 20/37\n🥈 Fan — 18/37\n🥉 Driver — 12/37',
            provisional: round === 16, participants: 6, recipients: {telegram: 45, web: 32}, already_sent: sent};
        }
        if (url.pathname === '/api/admin/tools/prediction-results/send') {
          const payload = route.request().postDataJSON();
          assert.equal(payload.round, 16);
          assert.equal(payload.confirmation, 'ОТПРАВИТЬ');
          posts++;
          if (!changed) {status = 409; response = {detail: 'Итоги изменились. Обновите предпросмотр перед отправкой.'}; changed = true;}
          else {assert.equal(payload.fingerprint, 'b'.repeat(64)); response = {recipients: {telegram: 45, web: 32}, already_sent: false}; sent = true;}
        }
        await route.fulfill({status, contentType: 'application/json', body: JSON.stringify(response)});
      });
      await page.goto('http://127.0.0.1:4180/admin?section=recovery');
      try {await page.locator('.recovery-target select').nth(1).selectOption('16');}
      catch (error) {console.error({errors, body: (await page.locator('body').innerText()).slice(0, 2000)}); throw error;}
      const panel = page.getByRole('region', {name: 'Рассылка итогов прогнозов'});
      await panel.getByText('Получатели: Telegram — 45, веб — 32.').waitFor();
      assert.match(await panel.innerText(), /предварительные итоги/);
      const send = panel.getByRole('button', {name: 'Разослать итоги в Telegram и веб'});
      assert.equal(await send.isDisabled(), true);
      await panel.getByRole('textbox').fill('ОТПРАВИТЬ');
      assert.equal(await send.isEnabled(), true);
      await panel.scrollIntoViewIfNeeded();
      await page.screenshot({path: path.join(output, `preview-${width}.png`), fullPage: true});
      await send.click();
      await panel.getByRole('alert').filter({hasText: 'Итоги изменились'}).waitFor();
      const refreshed = page.waitForResponse(response => response.url().includes('/prediction-results/preview'));
      await panel.getByRole('button', {name: 'Обновить предпросмотр рассылки'}).click();
      await refreshed;
      await panel.getByRole('textbox').fill('ОТПРАВИТЬ');
      await send.click();
      await panel.getByRole('status').filter({hasText: 'Рассылка создана.'}).waitFor();
      assert.equal(await send.count(), 0);
      await panel.getByRole('button', {name: 'Обновить предпросмотр рассылки'}).click();
      await panel.getByText('Эти итоги уже отправлены вручную.', {exact: false}).waitFor();
      assert.equal(await send.count(), 0);
      assert.equal(posts, 2);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      assert.deepEqual(errors, []);
      console.log(JSON.stringify({width, confirmation: true, stalePreview: true, sentBothChannels: true, deduplicated: true, overflow: false}));
      await context.close();
    }
  } finally {await browser.close(); await new Promise(resolve => server.close(resolve));}
})().catch(error => {console.error(error); process.exitCode = 1;});
