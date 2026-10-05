// Local browser regression: synthetic API responses, no forecasts or messages sent.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.PREDICTION_REVIEW_UI_URL || 'http://127.0.0.1:5174';
const fixture = 'artifacts/prediction-review-fixture.jpg';
const image = fs.existsSync(fixture) ? fs.readFileSync(fixture) : Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZYsAAAAASUVORK5CYII=', 'base64');
const imageType = fs.existsSync(fixture) ? 'image/jpeg' : 'image/png';
const items = [
  ['pole_driver', 'Поул-позиция', 'miss', 0, 3], ['winner_driver', 'Победитель', 'partial', 3, 8],
  ['second_driver', '2 место', 'miss', 0, 5], ['third_driver', '3 место', 'partial', 2, 4],
  ['fourth_driver', '4 место', 'partial', 2, 3], ['fifth_driver', '5 место', 'miss', 0, 2],
  ['fastest_lap_driver', 'Лучший круг', 'miss', 0, 3], ['first_retirement_driver', 'Первый сход', 'miss', 0, 5],
  ['safety_car', 'Машина безопасности', 'miss', 0, 4],
].map(([key, label, status, points, maximum]) => ({key, label, status, points, maximum,
  predicted: key === 'safety_car' ? 0 : 'ANT', actual: key === 'safety_car' ? 1 : 'VER',
  position: status === 'partial' ? 2 : null, reason: status === 'partial' ? 'Ваш пилот финишировал P2. Начислены баллы за близкую позицию.' : 'Нет совпадения в пределах начисления баллов.',
  rule: {exact: maximum, offsets: status === 'partial' ? [3, 2, 1] : [0, 0, 0]}}));
const round = {season: 2026, round: 16, event_name: 'Bahrain Grand Prix', points: 7, max_points: 37};
const progress = {season: 2026, latest: {...round, items}, history: [
  {...round, round: 12, event_name: 'Spanish Grand Prix', points: 13},
  {...round, round: 13, event_name: 'Azerbaijan Grand Prix', points: 12}, round,
], previous_points: 12, best_points: 14, average_points: 11.4, place: 1, place_change: 0,
  gap_to_higher: null, achievements: ['Первый сохранённый прогноз'], categories: [
    {label: 'Победитель', exact: 2, known: 5}, {label: 'Первый сход', exact: 0, known: 0},
  ]};
const card = {token: 'a'.repeat(32), kind: 'prediction', title: 'Мой прогноз', headline: '7 / 37 баллов',
  web_url: `${base}/share/${'a'.repeat(32)}`, image_url: `${base}/api/engagement/shares/${'a'.repeat(32)}/image.jpg`, provisional: false};

async function noOverflow(page, review) {
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Page must fit viewport');
  if (review) assert.ok(await page.locator('.personal-review-content').evaluate(el => el.scrollWidth <= el.clientWidth), 'Review must not scroll horizontally');
}

(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  try {
    for (const width of [320, 390, 768, 1440]) {
      const context = await browser.newContext({viewport: {width, height: 960}, reducedMotion: 'reduce'});
      const page = await context.newPage();
      const errors = [], creations = [], events = [];
      let failCreate = false, failReview = false, waiting = false, emptyHistory = false, pendingCreate, pendingImage;
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => {
        localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({status: 'completed'}));
        Object.defineProperty(navigator, 'clipboard', {value: {writeText: async () => {throw Error('Clipboard denied');}}, configurable: true});
      });
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.origin !== base) return route.abort();
        if (!url.pathname.startsWith('/api/')) return route.continue();
        if (url.pathname.endsWith('/image.jpg')) {if (pendingImage) await pendingImage; return route.fulfill({body: image, contentType: imageType});}
        if (url.pathname === '/api/auth/me') return route.fulfill({json: {id: 1, role: 'user', telegram_id: 123, display_name: 'Alex Racing'}});
        if (url.pathname === '/api/next-race') return route.fulfill({json: {status: 'season_finished'}});
        if (url.pathname === '/api/settings') return route.fulfill({json: {timezone: 'UTC'}});
        if (url.pathname === '/api/drivers') return route.fulfill({json: {drivers: [{code: 'ANT', name: 'Andrea Kimi Antonelli'}, {code: 'VER', name: 'Max Verstappen'}]}});
        if (url.pathname === '/api/predictions/current') return route.fulfill({json: {status: 'ok', ...round, is_open: false, opens_at_utc: '2099-10-09T08:30:00Z', profile: {completed: true, display_name: 'Alex Racing'}, drivers: [], scoring_rules: [], prediction: null}});
        if (url.pathname === '/api/predictions/leaderboard') return route.fulfill({json: {entries: [], rounds: [], season: 2026}});
        if (url.pathname === '/api/predictions/personal-season') return route.fulfill({json: emptyHistory ? {...progress, latest: null, history: [], best_points: null, average_points: null, place: null} : progress});
        if (url.pathname.startsWith('/api/predictions/mine/')) {
          if (failReview) return route.fulfill({status: 503, json: {detail: 'Временно недоступно'}});
          const reviewItems = waiting ? items.map((item, i) => i >= 7 ? {...item, status: i === 7 ? 'unknown' : 'unavailable', actual: i === 7 ? item.actual : null, points: null} : item) : items;
          return route.fulfill({json: {...round, complete: !waiting, items: reviewItems, race_facts: {source: 'Тестовый протокол', safety_car: 1, retirement_order_confirmed: false}}});
        }
        if (url.pathname === '/api/engagement/shares') {
          assert.equal(route.request().method(), 'POST');
          creations.push(route.request().postDataJSON());
          if (pendingCreate) await pendingCreate;
          return route.fulfill(failCreate ? {status: 503, json: {detail: 'Карточка временно недоступна'}} : {json: card});
        }
        if (url.pathname === '/api/engagement/event') events.push(route.request().postDataJSON());
        if (url.pathname.endsWith('/telegram')) assert.fail('Messages must only be prepared after an explicit send');
        return route.fulfill({json: {items: [], unread: 0, status: 'none', entries: []}});
      });
      await page.goto(`${base}/predictions?tab=history`);
      await page.getByRole('heading', {name: 'Мой сезон 2026'}).waitFor();
      assert.equal(await page.locator('.season-progress-metrics>div').count(), 3);
      assert.match(await page.locator('.season-progress-rounds>button').first().innerText(), /Bahrain/);
      await noOverflow(page);
      const [first, second] = await Promise.all([page.locator('.season-progress-primary').boundingBox(), page.locator('.season-progress-actions>.share-button').boundingBox()]);
      assert.ok(second.x >= first.x + first.width + 10 || second.y >= first.y + first.height + 10, 'Actions must be separated');
      await page.getByText('Точность по категориям', {exact: true}).click();
      await page.getByText('Ещё нет результатов', {exact: true}).waitFor();
      await page.getByText('Точность по категориям', {exact: true}).click();
      if ([390, 1440].includes(width)) await page.locator('.season-progress').screenshot({path: `artifacts/prediction-season-${width}.png`});
      const opener = page.getByRole('button', {name: 'Разобрать последний этап'});
      await opener.click();
      const review = page.locator('.personal-review');
      await review.getByText('Andrea Kimi Antonelli (ANT)').first().waitFor();
      assert.equal(await review.locator('.review-item').count(), 9);
      await noOverflow(page, true);
      await review.getByRole('button', {name: /Частично/}).click();
      assert.equal(await review.locator('.review-item').count(), 3);
      await review.getByRole('button', {name: /Ожидают данных/}).click();
      assert.equal(await review.locator('.review-item').count(), 0);
      await review.getByRole('button', {name: 'Все категории'}).click();
      await review.getByText('Как считаются очки', {exact: true}).first().click();
      await review.getByText('Если фактические данные отсутствуют, пункт не учитывается в максимуме.').first().waitFor();
      await review.getByText('Как считаются очки', {exact: true}).first().click();
      await review.locator('.personal-review-content').evaluate(el => {el.scrollTop = 0;});
      if ([390, 1440].includes(width)) await page.screenshot({path: `artifacts/prediction-review-${width}.png`});
      const content = review.locator('.personal-review-content');
      await content.evaluate(el => {el.scrollTop = el.scrollHeight;});
      assert.ok(await review.getByRole('button', {name: 'Закрыть разбор прогноза'}).isVisible(), 'Close stays visible while scrolling');
      await content.evaluate(el => {el.scrollTop = 0;});
      let releaseCreate;
      pendingCreate = new Promise(resolve => {releaseCreate = resolve;});
      let releaseImage;
      pendingImage = new Promise(resolve => {releaseImage = resolve;});
      await review.getByRole('button', {name: 'Поделиться результатом'}).click();
      const share = page.locator('.share-dialog');
      await share.getByText('Создаём и сохраняем карточку…').waitFor();
      assert.equal(await share.getByRole('checkbox').count(), 0);
      releaseCreate(); pendingCreate = null;
      await share.getByText('Карточка сохранена', {exact: false}).waitFor();
      assert.deepEqual(creations, [{kind: 'prediction', season: 2026, round: 16, consent: true}]);
      assert.deepEqual(events, []);
      assert.equal(await share.getByRole('button', {name: 'Готовим изображение…'}).isDisabled(), true, 'File must be ready before sending');
      releaseImage(); pendingImage = null;
      await share.getByRole('button', {name: 'Отправить в Telegram'}).waitFor();
      await share.locator('img').evaluate(img => img.decode());
      if ([390, 1440].includes(width)) await page.screenshot({path: `artifacts/prediction-share-${width}.png`});
      await noOverflow(page);
      await share.getByRole('button', {name: 'Копировать ссылку'}).click();
      assert.equal(await share.locator('input').evaluate(el => el === document.activeElement), true);
      await page.keyboard.press('Escape');
      await share.waitFor({state: 'detached'});
      assert.equal(await review.getByRole('button', {name: 'Поделиться результатом'}).evaluate(el => el === document.activeElement), true);
      await page.keyboard.press('Escape');
      await review.waitFor({state: 'detached'});
      assert.equal(await opener.evaluate(el => el === document.activeElement), true);
      if (width === 390) {
        failCreate = true;
        await page.locator('.season-progress-actions>.share-button').click();
        await share.getByRole('button', {name: 'Повторить создание'}).waitFor();
        failCreate = false;
        await share.getByRole('button', {name: 'Повторить создание'}).click();
        await share.getByText('Карточка сохранена', {exact: false}).waitFor();
        assert.equal(creations.length, 3);
        await page.keyboard.press('Escape');
        failReview = true;
        await opener.click();
        await review.getByRole('heading', {name: 'Не удалось загрузить разбор'}).waitFor();
        failReview = false; waiting = true;
        await review.getByRole('button', {name: 'Повторить', exact: true}).click();
        await review.getByText('Результат предварительный.', {exact: true}).waitFor();
        assert.match(await review.getByRole('button', {name: /Ожидают данных/}).innerText(), /1/);
        await review.getByRole('button', {name: /Ожидают данных/}).click();
        assert.equal(await review.locator('.review-item').count(), 1);
        assert.equal(await review.locator('.review-unavailable').count(), 1);
        await review.getByRole('button', {name: /Нет разбивки/}).click();
        assert.equal(await review.locator('.review-item').count(), 1);
        assert.equal(await review.locator('.review-unknown').count(), 1);
        await page.keyboard.press('Escape');
        emptyHistory = true;
        await page.reload();
        await page.getByText('После расчёта вашего первого этапа здесь появятся результаты.').waitFor();
        assert.equal(await page.locator('.season-progress-rounds>button').count(), 0);
        await noOverflow(page);
      }
      assert.deepEqual(errors, []);
      console.log(`Season spacing, review filters, sharing and keyboard: ${width}px passed`);
      await context.close();
    }
  } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode = 1;});
