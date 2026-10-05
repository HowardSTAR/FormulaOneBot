// Every submission and image is mocked; no account change or message is sent.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const base = process.env.FORM_UI_URL || 'http://127.0.0.1:5174';
const token = 'A'.repeat(32);
const card = {token,kind:'history',title:'История пилота',subtitle:'2026',headline:'P1',lines:[],cta:'Открыть',provisional:false,web_url:`${base}/share/${token}`,share_url:`https://t.me/example?start=${token}`,mini_app_url:null,image_url:`${base}/qa-card.png`,expires:0};
const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6rWQAAAAASUVORK5CYII=','base64');
(async()=>{
  const browser = await chromium.launch({channel:'msedge',headless:true});
  try {
    for (const width of [390,1440]) {
      const page = await browser.newPage({viewport:{width,height:900}});
      let fail = true, contactRequests = 0;
      await page.addInitScript(()=>{
        localStorage.setItem('turbotears-onboarding-v2',JSON.stringify({status:'completed'}));
        window.sharedFiles = [];
        window.copiedLinks = [];
        Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>window.copiedLinks.push(text)}});
        Object.defineProperty(navigator,'canShare',{value:({files})=>files?.length===1});
        Object.defineProperty(navigator,'share',{value:async ({files})=>{window.sharedFiles.push({size:files[0].size,type:files[0].type})}});
      });
      await page.route('**/qa-card.png',route=>route.fulfill({body:image,contentType:'image/png'}));
      await page.route('**/api/**',route=>{
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/standings-history') return route.fulfill({json:{series:[{id:'alonso',name:'Fernando Alonso',seasons:[{season:2026,status:'available',current:true,standing:{position:1,points:100,wins:2,round:15,teams:['Aston Martin']}}]}],years:[{season:2026,status:'available',source:'https://example.test'}],note:'Тестовые данные'}});
        if (route.request().method() === 'GET') return route.continue();
        if (path === '/api/contact-admin') {contactRequests++;return route.fulfill({status:fail?503:200,json:fail?{detail:'Временно недоступно. Повторите отправку.'}:{ok:true}})}
        if (path === '/api/engagement/shares') return route.fulfill({json:card});
        return route.fulfill({json:{ok:true}});
      });
      await page.goto(base+'/reset-password?token=qa');
      const passwords = page.locator('input[type="password"]');
      await passwords.nth(0).fill('Validpassword123');
      await passwords.nth(1).fill('Otherpassword123');
      assert.ok(await page.getByRole('status').filter({hasText:'Пароли не совпадают'}).isVisible());
      assert.equal(await passwords.nth(1).getAttribute('aria-invalid'),'true');
      assert.equal(await page.getByRole('button',{name:'Сохранить новый пароль'}).isDisabled(),true);
      await passwords.nth(1).fill('Validpassword123');
      assert.equal(await page.locator('#password-mismatch').count(),0);
      assert.equal(await page.getByRole('button',{name:'Сохранить новый пароль'}).isDisabled(),false);
      await page.goto(base+'/contact-admin');
      await page.getByLabel('Имя',{exact:true}).fill('QA Tester');
      await page.getByLabel('Контакт',{exact:true}).fill('qa@example.test');
      const message = page.locator('textarea');
      await message.fill('Тестовая проверка сохранения текста');
      await page.getByRole('button',{name:'Отправить в Telegram'}).click();
      await page.getByRole('alert').waitFor();
      assert.equal(await message.inputValue(),'Тестовая проверка сохранения текста');
      fail = false;
      await page.getByRole('button',{name:'Отправить в Telegram'}).click();
      await page.getByRole('status').filter({hasText:'доставлено'}).waitFor();
      assert.equal(contactRequests,2);
      await page.goto(base+'/history?ids=alonso&from=2026&to=2026');
      await page.getByRole('button',{name:'Поделиться сравнением'}).click();
      const dialog = page.getByRole('dialog',{name:'Поделиться с друзьями'});
      await dialog.getByRole('checkbox').check();
      await dialog.getByRole('button',{name:'Создать карточку'}).click();
      await dialog.getByRole('button',{name:'Отправить в Telegram'}).click();
      await dialog.getByRole('status').filter({hasText:'отправлена'}).waitFor();
      assert.deepEqual(await page.evaluate(()=>window.sharedFiles),[{size:image.length,type:'image/png'}]);
      await dialog.getByRole('button',{name:'Копировать ссылку'}).click();
      assert.deepEqual(await page.evaluate(()=>window.copiedLinks),[card.web_url]);
      await page.keyboard.press('Escape');
      assert.equal(await dialog.count(),0);
      await page.goto(base+'/wiki');
      await page.getByRole('searchbox').fill('zzzzzzzz-no-match');
      await page.getByRole('button',{name:'Сбросить фильтры'}).click();
      assert.equal(await page.getByRole('searchbox').inputValue(),'');
      for (const path of ['/legal/notices','/legal/assets']) {
        await page.goto(base+path);
        await page.locator('summary').click();
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
      }
      console.log(`${width}px: password feedback, contact recovery, image File sharing, glossary and legal details passed`);
      await page.close();
    }
  } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
