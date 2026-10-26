// Local visual/interaction regression. All API replies and writes come from the Vite-only fixture.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.PREDICTIONS_DESIGN_URL || 'http://127.0.0.1:5175';
const onlyFlows = process.env.PREDICTIONS_DESIGN_FLOWS === '1';
const out = process.env.PREDICTIONS_DESIGN_ARTIFACTS || '/tmp/turbotears-predictions';
fs.mkdirSync(out, {recursive: true});
const url = (params = {}) => `${base}/tests/home-design-preview.html?${new URLSearchParams({page:'predictions', auth:'member', theme:'light', ...params})}`;
async function fit(page) {
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Document must fit viewport');
  const invalid = await page.locator('.predictions-page input, .prediction-submit-row button, .predictions-tabs a, .prediction-grid .driver-picker-trigger').evaluateAll(elements => elements.filter(el => {const r=el.getBoundingClientRect(); return r.width && (r.left < 0 || r.right > innerWidth + 1);}).map(el => el.outerHTML));
  assert.deepEqual(invalid, [], 'Controls must fit viewport');
}
(async () => {
 const browser = await chromium.launch({channel: process.env.BROWSER_CHANNEL || 'chrome', headless: true});
 try {
  for (const theme of onlyFlows ? [] : ['light','dark']) for (const width of [320,390,768,899,900,1024,1440,1920]) {
   const context = await browser.newContext({viewport:{width,height:960}, reducedMotion:'reduce'});
   const page = await context.newPage(); const errors=[];
   page.on('pageerror', e => errors.push(e.message));
   await page.goto(url({theme,auth:'linked'}));
   await page.getByRole('heading',{name:'Гран-при Мексики',exact:true}).waitFor();
   await page.evaluate(() => document.fonts.ready);
   await fit(page);
   assert.equal(await page.locator('.prediction-grid .driver-picker-trigger').count(),8);
   await page.getByRole('link',{name:'Турнирная таблица',exact:true}).click();
   await page.locator('.prediction-leaderboard table').waitFor(); await fit(page);
   assert.equal(await page.locator('.prediction-leaderboard tbody tr').count(),3);
   if ([390,1440].includes(width)) { await page.evaluate(() => window.scrollTo(0,0)); await page.screenshot({path:`${out}/table-${width}-${theme}.png`,fullPage:true}); }
   await page.getByRole('link',{name:'Мой сезон',exact:true}).click();
   await page.getByRole('heading',{name:'Мой сезон 2026',exact:true}).waitFor(); await fit(page);
   if ([390,1440].includes(width)) { await page.evaluate(() => window.scrollTo(0,0)); await page.screenshot({path:`${out}/season-${width}-${theme}.png`,fullPage:true}); }
   await page.getByRole('button',{name:'Разобрать последний этап'}).click();
   await page.locator('.personal-review .review-item').first().waitFor(); await fit(page);
   await page.keyboard.press('Escape');
   await page.getByRole('link',{name:'Лиги друзей',exact:true}).click();
   await page.getByRole('heading',{name:'Приватные лиги',exact:true}).waitFor(); await fit(page);
   if ([390,1440].includes(width)) { await page.evaluate(() => window.scrollTo(0,0)); await page.screenshot({path:`${out}/leagues-${width}-${theme}.png`,fullPage:true}); }
   await page.getByRole('link',{name:'Мой прогноз',exact:true}).click();
   await page.getByRole('button',{name:'Поул-позиция: Выберите пилота',exact:true}).click();
   await page.getByRole('dialog',{name:'Выберите пилота'}).waitFor();
   await page.getByRole('textbox',{name:'Поиск пилота'}).fill('Норрис');
   await page.locator('.driver-picker-option').click();
   await page.getByRole('button',{name:'Поул-позиция: Ландо Норрис',exact:true}).waitFor();
   await page.locator('.prediction-safety-car').getByRole('button',{name:'Да',exact:true}).click();
   assert.equal(await page.locator('.prediction-safety-car').getByRole('button',{name:'Да',exact:true}).getAttribute('aria-pressed'),'true');
   await page.getByText('Как начисляются баллы',{exact:true}).click();
   await page.locator('.prediction-rules table').waitFor(); await fit(page);
   if ([390,1440].includes(width)) { await page.getByText('Как начисляются баллы',{exact:true}).click(); await page.evaluate(() => window.scrollTo(0,0)); await page.screenshot({path:`${out}/form-${width}-${theme}.png`,fullPage:true}); }
   assert.deepEqual(errors,[]); await context.close();
   console.log(`${theme} ${width}px: form, choices, navigation, table, review, leagues, overflow passed`);
  }
  for (const theme of ['light','dark']) for (const width of [390,1440]) {
    const filledContext=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'}); const filled=await filledContext.newPage();
    await filled.goto(url({auth:'linked',theme,state:'prediction-saved'}));
    await filled.getByRole('button',{name:'Победитель: Ландо Норрис',exact:true}).waitFor();
    await filled.locator('.prediction-grid img').evaluateAll(images=>Promise.all(images.map(img=>img.decode().catch(()=>{}))));
    await fit(filled);
    await filled.screenshot({path:`${out}/slots-filled-${width}-${theme}.png`,fullPage:true});
    await filled.locator('.prediction-form-shell').screenshot({path:`${out}/slots-panel-${width}-${theme}.png`});
    await filledContext.close();
  }
  const context = await browser.newContext({viewport:{width:390,height:960},reducedMotion:'reduce'}); const page=await context.newPage();
  for (const state of ['prediction-error','prediction-before','prediction-closed','prediction-finished','prediction-loading','prediction-name','prediction-empty']) {
   await page.goto(url({state})); await page.getByRole('heading',{name:'Прогнозы',exact:true}).waitFor();
   if (state==='prediction-error') { await page.getByRole('button',{name:'Повторить загрузку'}).click(); await page.getByRole('heading',{name:'Гран-при Мексики',exact:true}).waitFor(); }
   if (['prediction-before','prediction-closed'].includes(state)) { await page.locator('.driver-picker-trigger').first().waitFor(); assert.equal(await page.locator('.driver-picker-trigger').first().isDisabled(),true); }
   if (state==='prediction-finished') await page.getByRole('heading',{name:'Ждём следующий этап'}).waitFor();
   if (state==='prediction-loading') await page.getByText('Загрузка данных этапа…').waitFor();
   if (state==='prediction-name') { await page.getByRole('textbox',{name:'Имя участника',exact:true}).fill('Apex'); await page.getByRole('button',{name:'Сохранить имя',exact:true}).click(); await page.getByText('Apex',{exact:true}).waitFor(); }
   if (state==='prediction-empty') { await page.getByRole('link',{name:'Турнирная таблица',exact:true}).click(); await page.getByText('Турнирная таблица пока пуста.').waitFor(); }
   await fit(page);
  }
  await page.goto(url({state:'prediction-save-error'})); await page.getByRole('heading',{name:'Гран-при Мексики',exact:true}).waitFor();
  const choices=[['Победитель','NOR'],['2 место','PIA'],['3 место','VER'],['4 место','LEC'],['5 место','HAM'],['Поул-позиция','NOR'],['Лучший круг','NOR'],['Первый сход','STR']];
  for (const [label,code] of choices) { await page.getByRole('button',{name:`${label}: Выберите пилота`,exact:true}).click(); await page.getByRole('textbox',{name:'Поиск пилота'}).fill(code); await page.locator('.driver-picker-option:not(:disabled)').click(); }
  await page.getByRole('button',{name:'2 место: Оскар Пиастри',exact:true}).click(); await page.getByRole('textbox',{name:'Поиск пилота'}).fill('NOR'); assert.equal(await page.locator('.driver-picker-option').isDisabled(),true); await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'Отправить прогноз',exact:true}).click(); await page.getByRole('alert').waitFor();
  await page.getByRole('button',{name:'Отправить прогноз',exact:true}).click(); await page.getByText('Прогноз сохранён. Его можно изменить до начала квалификации.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Обновить прогноз',exact:true}).waitFor();
  await page.goto(url({auth:'guest'})); await page.getByRole('button',{name:'Войти и сохранить черновик'}).waitFor(); assert.equal(await page.locator('.predictions-tabs').count(),0); await fit(page);
  await page.goto(url({format:'sprint',championship:'1'})); await page.locator('.title-answer').waitFor(); assert.equal(await page.locator('.prediction-grid .driver-picker-trigger').count(),10); await fit(page);
  await page.locator('.title-answer').getByRole('button',{name:'Нет',exact:true}).click(); assert.equal(await page.locator('.title-answer').getByRole('button',{name:'Нет',exact:true}).getAttribute('aria-pressed'),'true');
  for (const width of [320,390,900,1440]) { await page.setViewportSize({width,height:960}); await page.goto(url({scale:'2',auth:'linked',championship:'1'})); await page.getByRole('heading',{name:'Гран-при Мексики',exact:true}).waitFor(); await fit(page); await page.evaluate(() => window.scrollTo(0,0)); await page.screenshot({path:`${out}/scale-${width}.png`,fullPage:true}); }
  // Real keyboard route to the primary form control and a visible focus ring.
  await page.goto(url({auth:'linked'})); await page.getByRole('heading',{name:'Гран-при Мексики',exact:true}).waitFor();
  await page.getByRole('link',{name:'Мой прогноз',exact:true}).focus(); await page.keyboard.press('Tab');
  assert.ok(await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle !== 'none'));
  await page.setViewportSize({width:1440,height:960});
  await page.goto(url({auth:'linked',season:'2025'}) + '#invite=preview-token');
  await page.getByRole('heading',{name:'Гран-при Мексики',exact:true}).waitFor();
  const nav=page.getByRole('navigation',{name:'Разделы прогнозов',exact:true});
  const start=await nav.getByRole('link',{name:'Мой прогноз',exact:true}).boundingBox();
  const end=await nav.getByRole('link',{name:'Лиги друзей',exact:true}).boundingBox();
  await page.mouse.move(start.x+start.width/2,start.y+start.height/2); await page.mouse.down();
  await page.mouse.move(end.x+end.width/2,end.y+end.height/2,{steps:8}); await page.mouse.up();
  await page.getByRole('heading',{name:'Приватные лиги',exact:true}).waitFor();
  assert.match(await nav.getByRole('link',{name:'Лиги друзей',exact:true}).getAttribute('href'),/season=2025.*#invite=preview-token/);
  await nav.getByRole('link',{name:'Мой прогноз',exact:true}).hover();
  assert.equal(await nav.getByRole('link',{name:'Мой прогноз',exact:true}).evaluate(el=>getComputedStyle(el).textDecorationLine),'none');
  await page.emulateMedia({contrast:'more',reducedMotion:'reduce'});
  assert.equal(await nav.evaluate(el=>getComputedStyle(el).backdropFilter),'none');
  assert.equal(await nav.locator('.home-section-lens').evaluate(el=>getComputedStyle(el).transitionDuration),'0s');
  await fit(page);
  await page.screenshot({path:`${out}/contrast-1440.png`,fullPage:true});
  await context.close();
  console.log('Glass drag, URL/invitation preservation, hover, reduced motion and increased contrast passed');
  console.log('Loading/error/retry, name, closed windows, empty/guest, duplicate choices, save failure/success, sprint/title, 200% text and focus passed');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
