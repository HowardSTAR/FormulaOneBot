// Optional browser smoke test: NODE_PATH must contain an installed playwright.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 844, height: 300 }, isMobile: true, hasTouch: true });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => { errors.push(error.message); console.error('Page error:', error.message); });
    page.on('console', message => { if (message.type() === 'error') console.error('Console:', message.text()); });
    await page.route('**/api/**', route => route.fulfill({ json: { ghost: null, entries: [], me: null } }));
    await page.goto(process.env.RACE_TEST_URL || 'http://127.0.0.1:4175/race-game/index.html');
    await page.locator('canvas').waitFor({ timeout: 10000 });
    const frame = page;
    const gas = frame.locator('#touch-throttle');
    const brake = frame.locator('#touch-brake');
    const gasBox = await gas.boundingBox();
    const brakeBox = await brake.boundingBox();
    assert.ok(gasBox.y + gasBox.height <= brakeBox.y, 'brake must be below throttle');
    assert.ok(brakeBox.y + brakeBox.height <= 300, 'pedals fit short landscape viewport');
    await frame.locator('#start-button').click();
    await page.waitForTimeout(3500);
    const stick = await frame.locator('#touch-joystick').boundingBox();
    await page.mouse.move(stick.x + stick.width / 2, stick.y + stick.height / 2);
    await page.mouse.down();
    await page.mouse.move(stick.x + stick.width * .8, stick.y + stick.height / 2);
    assert.ok(await frame.locator('#joystick-knob').evaluate(el => !el.style.transform.includes('translate(0px, 0px)')));
    await page.mouse.up();
    assert.equal(await frame.locator('#joystick-knob').evaluate(el => el.style.transform), 'translate(0px, 0px)');
    await page.screenshot({ path: path.resolve('artifacts/race-mobile-landscape.png') });
    await page.setViewportSize({ width: 390, height: 700 });
    await page.waitForTimeout(300);
    const canvas = await frame.locator('canvas').boundingBox();
    assert.equal(Math.round(canvas.width), 390);
    assert.equal(Math.round(canvas.height), 700);
    await page.screenshot({ path: path.resolve('artifacts/race-mobile-portrait.png') });
    assert.deepEqual(errors, []);
    console.log('Mobile layout, joystick capture/release, rotation and startup: passed');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
