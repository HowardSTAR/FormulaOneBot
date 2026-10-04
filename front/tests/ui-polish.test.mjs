import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
import postcss from 'postcss';

const source = path => readFileSync(new URL(path, import.meta.url), 'utf8');
const compiled = ts.transpileModule(source('../src/helpers/reminderClock.ts'), {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText;
const {reminderClock, reminderBody} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const start = Date.parse('2026-10-09T12:30:00Z');
const reminder = {kind: 'practice1', start_utc: '2026-10-09T15:30:00+03:00', duration_minutes: 60};

test('notification countdown ticks, includes days, and never goes negative', () => {
  assert.equal(reminderClock(reminder, start-1001).label, 'До старта: 00:00:02');
  assert.equal(reminderClock(reminder, start-1).label, 'До старта: 00:00:01');
  assert.equal(reminderClock(reminder, start-86400000).label, 'До старта: 1 д · 00:00:00');
  assert.equal(reminderClock(reminder, start).label, 'УЖЕ ИДЁТ');
  assert.equal(reminderClock(reminder, start+3599999).phase, 'live');
  assert.equal(reminderClock(reminder, start+3600000).label, 'Сессия прошла');
  assert.equal(reminderClock({...reminder, kind: 'race'}, start+3600000).label, 'Этап прошёл');
  assert.equal(reminderClock(reminder, start).estimated, true);
});
test('legacy and malformed metadata cannot fabricate a start or live status', () => {
  for (const start_utc of [null, 'bad', '']) assert.equal(reminderClock({...reminder, start_utc}, start).phase, 'unknown');
  assert.equal(reminderClock({...reminder, duration_minutes: NaN}, start).phase, 'unknown');
});
test('reminder presentation removes stale countdown but retains event and date', () => {
  const output = reminderBody('🏎 Скоро свободные заезды — FP2!\n\nЧерез 59 мин. старт: Bahrain Grand Prix\n📍 Сахир\nНачало в 11:00');
  assert.ok(!output.includes('59 мин.'));
  assert.match(output, /Bahrain Grand Prix/);
  assert.match(output, /Начало в 11:00/);
  assert.equal(reminderBody('38 минут назад старт: Race'), 'Race');
  assert.equal(reminderBody('Уже завтра старт: Race'), 'Race');
  assert.equal(reminderBody('УЖЕ ИДЁТ старт: Race'), 'Race');
});
test('receipt is below page content, scoped to route and excludes auxiliary requests', () => {
  const layout = source('../src/components/SwipeBackLayout.tsx');
  assert.ok(layout.indexOf('<DataReceipt />') > layout.indexOf('<Outlet />'));
  assert.match(source('../src/components/DataReceipt.tsx'), /receipt\?\.route !== route/);
  const api = source('../src/helpers/api.ts');
  assert.match(api, /requestedRoute/);
  assert.match(api, /method === 'GET'/);
  for (const page of ['drivers/DriversPage', 'constructors/ConstructorsPage']) assert.ok(!source(`../src/pages/${page}.tsx`).includes('время обновления источника'));
});
test('calendar filters keep receipt, but another season or race does not', async () => {
  const compiled = ts.transpileModule(source('../src/helpers/dataReceipt.ts'), {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText;
  const {dataReceiptKey} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
  assert.equal(dataReceiptKey('/season', '?filter=past&round=15'), dataReceiptKey('/season', ''));
  assert.notEqual(dataReceiptKey('/season', '?year=1997'), dataReceiptKey('/season', ''));
  assert.notEqual(dataReceiptKey('/race-details', '?season=2026&round=16'), dataReceiptKey('/race-details', '?season=2026&round=17'));
});
test('calendar action downloads the whole weekend directly without a site dialog', () => {
  const component = source('../src/components/CalendarDownload.tsx');
  assert.ok(!component.includes('<dialog'));
  assert.match(component, /\/api\/calendar\/weekend\.ics/);
  assert.ok(!component.includes('data:text/calendar'));
  assert.match(component, /Импорт нужно подтвердить/);
  assert.match(component, /Скачать весь этап/);
});
test('shared buttons and compact layout are eager, no fixed card heights', () => {
  assert.match(source('../src/App.tsx'), /ui-polish\.css/);
  const css = source('../src/assets/ui-polish.css');
  postcss.parse(css);
  assert.match(css, /min-height: 44px/);
  assert.match(css, /index-hero-wrap > \.personal-home \{ margin-top: 16px/);
  assert.match(css, /session-row \{ display: grid; grid-template-columns: minmax\(0, 1fr\) auto;/);
});
