// Exercise the visible continuity at both carousel edges, with real browser animation.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.HOME_UI_URL || 'http://127.0.0.1:5173';
async function selected(page, index) {
  await page.waitForFunction(index => {
    const dots = [...document.querySelectorAll('.home-spotlight-pages button')];
    const v = document.querySelector('.home-spotlight-viewport');
    return dots[index]?.hasAttribute('aria-current') && Math.abs(v.scrollLeft - (index + 1) * v.getBoundingClientRect().width) < 2;
  }, index);
}
async function sampleMove(page, key) {
  await page.evaluate(() => { const v = document.querySelector('.home-spotlight-viewport'); window.carouselFrames = []; window.carouselSampling = true;
    const sample = () => { if (!window.carouselSampling) return; window.carouselFrames.push(v.scrollLeft / v.getBoundingClientRect().width); requestAnimationFrame(sample); }; sample(); });
  await page.locator('.home-spotlight-viewport').press(key);
}
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    for (const [width, auth, count] of [[390, 'member', 4], [1024, 'member', 4], [320, 'guest', 2]]) {
      const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'no-preference', hasTouch: true });
      await page.route('https://telegram.org/**', r => r.abort());
      await page.goto(`${base}/tests/home-design-preview.html?theme=dark&auth=${auth}&spotlight=${count === 4 ? 'team' : 'driver-1'}&demoVotes=1`);
      await page.locator('.home-standing-table').waitFor(); await selected(page, count - 1);
      assert.equal(await page.getByRole('button', { name: /^(Предыдущий|Следующий) слайд$/ }).count(), 0);
      const height = await page.locator('.home-banner-stage').evaluate(e => e.getBoundingClientRect().height);
      await sampleMove(page, 'ArrowRight'); await selected(page, 0);
      const forward = await page.evaluate(() => { window.carouselSampling = false; return window.carouselFrames; });
      assert.ok(forward.some(x => x > count + .05 && x < count + .95), JSON.stringify({ width, forward }));
      assert.ok(forward.every(x => x >= count - .02 || Math.abs(x - 1) < .02), 'Wrap must not travel backwards through intermediate cards');
      await sampleMove(page, 'ArrowLeft'); await selected(page, count - 1);
      const backward = await page.evaluate(() => { window.carouselSampling = false; return window.carouselFrames; });
      assert.ok(backward.some(x => x > .05 && x < .95), JSON.stringify({ width, backward }));
      assert.ok(backward.every(x => x <= 1.02 || Math.abs(x - count) < .02), 'Reverse wrap must stay adjacent');
      assert.ok(Math.abs(await page.locator('.home-banner-stage').evaluate(e => e.getBoundingClientRect().height) - height) < 1);
      const duplicateIds = await page.evaluate(() => { const ids = [...document.querySelectorAll('[id]')].map(e => e.id); return ids.filter((id, i) => ids.indexOf(id) !== i); });
      assert.deepEqual(duplicateIds, []);
      assert.equal(await page.locator('.home-spotlight-buffer:not([inert])').count(), 0);
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.locator('.home-spotlight-viewport').press('ArrowRight'); await selected(page, 0);
      await page.close();
    }
    console.log('3 circular motion scenarios passed: forward/reverse adjacent transitions, fractional widths, guest/member, stable height, inert snapshots, unique IDs and reduced motion.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
