// Uses the isolated design fixture; no production records are changed.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { mkdirSync } = require('node:fs');
const base = process.env.GAMES_UI_URL || 'http://127.0.0.1:5173';
const output = process.env.GAMES_UI_OUTPUT || '.tmp/game-light';
mkdirSync(output, { recursive: true });
async function aligned(page, selector) {
  const surface = page.locator('.game-play-surface');
  const source = page.locator(selector).filter({ visible: true }).first();
  const root = await surface.boundingBox(), lamp = await source.boundingBox();
  const light = await surface.evaluate(element => ({ x: parseFloat(element.style.getPropertyValue('--game-light-x')), y: parseFloat(element.style.getPropertyValue('--game-light-y')), radius: parseFloat(element.style.getPropertyValue('--game-light-radius')) }));
  assert.ok(Math.abs(light.x - (lamp.x + lamp.width / 2 - root.x)) < 2, JSON.stringify({ light, lamp, root }));
  assert.ok(Math.abs(light.y - (lamp.y + lamp.height / 2 - root.y)) < 2, JSON.stringify({ light, lamp, root }));
  assert.ok(Number.isFinite(light.radius) && light.radius > 0);
  return light;
}
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  let scenarios = 0;
  try {
    for (const theme of ['light', 'dark']) for (const width of [390, 1440]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      await page.goto(`${base}/tests/home-design-preview.html?page=reflex-grid-game&auth=guest&theme=${theme}`);
      await page.locator('.reflex-tile.active').waitFor();
      await aligned(page, '.reflex-tile.active');
      await page.clock.install();
      for (const corner of [0, 8]) {
        const current = await page.locator('.reflex-tile.active').evaluate(e => Array.from(e.parentElement.children).indexOf(e));
        if (current !== corner) {
          await page.evaluate(index => { Math.random = () => (index + .5) / 9; }, corner);
          await page.locator('.reflex-tile.active').click();
        }
        await aligned(page, '.reflex-tile.active');
        await page.locator('.game-play-surface').screenshot({ path: `${output}/reflex-${theme}-${width}-corner-${corner}.png` });
      }
      // A resized game must preserve source-relative light even while scrolling is locked.
      await page.setViewportSize({ width: width === 390 ? 320 : 900, height: 1000 });
      await page.locator('.reflex-grid').boundingBox();
      await page.waitForTimeout(50);
      await page.clock.runFor(64);
      await aligned(page, '.reflex-tile.active');
      assert.equal(await page.evaluate(() => document.body.style.position), 'fixed');
      assert.deepEqual(errors, []);
      await page.close(); scenarios++;

      const reaction = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
      await reaction.goto(`${base}/tests/home-design-preview.html?page=reaction-game&auth=guest&theme=${theme}`);
      await reaction.locator('.reaction-play-surface').waitFor();
      await aligned(reaction, '.reaction-button, .reaction-desktop-start');
      await reaction.locator('.game-play-surface').screenshot({ path: `${output}/reaction-${theme}-${width}.png` });
      await reaction.setViewportSize({ width: width === 390 ? 900 : 390, height: 1000 });
      await reaction.waitForTimeout(80);
      await aligned(reaction, '.reaction-button, .reaction-desktop-start');
      await reaction.emulateMedia({ contrast: 'more' });
      assert.equal(await reaction.locator('.game-play-surface').evaluate(e => getComputedStyle(e, '::before').display), 'none');
      await reaction.close(); scenarios++;
    }
    console.log(`Passed ${scenarios} source-position, movement, resize and contrast scenarios.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
