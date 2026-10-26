// Local-only fixture: portraits, result comparisons, responsive dialog and keyboard recovery.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.env.PREDICTIONS_DESIGN_URL||'http://127.0.0.1:5175';
const url=(theme,scale)=>`${base}/tests/home-design-preview.html?${new URLSearchParams({page:'predictions',tab:'history',auth:'linked',theme,state:'prediction-saved',...(scale?{scale:'2'}:{})})}`;
async function open(page,theme='light',scale=false){
 await page.goto(url(theme,scale));
 const opener=page.getByRole('button',{name:'Разобрать последний этап'});await opener.click();
 const dialog=page.getByRole('dialog',{name:'Мой прогноз',exact:true});
 await dialog.locator('.review-driver').first().waitFor();
 await dialog.getByText('Ландо Норрис (NOR)',{exact:true}).first().waitFor();
 return {opener,dialog};
}
async function fit(page,dialog){
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Document fits');
 assert.ok(await dialog.locator('.personal-review-content').evaluate(el=>el.scrollWidth<=el.clientWidth),'Dialog content fits');
 assert.ok(await dialog.evaluate(el=>{const r=el.getBoundingClientRect();return r.left>=-1&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1;}),'Window fits');
}
(async()=>{const browser=await chromium.launch({channel:process.env.BROWSER_CHANNEL||'chrome',headless:true});try{
 for(const theme of ['light','dark']) for(const width of [320,390,768,1440,1920]){
  const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const {dialog,opener}=await open(page,theme);await fit(page,dialog);
  assert.equal(await dialog.locator('.review-item').count(),9);
  assert.equal(await dialog.locator('.review-driver .entrant-portrait').count(),17,'Both results and retirement group have portraits');
  await dialog.locator('.entrant-portrait img').evaluateAll(images=>Promise.all(images.filter(img=>{const r=img.getBoundingClientRect();return r.top<innerHeight&&r.bottom>0;}).map(img=>img.decode().catch(()=>{}))));
  assert.equal(await dialog.locator('.entrant-portrait img').evaluateAll(images=>images.filter(img=>{const r=img.getBoundingClientRect();return r.top<innerHeight&&r.bottom>0;}).every(img=>img.naturalWidth>0)),true,'Preview portraits load');
  const meter=dialog.getByRole('meter',{name:'Баллы за этап'});assert.equal(await meter.getAttribute('aria-valuenow'),'25');
  if([390,1440].includes(width)) await page.screenshot({path:`artifacts/personal-review-design-${width}-${theme}.png`});
  await dialog.getByRole('button',{name:/Частично/}).click();assert.equal(await dialog.locator('.review-item').count(),2);
  await dialog.getByRole('button',{name:/Не угадано/}).click();assert.equal(await dialog.locator('.review-item').count(),2);
  await dialog.getByRole('button',{name:/Угадано/}).filter({hasText:'Угадано'}).click();assert.equal(await dialog.locator('.review-item').count(),5);
  await dialog.getByRole('button',{name:'Все категории',exact:true}).click();
  const details=dialog.getByText('Как считаются очки',{exact:true}).first();await details.click();await dialog.getByText('Результат не совпал с прогнозом.',{exact:true}).first().waitFor();await details.click();
  await dialog.locator('.personal-review-content').evaluate(el=>{el.scrollTop=el.scrollHeight;});
  assert.ok(await dialog.getByRole('button',{name:'Закрыть разбор прогноза'}).isVisible());
  assert.equal(await page.evaluate(()=>document.documentElement.style.overflow),'hidden');
  await page.keyboard.press('Escape');await dialog.waitFor({state:'detached'});assert.equal(await opener.evaluate(el=>el===document.activeElement),true);
  assert.notEqual(await page.evaluate(()=>document.documentElement.style.overflow),'hidden');
  assert.deepEqual(errors,[]);await context.close();console.log(`${width}px ${theme}: portraits, comparisons, filters, details, scroll, Escape and focus passed`);
 }
 for(const width of [320,390,1440]){
  const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'});const page=await context.newPage();const {dialog}=await open(page,'dark',true);await fit(page,dialog);await page.screenshot({path:`/tmp/personal-review-scale-${width}.png`});await context.close();
 }
 // Regular motion, click-to-close and backdrop dismissal retain the same native focus contract.
 for(const width of [390,1440]){
  const context=await browser.newContext({viewport:{width,height:1000}});const page=await context.newPage();let {dialog,opener}=await open(page);
  await dialog.getByRole('button',{name:'Закрыть разбор прогноза'}).click();await dialog.waitFor({state:'detached'});assert.equal(await opener.evaluate(el=>el===document.activeElement),true);
  await opener.click();await page.getByRole('dialog',{name:'Мой прогноз',exact:true}).waitFor();await page.mouse.click(1,1);await page.getByRole('dialog',{name:'Мой прогноз',exact:true}).waitFor({state:'detached'});
  await context.close();
 }
 console.log('200% text, animated close and backdrop passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
