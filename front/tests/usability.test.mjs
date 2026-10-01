import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

async function moduleFrom(relative, transform = source => source) {
  const source = transform(readFileSync(new URL(relative, import.meta.url), 'utf8'));
  const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React}}).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
}
const presentation = await moduleFrom('../src/helpers/presentation.ts');
const {safeReturnPath} = await moduleFrom('../src/helpers/returnPath.ts');
const {notificationBody} = await moduleFrom('../src/helpers/notificationPresentation.ts');
const {describeAuditChange} = await moduleFrom('../src/helpers/adminAudit.ts');
const {readSessionFilters} = await moduleFrom('../src/helpers/sessionFilters.ts', source => source.replace(/^import .*;$/gm, ''));
globalThis.React = React;
const {YearSelect} = await moduleFrom('../src/components/YearSelect.tsx');
const {CustomSelect} = await moduleFrom('../src/components/CustomSelect.tsx', source => source.replace('import { hapticSelection } from "../helpers/telegram";', 'const hapticSelection = () => {};'));

test('missing numeric fields never become zero, NaN or undefined; real zero survives', () => {
  for (const value of [null, undefined, '', ' ', false, 'NaN', Infinity]) assert.equal(presentation.optionalNumber(value), null);
  assert.equal(presentation.optionalNumber(0), 0);
  assert.equal(presentation.optionalNumber('22'), 22);
});
test('countdown starts now, not midnight; invalid and expired dates are safe', () => {
  assert.equal(presentation.daysUntil('2026-10-04T12:00:00Z', Date.parse('2026-10-01T15:00:00Z')), 3);
  assert.equal(presentation.daysUntil('invalid'), null);
  assert.equal(presentation.daysUntil('2000-01-01'), 0);
  assert.equal(presentation.localDateTime(undefined), '—');
  assert.equal(presentation.localDateTime('bad date'), '—');
  assert.match(presentation.timezoneName('Etc/GMT-3'), /UTC\+03:00 · Москва/);
});
test('only obsolete blanket warning is removed after all facts confirmed', () => {
  const note = 'Источник не предоставил статусы сессии; дополнительные факты не подтверждены. Источники расходятся.';
  const items = ['fastest_lap_driver','first_retirement_driver','safety_car'].map(key => ({key, actual: key === 'safety_car' ? 0 : 'RUS', status: 'miss'}));
  assert.equal(presentation.confirmedFactsNote(note, items), 'Источники расходятся.');
  assert.equal(presentation.confirmedFactsNote(note, items.slice(1)), note);
});
test('race link opens requested stage, and explicit latest stays latest', () => {
  assert.deepEqual(readSessionFilters(new URLSearchParams('season=1997&round=4'),1950,2026), {season:1997, selectedRound:4, mode:'archive'});
  assert.equal(readSessionFilters(new URLSearchParams('round=15&mode=latest')).mode, 'latest');
  for (const query of ['season=2000junk&round=3junk','season=-1&round=-5','season=9999&round=999']) assert.equal(readSessionFilters(new URLSearchParams(query),1950,2026).selectedRound, null);
});
test('return after sign in allows only intended local personal routes', () => {
  assert.equal(safeReturnPath('/favorites'), '/favorites');
  assert.equal(safeReturnPath('/voting?season=2026&round=15&evil=https://example.com'), '/voting?season=2026&round=15');
  for (const value of ['https://example.com','//example.com','/admin','/\\example.com',null]) assert.equal(safeReturnPath(value), null);
});
test('legacy all-zero race points are unknown, not silently re-scored', () => {
  const body = Array.from({length:5},(_,i)=>`P${i+1} · Driver ${i} · Team · 0.0`).join('\n');
  const output = notificationBody(body,'/race-results?season=2026&round=15');
  assert.equal(output.uncertainPoints,true);
  assert.ok(output.body.endsWith(' · —'));
  assert.equal(notificationBody(body,'/voting').body,body);
  const withPoints=body.replace('0.0','25');
  assert.equal(notificationBody(withPoints,'/race-results?season=2026').body,withPoints);
});

test('admin audit describes old and new values without exposing raw JSON by default', () => {
  assert.equal(describeAuditChange('user.role_changed', {from:'user', to:'admin'}), 'Было: Участник → стало: Администратор');
  assert.match(describeAuditChange('game_records.user_cleared', {scope:'race', total:3}), /Emerald Loop · удалено записей: 3/);
  assert.equal(describeAuditChange('new.action', {}), 'Подробности доступны в технических сведениях.');
});
test('year and round selectors use labelled native controls with selected values', () => {
  const year=renderToStaticMarkup(React.createElement(YearSelect,{value:1997,minYear:1950,maxYear:2026,onChange:()=>{},ariaLabel:'Сезон'}));
  assert.match(year,/<select[^>]*aria-label="Сезон"/);
  assert.match(year,/<option value="1997" selected="">1997<\/option>/);
  const round=renderToStaticMarkup(React.createElement(CustomSelect,{value:2,options:[{value:1,label:'Первый'},{value:2,label:'Второй'}],onChange:()=>{},ariaLabel:'Этап'}));
  assert.match(round,/<select[^>]*aria-label="Этап"/);
  assert.match(round,/<option value="2" selected="">Второй<\/option>/);
});
