// Local browser checks with mocked race/share APIs and a sandboxed clipboard.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const tracks = require('../app/race_tracks.json');
const track = tracks.find(item => item.id.includes('canyon'));
const base = process.env.RACE_UI_URL || 'http://127.0.0.1:5173';
const token = 'A'.repeat(32);
const shareUrl = `https://example.test/share/${token}`;
const [x, y] = track.centerLine[0];
const ghost = { name: 'Тестовый призрак', time_ms: 120000, samples: [{t: 0, x: x + 80, y, rotation: 0}, {t: 120000, x: x + 80, y, rotation: 0}] };

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true, timeout: 30000 });
  try {
    for (const viewport of [
      {width: 1440, height: 900}, {width: 844, height: 390},
      {width: 844, height: 300}, {width: 390, height: 844}, {width: 320, height: 700},
    ]) {
      const mobile = viewport.width < 1000;
      const context = await browser.newContext({ viewport, hasTouch: mobile, isMobile: mobile });
      const page = await context.newPage();
      const errors = [];
      const creations = [];
      let failCreation = false;
      page.on('pageerror', e => { errors.push(e.message); console.error('Browser error:', e.message); });
      await page.addInitScript(() => {
        window.raceUiClipboard = [];
        window.raceUiDenyCopy = false;
        Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {writeText: async text => {
          if (window.raceUiDenyCopy) throw new Error('Clipboard denied');
          window.raceUiClipboard.push(text);
        }} });
      });
      await page.route('**/api/**', route => {
        const requestUrl = new URL(route.request().url());
        const path = requestUrl.pathname;
        if (path === '/api/engagement/shares') {
          creations.push(route.request().postDataJSON());
          if (failCreation) return route.fulfill({ status: 503, json: {detail: 'Не удалось создать карточку'} });
          return route.fulfill({ json: {token, kind: 'race', share_url: shareUrl, title: track.name, headline: '02:00.000'} });
        }
        const requestedTrack = requestUrl.searchParams.get('track_id') || track.id;
        const json = path.startsWith('/api/engagement/challenges/') ? {track_id: track.id, name:'Друг',time_ms:120000,ghost,entries:[]}
          : path === '/api/engagement/weekly' ? {track_id: track.id, end: '2026-10-05T00:00:00Z'}
          : path === '/api/race-game-leaderboard' ? {track_id:requestedTrack,ghost,entries:[],me:null}
          : path.includes('/race-game/') ? {track_id: track.id, ghost, entries: [], me: null}
          : path === '/api/next-race' ? {status: 'none'} : {};
        return route.fulfill({ json });
      });
      await page.goto(`${base}/race-game?weekly=1`);
      await page.locator('.race-game-frame, .race-game-orientation-prompt').first().waitFor();
      const orientation = page.getByRole('button', {name: 'Continue / Играть'});
      if (await orientation.isVisible()) await orientation.click();
      const frame = page.frameLocator('.race-game-frame');
      try { await frame.locator('canvas').waitFor({timeout: 15000}); }
      catch (error) {
        await page.screenshot({path: 'artifacts/race-simple-start-failure.png'});
        console.error('Frame URLs:', page.frames().map(frame => frame.url()));
        console.error('Page:', await page.locator('body').innerText());
        throw error;
      }
      const start = frame.getByRole('button', {name: 'НАЧАТЬ ЗАЕЗД', exact: true});
      await start.waitFor();
      await start.evaluate(el => { if (el.disabled) return new Promise(resolve => { const id = setInterval(() => { if (!el.disabled) { clearInterval(id); resolve(); } }, 50); }); });
      assert.equal(await frame.locator('.race-intro > .eyebrow').textContent(), 'ЗАЕЗД НА ТРАССЕ');
      assert.equal(await frame.locator('#modal-title').textContent(), track.name);
      assert.ok(await frame.locator('#track-preview svg').isVisible());
      assert.equal(await frame.locator('#track-description').textContent(), track.description);
      assert.ok(await frame.getByRole('combobox', {name: 'Выбрать трассу'}).isVisible());
      assert.equal(await frame.locator('#track-select option').count(), tracks.length);
      for (const selector of ['#menu-tracks-button', '.fullscreen-help', '.mobile-note', '.surface-chip', '.desktop-hint', '#challenge-panel a']) {
        assert.equal(await frame.locator(selector).count(), 0, selector);
      }
      assert.equal(await frame.locator('#challenge-panel').isVisible(), false);
      assert.ok(await frame.locator('.race-share-note').isVisible());
      const visibleControls = frame.locator(mobile ? '.touch-guide' : '.keyboard-guide');
      assert.ok(await visibleControls.isVisible());
      const dimensions = await start.evaluate(el => {
        const button = el.getBoundingClientRect();
        const card = document.querySelector('.modal-card').getBoundingClientRect();
        return {height: button.height, bottom: button.bottom, cardBottom: card.bottom, overflow: document.documentElement.scrollWidth > innerWidth};
      });
      assert.ok(dimensions.height >= 56);
      assert.ok(dimensions.bottom <= dimensions.cardBottom, 'Start is visible without scrolling');
      assert.equal(dimensions.overflow, false);
      const quickLinks = await frame.locator('.modal-quick-links').evaluate(el => ({bottom: el.getBoundingClientRect().bottom, viewport: innerHeight}));
      if (quickLinks.bottom > quickLinks.viewport) {
        await page.screenshot({path:'artifacts/race-select-short-failure.png'});
        console.error(await frame.locator('.modal-card').evaluate(card => [...card.children].map(el => ({class:el.className,height:el.getBoundingClientRect().height,top:el.getBoundingClientRect().top,bottom:el.getBoundingClientRect().bottom}))));
      }
      assert.ok(quickLinks.bottom <= quickLinks.viewport, 'Intro actions fit the viewport');
      await page.screenshot({ path: `artifacts/race-intro-simple-${viewport.width}-${viewport.height}.png` });

      // The finish flow exposes this button after a verified score save.
      // Simulate that availability to exercise the actual iframe-to-parent share action.
      const share = frame.locator('#share-race-button');
      await share.evaluate(el => { el.hidden = false; });
      const urlBefore = page.url();
      await share.click();
      const dialog = page.getByRole('dialog', {name: 'Поделиться заездом'});
      await dialog.getByText('Ссылка скопирована', {exact: true}).waitFor();
      assert.equal(creations.length, 1, 'StrictMode must create one card');
      assert.deepEqual(creations[0], {kind: 'race', track_id: track.id, consent: true});
      assert.equal(await dialog.getByRole('checkbox').count(), 0);
      assert.equal(await dialog.getByRole('button', {name: 'Создать карточку'}).count(), 0);
      assert.equal(await dialog.getByRole('textbox', {name: 'Ссылка на заезд'}).inputValue(), shareUrl);
      assert.deepEqual(await page.evaluate(() => window.raceUiClipboard), [shareUrl]);
      await dialog.getByRole('button', {name: 'Скопировать', exact: true}).click();
      assert.deepEqual(await page.evaluate(() => window.raceUiClipboard), [shareUrl, shareUrl]);
      assert.equal(page.url(), urlBefore);
      await page.screenshot({ path: `artifacts/race-share-simple-${viewport.width}-${viewport.height}.png` });
      await page.keyboard.press('Escape');
      assert.equal(await dialog.count(), 0);

      if (viewport.width === 1440) {
        await page.evaluate(() => { window.raceUiDenyCopy = true; });
        await share.click();
        await dialog.getByText('Нажмите «Скопировать» или скопируйте ссылку из поля.', {exact: true}).waitFor();
        assert.equal(await dialog.getByText('Ссылка скопирована', {exact: true}).count(), 0);
        await dialog.getByRole('button', {name: 'Скопировать', exact: true}).click();
        assert.ok(await dialog.getByRole('textbox', {name: 'Ссылка на заезд'}).evaluate(el => el === document.activeElement && el.selectionStart === 0 && el.selectionEnd === el.value.length));
        await page.keyboard.press('Escape');
        failCreation = true;
        await share.click();
        await dialog.getByRole('alert').waitFor();
        const beforeRetry = creations.length;
        failCreation = false;
        await page.evaluate(() => { window.raceUiDenyCopy = false; });
        await dialog.getByRole('button', {name: 'Повторить'}).click();
        await dialog.getByText('Ссылка скопирована', {exact: true}).waitFor();
        assert.equal(creations.length, beforeRetry + 1);
        await page.keyboard.press('Escape');
      }
      if (viewport.width === 1440) {
        const picker = frame.getByRole('combobox', {name:'Выбрать трассу'});
        for (const nextTrack of tracks) {
          await picker.selectOption(nextTrack.id);
          await start.waitFor();
          await page.waitForFunction(() => {
            const button = document.querySelector('.race-game-frame')?.contentDocument?.querySelector('#start-button');
            return button && !button.disabled;
          });
          assert.equal(await frame.locator('#modal-title').textContent(),nextTrack.name);
          assert.equal(await frame.locator('#track-description').textContent(),nextTrack.description);
          assert.equal(await frame.locator('#track-name').textContent(),nextTrack.name.toUpperCase());
          assert.equal(await frame.locator('#time-value').textContent(),'00:00.000');
          assert.ok(await frame.locator('#track-preview polyline').getAttribute('points') === [...nextTrack.centerLine,nextTrack.centerLine[0]].map(point=>point.join(',')).join(' '));
          assert.equal(await frame.locator('body').evaluate(() => localStorage.getItem('emerald-loop-selected-track')),nextTrack.id);
          await page.screenshot({path:`artifacts/race-select-${nextTrack.id}.png`});
        }
        await picker.selectOption(track.id);
        await frame.locator('#modal-title').getByText(track.name,{exact:true}).waitFor();
        await picker.focus();
        await page.keyboard.press('ArrowDown');
        assert.equal(await frame.locator('#time-value').textContent(),'00:00.000','Native arrow keys must not start the race');
        await picker.selectOption(track.id);
        await start.waitFor();
        await page.waitForFunction(() => !document.querySelector('.race-game-frame').contentDocument.querySelector('#start-button').disabled);
        await start.click();
        await frame.locator('#time-value').evaluate(el => new Promise(resolve => {
          const check = () => { if (el.textContent !== '00:00.000') { observer.disconnect(); resolve(); } };
          const observer = new MutationObserver(check); observer.observe(el, {childList: true}); check();
        }));
        await page.screenshot({path: 'artifacts/race-ghost-subtle.png'});
        assert.equal(await frame.locator('.surface-chip').count(), 0);
        assert.equal(await frame.locator('.desktop-hint').count(), 0);
        // A new track leaves the friend challenge and uses the newly selected track for sharing.
        await page.goto(`${base}/race-game?challenge=${token}`);
        await frame.getByRole('combobox',{name:'Выбрать трассу'}).waitFor();
        await frame.locator('#challenge-title').getByText('Вызов: Друг',{exact:true}).waitFor();
        const other = tracks.find(item=>item.id !== track.id);
        await frame.locator('#track-select').selectOption(other.id);
        await frame.locator('#modal-title').getByText(other.name,{exact:true}).waitFor();
        assert.equal(await frame.locator('#challenge-panel').isVisible(),false);
        await frame.locator('#share-race-button').evaluate(el=>{el.hidden=false;});
        await frame.locator('#share-race-button').click();
        await dialog.getByText('Ссылка скопирована',{exact:true}).waitFor();
        assert.equal(creations.at(-1).track_id,other.id);
      }
      assert.deepEqual(errors, []);
      await context.close();
      console.log(`${viewport.width}×${viewport.height}: compact start, controls, weekly route and instant sharing passed`);
    }
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
