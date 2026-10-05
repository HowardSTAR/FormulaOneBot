const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.STANDINGS_UI_URL || 'http://127.0.0.1:5174';
(async()=>{
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    for (const width of [390,1440]) for (const kind of ['drivers','constructors']) {
      const page = await browser.newPage({viewport:{width,height:900}});
      let mode = 'slow';
      await page.route(`**/api/${kind}?**`,async route=>{
        const year = new URL(route.request().url()).searchParams.get('season');
        if (year === '2025' && mode === 'slow') await new Promise(resolve=>setTimeout(resolve,1000));
        if (mode === 'fail') return route.fulfill({status:503,json:{detail:'Временно недоступно'}});
        const item = kind === 'drivers' ? {code:'QA',name:`Пилот ${year}`,driverId:'qa',constructorName:'QA',constructorId:'qa',position:1,points:100}
          : {name:`Команда ${year}`,constructorId:'qa',position:1,points:100};
        await route.fulfill({json:{[kind]:mode === 'empty' ? [] : [item]}});
      });
      await page.goto(`${base}/${kind}`);
      const select = page.getByRole('combobox',{name:'Сезон'}).filter({visible:true}).first();
      const choose = async year=>{
        await select.click();
        await page.getByRole('option',{name:year,exact:true}).click();
      };
      await choose('2025');
      await choose('2024');
      await page.waitForTimeout(1300);
      const expected = kind === 'drivers' ? 'Пилот 2024' : 'Команда 2024';
      assert.ok((await page.locator('body').innerText()).includes(expected));
      assert.ok(!(await page.locator('body').innerText()).includes(kind === 'drivers' ? 'Пилот 2025' : 'Команда 2025'));
      mode = 'fail';
      await choose('2023');
      const retry = page.getByRole('button',{name:'Повторить',exact:true}).filter({visible:true});
      await retry.waitFor();
      mode = 'ok';
      await retry.click();
      await page.getByText(kind === 'drivers' ? 'Пилот 2023' : 'Команда 2023',{exact:true}).filter({visible:true}).first().waitFor();
      mode = 'empty';
      await choose('2022');
      await page.getByText('Нет данных',{exact:true}).filter({visible:true}).waitFor();
      console.log(`${kind} ${width}px: delayed old response, error retry and empty state passed`);
      await page.close();
    }
  } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
