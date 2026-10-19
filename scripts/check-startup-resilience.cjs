// Production build + local API fixtures; no real account, API or external traffic.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'C:/Users/sevag/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { readFileSync, mkdirSync } = require('node:fs');
const { resolve } = require('node:path');

const sdk = readFileSync(resolve('front/public/vendor/telegram-web-app.js'), 'utf8');
const output = resolve('.tmp/startup-resilience');
mkdirSync(output, { recursive: true });

async function serve(build, port) {
  const child = spawn(process.execPath, ['scripts/serve-perf-fixture.mjs', build, String(port)], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  await new Promise((yes, no) => {
    const timer = setTimeout(() => no(new Error('Fixture startup timed out')), 10000);
    child.once('error', error => { clearTimeout(timer); no(error); });
    child.once('exit', code => { clearTimeout(timer); no(new Error(`Fixture exited: ${code}`)); });
    child.stdout.once('data', () => { clearTimeout(timer); yes(); });
  });
  return child;
}

async function check(browser, base, { name, blocked, baseline = false, telegram = false, mobile = false }) {
  const page = await browser.newPage({ viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 } });
  const errors = [], external = [], pending = [], authHeaders = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'skipped' })));
  if (telegram) {
    page.on('request', request => {
      if (new URL(request.url()).pathname === '/api/next-race') authHeaders.push(request.headers()['x-telegram-init-data']);
    });
  }
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== base) {
      external.push(url.hostname);
      if (blocked === 'all' || blocked === 'telegram' && url.hostname === 'telegram.org' || blocked === 'fonts' && url.hostname.startsWith('fonts.')) {
        return new Promise(done => pending.push(async () => { await route.abort().catch(() => {}); done(); }));
      }
      if (url.hostname === 'telegram.org') return route.fulfill({ contentType: 'text/javascript', body: sdk });
      return route.abort();
    }
    if (telegram && url.pathname === '/vendor/telegram-web-app.js') {
      // The module entry must not race a slower SDK, including after reload.
      await new Promise(done => setTimeout(done, 350));
    }
    return route.continue();
  });
  try {
    await page.goto(base + (telegram ? '/#tgWebAppData=startup-fixture&tgWebAppVersion=8.0&tgWebAppPlatform=tdesktop' : '/'), { waitUntil: 'commit' });
    const mounted = await page.locator('.weekend-board').waitFor({ state: 'visible', timeout: baseline ? 2500 : 6000 }).then(() => true, () => false);
    if (baseline) {
      assert.equal(mounted, false, `${name}: original build must reproduce blank startup`);
      assert.equal(await page.evaluate(() => document.querySelector('#root')?.childElementCount || 0), 0);
      assert(external.length > 0);
      console.log(`${name}: blank screen reproduced while external request remains pending`);
      return;
    }
    assert(mounted, `${name}: UI must render without waiting for external hosts`);
    await page.locator('.weekend-board-row').first().waitFor();
    if (telegram) {
      assert.equal(await page.evaluate(() => window.Telegram.WebApp.initData), 'startup-fixture');
      await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
      await page.locator('.weekend-board-row').first().waitFor();
      assert.equal(await page.evaluate(() => window.Telegram.WebApp.initData), 'startup-fixture', 'SDK must restore init data without the launch hash');
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.locator('.weekend-board-row').first().waitFor();
      assert.equal(await page.evaluate(() => window.Telegram.WebApp.initData), 'startup-fixture', 'SDK must restore init data on reload');
      assert(authHeaders.length >= 3);
      assert(authHeaders.every(header => header === 'startup-fixture'), 'first API reads must use Telegram auth');
    }
    await page.evaluate(() => document.fonts.ready);
    assert(await page.evaluate(() => document.fonts.check('600 16px Inter', 'Привет F1')));
    assert(!external.some(host => /^(telegram\.org|fonts\.googleapis\.com|fonts\.gstatic\.com)$/.test(host)), 'startup SDK/fonts must be same-origin');
    assert.deepEqual(errors, []);
    await page.screenshot({ path: resolve(output, `${name}.png`) });
    const timing = await page.evaluate(() => ({ firstContentfulPaint: performance.getEntriesByName('first-contentful-paint')[0]?.startTime, domContentLoaded: performance.getEntriesByType('navigation')[0]?.domContentLoadedEventEnd }));
    console.log(`${name}: PASS ${JSON.stringify(timing)}`);
  } finally {
    await Promise.all(pending.map(release => release()));
    await page.close();
  }
}

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const servers = [];
  try {
    if (process.argv.includes('--before')) {
      servers.push(await serve('.tmp/startup-before', 4181));
      for (const blocked of ['telegram', 'fonts']) await check(browser, 'http://127.0.0.1:4181', { name: `before-${blocked}`, blocked, baseline: true });
    }
    servers.push(await serve(process.argv[2] && !process.argv[2].startsWith('--') ? process.argv[2] : 'front/dist', 4182));
    for (const mobile of [false, true]) await check(browser, 'http://127.0.0.1:4182', { name: `after-${mobile ? 'mobile' : 'desktop'}`, blocked: 'all', mobile });
    await check(browser, 'http://127.0.0.1:4182', { name: 'telegram-auth-and-reload', blocked: 'all', telegram: true });
  } finally {
    await browser.close();
    for (const server of servers) server.kill();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
