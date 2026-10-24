// Read-only browser checks for the home carousel and four in-content sections.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const sectionNav = page => page.viewportSize().width >= 900 ? page.getByRole('navigation', { name: 'Главное меню', exact: true }) : page.getByRole('navigation', { name: 'Разделы главной', exact: true });
const base = process.env.HOME_UI_URL || 'http://127.0.0.1:5173';
async function fixture(browser, width, theme, extra = '') {
  const context = await browser.newContext({ viewport: { width, height: 1000 }, hasTouch: true, timezoneId: 'Europe/Moscow', reducedMotion: 'reduce' });
  const page = await context.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.clock.install({ time: new Date('2026-10-24T07:17:00Z') });
  await page.route('https://telegram.org/**', route => route.abort());
  await page.route('https://media.formula1.com/**', route => route.abort());
  await page.goto(`${base}/tests/home-design-preview.html?theme=${theme}${extra}`);
  await page.locator('.home-spotlight-pages').waitFor({ state: 'attached' });
  await page.locator('.home-standing-table').waitFor();
  await page.waitForFunction(() => !document.querySelector('.home-favorite-card')?.textContent.includes('Загружаем'));
  return { page, context, errors };
}
async function check(page) {
  const evidence = await page.evaluate(() => {
    const root = document.querySelector('.home-screen'), issues = [], contrast = [];
    const rgb = value => (value.match(/[\d.]+/g) || []).map(Number);
    const lum = values => values.slice(0, 3).map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while(walker.nextNode()) {
      const node = walker.currentNode, element = node.parentElement;
      if (!node.textContent.trim() || element.closest('[inert],[aria-hidden="true"],.home-sr-only') || !element.checkVisibility()) continue;
      const r = element.getBoundingClientRect();
      if (r.width && (r.left < -1 || r.right > innerWidth + 1)) issues.push(node.textContent);
      const style = getComputedStyle(element); let background = null;
      for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) { const value = rgb(getComputedStyle(ancestor).backgroundColor); if (value.length === 3 || value[3] === 1) { background = value; break; } }
      if (background) { const a = lum(rgb(style.color)), b = lum(background), ratio = (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
        const minimum = parseFloat(style.fontSize) >= 24 || (parseFloat(style.fontSize) >= 18.66 && Number(style.fontWeight) >= 700) ? 3 : 4.5;
        if (ratio < minimum) contrast.push({ text: node.textContent, ratio }); }
    }
    const viewport = document.querySelector('.home-spotlight-viewport');
    const pageIndex = [...document.querySelectorAll('.home-spotlight-pages button')].findIndex(el => el.hasAttribute('aria-current'));
    return { overflow: document.documentElement.scrollWidth > innerWidth, issues, contrast, season: root.dataset.section === 'season', alignment: root.dataset.section === 'season' && viewport ? Math.abs(viewport.scrollLeft - pageIndex * viewport.getBoundingClientRect().width) : 0, sections: document.querySelectorAll('.home-sections a').length,
      inlineNavigation: document.querySelector('.home-sections').checkVisibility(), desktop: innerWidth >= 900, overview: innerWidth >= 1200, visibleSlides: document.querySelectorAll('.home-banner-panel[data-active] .home-spotlight-slide:not([inert])').length, slides: document.querySelectorAll('.home-spotlight-slide').length, dots: document.querySelectorAll('.home-spotlight-pages button').length, guest: Boolean(document.querySelector('.home-personalize')) };
  });
  assert.equal(evidence.overflow, false, JSON.stringify(evidence));
  assert.deepEqual(evidence.issues, []);
  assert.deepEqual(evidence.contrast, []);
  assert.ok(evidence.alignment <= 2, JSON.stringify(evidence));
  assert.equal(evidence.sections, 4);
  assert.equal(evidence.visibleSlides, evidence.season ? evidence.overview ? evidence.slides : 1 : 0);
  assert.equal(evidence.slides, evidence.guest ? 2 : 4);
  assert.equal(evidence.dots, evidence.slides);
  assert.equal(evidence.inlineNavigation, !evidence.desktop);
}
async function selected(page, index) {
  await page.waitForFunction(index => [...document.querySelectorAll('.home-spotlight-pages button')].findIndex(el => el.hasAttribute('aria-current')) === index, index);
  await page.waitForFunction(index => { const v = document.querySelector('.home-spotlight-viewport'); return Math.abs(v.scrollLeft - index * v.getBoundingClientRect().width) < 2; }, index);
}
async function swipe(page, from, to) {
  const session = await page.context().newCDPSession(page);
  const box = await page.locator('.home-spotlight-viewport').boundingBox();
  const y = Math.min(box.y + 100, 750);
  await session.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: from, y }] });
  for (let step = 1; step <= 8; step++) {
    await session.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: from + (to - from) * step / 8, y }] });
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  await session.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await session.detach();
}
(async () => {
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true });
  let checks = 0;
  try {
    for (const theme of ['light', 'dark']) for (const width of [320, 390, 820, 1024]) {
      const { page, context, errors } = await fixture(browser, width, theme, '&auth=member');
      await selected(page, 0); await check(page);
      assert.equal(await page.locator('.mobile-primary-nav').count(), 0);
      for (let index = 1; index <= 4; index++) {
        await page.getByRole('button', { name: 'Следующий слайд', exact: true }).click();
        await selected(page, index % 4); await check(page);
        assert.equal(await page.locator('.home-race-cue, .home-spotlight-preferences').count(), 0);
      }
      await page.getByRole('button', { name: 'Предыдущий слайд', exact: true }).click();
      await selected(page, 3);
      await page.locator('.home-spotlight-viewport').focus(); await page.keyboard.press('ArrowRight'); await selected(page, 0);
      await page.keyboard.press('ArrowLeft'); await selected(page, 3);
      await page.getByRole('button', { name: /2 из 4:/ }).click(); await selected(page, 1);
      const pilot = page.locator('.home-spotlight-slide:not([inert])');
      assert.equal(await pilot.locator('h2').innerText(), 'Оскар Пиастри');
      assert.match(await pilot.getByRole('link').getAttribute('href'), /code=PIA.*season=2026/);
      assert.equal(await pilot.locator('.home-spotlight-monogram').isVisible(), true);
      for (const [label, heading] of [['Игры', 'Между гонками'], ['Справка и отзывы', 'Справка и отзывы'], ['Подписка', 'Что даёт подписка']]) {
        await sectionNav(page).getByRole('link', { name: label, exact: true }).click();
        await page.getByRole('heading', { name: heading, exact: true }).waitFor();
        assert.equal(await page.locator('.home-spotlight').isVisible(), false);
        assert.equal(await page.locator('.home-banner-panel[data-active] .home-section-hero').count(), 1);
        await check(page);
        if (width >= 900) {
          const current = await sectionNav(page).locator('a[aria-current="page"]').allTextContents();
          assert.deepEqual(current, [label]);
        }
        if (label === 'Справка и отзывы') {
          assert.equal(await page.getByRole('link', { name: /Справочник F1/ }).getAttribute('href'), '/wiki');
          assert.equal(await page.getByRole('link', { name: /Написать отзыв/ }).getAttribute('href'), '/contact-admin');
          assert.equal(await page.locator('.home-guide-links .home-guide-link').count(), 3);
          assert.equal(await page.locator('.home-section-content .index-menu-icon, .home-section-content img').count(), 0);
        }
      }
      await sectionNav(page).getByRole('link', { name: 'Сезон', exact: true }).click();
      await selected(page, 1);
      await page.getByRole('button', { name: /1 из 4:/ }).click(); await selected(page, 0);
      await page.locator('.home-standing-table').waitFor(); await check(page);
      assert.deepEqual(errors, []);
      await context.close(); checks++;
    }
    const adaptive = await fixture(browser, 899, 'light', '&auth=member');
    await adaptive.page.getByRole('button', { name: /3 из 4:/ }).click(); await selected(adaptive.page, 2);
    await sectionNav(adaptive.page).getByRole('link', { name: 'Справка и отзывы', exact: true }).click(); await check(adaptive.page);
    await adaptive.page.setViewportSize({ width: 900, height: 1000 }); await check(adaptive.page);
    assert.equal(await sectionNav(adaptive.page).getByRole('link', { name: 'Справка и отзывы', exact: true }).getAttribute('aria-current'), 'page');
    await sectionNav(adaptive.page).getByRole('link', { name: 'Подписка', exact: true }).click(); await check(adaptive.page);
    await adaptive.page.setViewportSize({ width: 390, height: 1000 }); await check(adaptive.page);
    assert.equal(await sectionNav(adaptive.page).getByRole('link', { name: 'Подписка', exact: true }).getAttribute('aria-current'), 'page');
    await adaptive.context.close(); checks++;
    const touchCase = await fixture(browser, 390, 'dark', '&auth=member');
    await swipe(touchCase.page, 320, 35); await selected(touchCase.page, 1);
    await touchCase.page.getByRole('button', { name: /4 из 4:/ }).click(); await selected(touchCase.page, 3);
    await swipe(touchCase.page, 320, 35); await selected(touchCase.page, 0);
    await swipe(touchCase.page, 60, 330); await selected(touchCase.page, 3);
    await check(touchCase.page); await touchCase.context.close(); checks++;
    for (const theme of ['light', 'dark']) for (const signedIn of [true, false]) {
      const { page, context } = await fixture(browser, 390, theme, signedIn ? '&auth=member&spotlight=team' : '&spotlight=driver-1');
      const last = signedIn ? 3 : 1;
      await selected(page, last);
      const carousel = page.locator('.home-spotlight-viewport');
      await carousel.hover();
      // This failed before the fix: a trackpad swipe never crossed either edge.
      await page.mouse.wheel(120, 0); await selected(page, 0);
      for (const delta of [80, 40, 20, 8]) { await page.mouse.wheel(delta, 0); await page.waitForTimeout(20); }
      await selected(page, 0); // the same gesture's inertia must not page again
      await page.mouse.wheel(-120, 0); await selected(page, last);
      await page.waitForTimeout(220);
      await page.mouse.wheel(12, 0); await page.waitForTimeout(30); await selected(page, last);
      for (let step = 0; step < 5; step++) { await page.mouse.wheel(12, 0); await page.waitForTimeout(20); }
      await selected(page, 0); // slow input accumulates, small jitter alone does not wrap
      await page.waitForTimeout(220);
      const before = await page.evaluate(() => scrollY);
      await page.mouse.wheel(0, 180);
      await page.waitForFunction(before => scrollY > before, before);
      await selected(page, 0); // vertical page scrolling stays native
      await page.evaluate(() => scrollTo(0, 0));
      await swipe(page, 60, 330); await selected(page, last);
      await swipe(page, 320, 35); await selected(page, 0);
      await check(page); await context.close(); checks++;
    }
    for (const extra of ['&auth=member&state=favorites-error', '&auth=member&state=favorites-empty', '&auth=member&state=favorites-missing', '&scale=2&auth=member', '']) {
      const { page, context, errors } = await fixture(browser, 320, 'light', extra);
      await page.getByRole('button', { name: new RegExp(extra ? '2 из 4:' : '2 из 2:') }).click(); await selected(page, 1); await check(page);
      if (extra.includes('favorites-missing')) assert.match(await page.locator('.home-spotlight-slide:not([inert])').innerText(), /Нет данных за этот сезон/);
      if (extra.includes('favorites-error')) assert.match(await page.locator('.home-spotlight-slide:not([inert]) .home-favorite-error').innerText(), /Избранное не загрузилось/);
      if (extra.includes('favorites-empty')) assert.equal(await page.locator('.home-spotlight-slide:not([inert]) .home-favorite-kind').innerText(), 'В лидерах сезона');
      if (extra.includes('scale=2')) { await page.getByRole('button', { name: /4 из 4:/ }).click(); await selected(page, 3); await check(page); }
      if (!extra) { assert.equal(await page.locator('.home-personalize').isVisible(), true); assert.equal(await page.getByRole('link', { name: /Создать аккаунт/ }).getAttribute('href'), '/account?mode=register'); }
      assert.deepEqual(errors, []); await context.close(); checks++;
    }
    for (const theme of ['light', 'dark']) for (const width of [320, 390, 1440]) {
      const { page, context } = await fixture(browser, width, theme, '&spotlight=driver-1');
      await selected(page, 1); await check(page);
      const signup = page.getByRole('link', { name: /Создать аккаунт/ });
      await signup.focus();
      assert.equal(await signup.evaluate(el => getComputedStyle(el).outlineStyle), 'solid');
      assert.equal(await signup.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(185, 43, 37)');
      assert.notEqual(await signup.evaluate(el => getComputedStyle(el).backdropFilter), 'none');
      await page.emulateMedia({ contrast: 'more' });
      assert.equal(await signup.evaluate(el => getComputedStyle(el).backdropFilter), 'none');
      await page.emulateMedia({ contrast: 'no-preference' });
      const session = await context.newCDPSession(page);
      await session.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-transparency', value: 'reduce' }] });
      assert.equal(await signup.evaluate(el => getComputedStyle(el).backdropFilter), 'none');
      await session.detach();
      await signup.click();
      await page.getByRole('button', { name: 'Продолжить регистрацию', exact: true }).waitFor();
      assert.equal(await page.getByRole('button', { name: 'Регистрация', exact: true }).getAttribute('class'), 'active');
      await context.close(); checks++;
    }
    const real = await browser.newPage({ viewport: { width: 390, height: 1000 }, reducedMotion: 'reduce' });
    await real.addInitScript(() => localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'skipped' })));
    await real.route('https://telegram.org/**', route => route.abort());
    await real.route('**/api/**', route => {
      const path = new URL(route.request().url()).pathname;
      if (path === '/api/auth/me') return route.fulfill({ json: { id: 1, email: 'preview@example.test', role: 'user', email_verified: true } });
      const json = path === '/api/drivers' ? { drivers: [{ code: 'NOR', name: 'Pilot One', position: 1, points: 0 }, { code: 'PIA', name: 'Pilot Two', position: 2, points: 0 }] }
        : path === '/api/constructors' ? { constructors: [{ name: 'Team One', position: 1, points: 0 }] }
        : path === '/api/next-race' ? { status: 'ok', event_name: 'Test Grand Prix', season: 2026, round: 19, race_start_utc: '2026-10-25T20:00:00Z' } : {};
      return route.fulfill({ json });
    });
    await real.goto(`${base}/?spotlight=team&view=guide`);
    await real.getByRole('heading', { name: 'Справка и отзывы', exact: true }).waitFor();
    await real.reload(); await real.locator('.home-section-hero--guide').waitFor();
    await sectionNav(real).getByRole('link', { name: 'Игры', exact: true }).click();
    await real.waitForURL(url => url.searchParams.get('view') === 'games' && url.searchParams.get('spotlight') === 'team');
    await real.goBack(); await real.waitForURL(url => url.searchParams.get('view') === 'guide');
    await sectionNav(real).getByRole('link', { name: 'Сезон', exact: true }).click(); await selected(real, 3);
    await real.getByRole('button', { name: 'Следующий слайд' }).click(); await selected(real, 0);
    assert.equal(new URL(real.url()).searchParams.has('spotlight'), false);
    await real.close(); checks++;
    console.log(`${checks} carousel scenarios passed: two guest/four member slides, four icon sections, favorites/fallbacks, circular buttons/keyboard/native touch/trackpad, momentum and slow swipes, vertical scrolling, guest signup slide, views, image failures, glass accessibility, registration, 200% text and URL state.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
