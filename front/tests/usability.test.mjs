import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { posix } from 'node:path';
import {loadTs} from './support/modules.mjs';
import postcss from 'postcss';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

async function moduleFrom(relative, transform = source => source) {
  return loadTs(new URL(relative,import.meta.url),transform);
}
const presentation = await moduleFrom('../src/helpers/presentation.ts');
const {safeReturnPath} = await moduleFrom('../src/helpers/returnPath.ts');
const {notificationBody} = await moduleFrom('../src/helpers/notificationPresentation.ts');
const {describeAuditChange} = await moduleFrom('../src/helpers/adminAudit.ts');
const {readSessionFilters} = await moduleFrom('../src/helpers/sessionFilters.ts', source => source.replace(/^import .*;$/gm, ''));
const calendar = await moduleFrom('../src/helpers/seasonCalendar.ts');
const {calendarText} = await moduleFrom('../src/helpers/calendar.ts');

test('downloaded sessions cover their full calendar window in UTC', () => {
  for (const [title, end] of [['Гонка', '20261010T013000Z'], ['Квалификация', '20261010T000000Z'], ['Спринт-квалификация', '20261009T233000Z']]) {
    const text = calendarText(title, '2026-10-10T01:30:00+03:00', 'https://example.test/season');
    assert.match(text, /DTSTART:20261009T223000Z/);
    assert.ok(text.includes(`DTEND:${end}`));
    assert.match(text.replace(/\r\n /g, ''), /окончания ориентировочное/);
  }
  assert.equal(calendarText('Гонка', 'bad', ''), null);
});
globalThis.React = React;
const {CustomSelect, SelectField} = await moduleFrom('../src/components/CustomSelect.tsx', source => source.replace(/^import .*;$/gm, '') + '\nconst {Children, isValidElement, useId, useLayoutEffect, useRef, useState} = globalThis.React; const hapticSelection = () => {};');
globalThis.SelectField = SelectField;
const {YearSelect} = await moduleFrom('../src/components/YearSelect.tsx', source => source.replace(/^import .*;$/gm, 'const SelectField = globalThis.SelectField;'));

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

test('fixed timezone choices include places and keep the original UTC offsets', () => {
  const options = presentation.FIXED_TIMEZONE_OPTIONS;
  assert.equal(options.length, 25);
  for (const [index, option] of options.entries()) {
    const hours = index - 12;
    const value = hours === 0 ? 'UTC' : `Etc/GMT${hours < 0 ? '+' : '-'}${Math.abs(hours)}`;
    assert.equal(option.value, value);
    assert.match(option.label, /^UTC[+-]\d{2}:00 · .+/);
  }
  assert.match(presentation.timezoneName('UTC'), /Рейкьявик/);
  assert.match(presentation.timezoneName('Europe/Moscow'), /UTC\+03:00 · Москва/);
  assert.equal(presentation.timezoneName('Invalid/Zone'), 'Invalid/Zone');
});

test('city examples match their fixed offset throughout the year', () => {
  const cityZones = [
    'Pacific/Pago_Pago', 'Pacific/Honolulu', 'Pacific/Gambier', 'Pacific/Pitcairn',
    'America/Phoenix', 'America/Guatemala', 'America/Bogota', 'America/Santo_Domingo',
    'America/Argentina/Buenos_Aires', 'America/Noronha', 'Atlantic/Cape_Verde',
    'Atlantic/Reykjavik', 'Africa/Lagos', 'Africa/Johannesburg', 'Europe/Moscow',
    'Asia/Dubai', 'Asia/Tashkent', 'Asia/Dhaka', 'Asia/Bangkok', 'Asia/Shanghai',
    'Asia/Tokyo', 'Asia/Vladivostok', 'Asia/Magadan', 'Pacific/Fiji',
  ];
  const offset = (zone, date) => new Intl.DateTimeFormat('en', { timeZone: zone, timeZoneName: 'longOffset' })
    .formatToParts(date).find(part => part.type === 'timeZoneName').value;
  for (const [index, cityZone] of cityZones.entries()) {
    for (let month = 0; month < 12; month++) {
      const date = new Date(Date.UTC(2026, month, 15, 12));
      assert.equal(offset(cityZone, date), offset(presentation.FIXED_TIMEZONE_OPTIONS[index + 1].value, date), cityZone);
    }
  }
});
test('only obsolete blanket warning is removed after all facts confirmed', () => {
  const note = 'Источник не предоставил статусы сессии; дополнительные факты не подтверждены. Источники расходятся.';
  const items = ['fastest_lap_driver','first_retirement_driver','safety_car'].map(key => ({key, actual: key === 'safety_car' ? 0 : 'RUS', status: 'miss'}));
  assert.equal(presentation.confirmedFactsNote(note, items), 'Источники расходятся.');
  assert.equal(presentation.confirmedFactsNote(note, items.map(item => ({...item, status: 'unknown'}))), 'Источники расходятся.');
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
test('year and round selectors expose labelled comboboxes and selected options', () => {
  const year=renderToStaticMarkup(React.createElement(YearSelect,{value:1997,minYear:1950,maxYear:2026,onChange:()=>{},ariaLabel:'Сезон'}));
  assert.match(year,/role="combobox" aria-label="Сезон"/);
  assert.match(year,/role="option" aria-selected="true"[^>]*>1997<\/div>/);
  assert.ok(!year.includes('<select'));
  const round=renderToStaticMarkup(React.createElement(CustomSelect,{value:2,options:[{value:1,label:'Первый'},{value:2,label:'Второй'}],onChange:()=>{},ariaLabel:'Этап'}));
  assert.match(round,/role="combobox" aria-label="Этап"/);
  assert.match(round,/role="option" aria-selected="true"[^>]*>Второй<\/div>/);
  assert.ok(!round.includes('<select'));
});

test('Docker frontend build includes the legal registers at their resolved import paths', () => {
  const dockerfile = readFileSync(new URL('../../Dockerfile', import.meta.url), 'utf8');
  const stage = dockerfile.split(/^FROM .+ AS front-builder\r?$/m)[1]?.split(/^FROM /m)[0];
  assert.ok(stage, 'frontend builder stage must exist');
  assert.match(stage, /^WORKDIR \/front\r?$/m);
  const source = readFileSync(new URL('../src/pages/legal/LicenseRegisterPage.tsx', import.meta.url), 'utf8');
  const imports = [...source.matchAll(/from ['"]([^'"]+\.md)\?raw['"]/g)].map(match => match[1]);
  assert.equal(imports.length, 2);
  const copies = [...stage.matchAll(/^COPY (?!\s*--)(.+)\r?$/gm)].map(match => match[1].trim().split(/\s+/));
  for (const relative of imports) {
    const filename = posix.basename(relative);
    assert.ok(readFileSync(new URL(relative, new URL('../src/pages/legal/LicenseRegisterPage.tsx', import.meta.url))).length);
    const expected = posix.resolve('/front/src/pages/legal', relative);
    assert.ok(copies.some(parts => parts.slice(0, -1).includes(filename)
      && posix.resolve('/front', parts.at(-1), filename) === expected),
    `${filename} must be copied to ${expected} in the frontend builder`);
  }
});

test('calendar URL accepts bounded years and rounds and retains the requested filter', () => {
  assert.deepEqual(calendar.readCalendarQuery(new URLSearchParams('year=1997&round=4&filter=past'),2026), {year:1997,round:4,filter:'past'});
  assert.deepEqual(calendar.readCalendarQuery(new URLSearchParams('year=1997junk&round=0&filter=bad'),2026), {year:2026,round:null,filter:'upcoming'});
  assert.equal(calendar.readCalendarQuery(new URLSearchParams('year=1997'),2026).filter,'all');
  assert.equal(calendar.readCalendarQuery(new URLSearchParams('year=2027&round=41'),2026).year,2026);
});

const calendarRace = (round, start, extra={}) => ({round,event_name:`Race ${round}`,location:'Test',date:start?.slice(0,10) ?? '',race_start_utc:start,...extra});
test('calendar distinguishes an active weekend from a race and ages out recent results', () => {
  const past=calendarRace(15,'2026-09-26T11:00:00Z');
  const next=calendarRace(16,'2026-10-04T14:00:00Z',{practice1_start_utc:'2026-10-02T10:00:00Z'});
  let state=calendar.calendarState([past,next],2026,Date.parse('2026-10-02T12:00:00Z'),15);
  assert.equal(state.statusByRound.get(15),'finished');
  assert.equal(state.statusByRound.get(16),'weekend');
  assert.equal(state.nextRound,16);
  state=calendar.calendarState([past,next],2026,Date.parse('2026-10-04T15:00:00Z'));
  assert.equal(state.statusByRound.get(16),'live');
  state=calendar.calendarState([past,next],2026,Date.parse('2026-10-04T19:00:00Z'));
  assert.equal(state.statusByRound.get(16),'pending');
  assert.deepEqual(calendar.filteredCalendar([past,next],state.statusByRound,'past').map(r=>r.round),[15,16]);
  assert.equal(calendar.filteredCalendar([past,next],state.statusByRound,'upcoming').length,0);
  assert.equal(calendar.calendarState([past,next],2026,Date.parse('2026-10-04T16:00:00Z'),16).statusByRound.get(16),'recent');
});
test('calendar cancelled stages never replace the next race or count as completed', () => {
  const races=[calendarRace(1,'2026-03-01T12:00:00Z'),calendarRace(2,'2026-03-08T12:00:00Z',{is_cancelled:true}),calendarRace(3,'2026-03-15T12:00:00Z')];
  const state=calendar.calendarState(races,2026,Date.parse('2026-03-10T12:00:00Z'));
  assert.equal(state.nextRound,3);
  assert.deepEqual(calendar.filteredCalendar(races,state.statusByRound,'past').map(r=>r.round),[1]);
  assert.equal(calendar.filteredCalendar(races,state.statusByRound,'all').length,3);
  assert.deepEqual(calendar.calendarResultLinks(races[1],2026,Date.now(),'cancelled'),[]);
});
test('calendar selection prefers the latest past race and respects deep links', () => {
  const races=[calendarRace(1,'2026-03-01T12:00:00Z'),calendarRace(2,'2026-03-08T12:00:00Z')];
  const statuses=calendar.calendarState(races,2026,Date.parse('2026-03-10T12:00:00Z')).statusByRound;
  assert.equal(calendar.selectedCalendarRace(races,null,'past',statuses).round,2);
  assert.equal(calendar.selectedCalendarRace(races,1,'past',statuses).round,1);
  assert.equal(calendar.selectedCalendarRace([],1,'past',statuses),null);
});
test('calendar dates respect real session times but date-only archives do not shift by timezone', () => {
  const race=calendarRace(1,'2026-11-22T06:00:00Z');
  assert.equal(calendar.raceDateParts(race,'America/Los_Angeles').day,'21');
  assert.equal(calendar.raceDateParts({...race,race_start_utc:null},'America/Los_Angeles').day,'22');
  assert.equal(calendar.raceDateParts({...race,race_start_utc:null,date:'bad'},'UTC').label,'Дата уточняется');
  assert.equal(calendar.calendarState([calendarRace(1,null)],2026,Date.parse('2026-03-10T12:00:00Z')).statusByRound.get(1),'unknown');
});
test('calendar shows practices and only links to sessions that have started', () => {
  const race=calendarRace(16,'2026-10-04T14:00:00Z',{practice1_start_utc:'2026-10-02T10:00:00Z',practice2_start_utc:'2026-10-02T14:00:00Z',practice3_start_utc:'2026-10-03T10:00:00Z',quali_start_utc:'2026-10-03T14:00:00Z'});
  assert.equal(calendar.raceSessions(race).length,5);
  assert.deepEqual(calendar.calendarResultLinks(race,2026,Date.parse('2026-10-02T12:00:00Z'),'weekend'),[]);
  const links=calendar.calendarResultLinks(race,2026,Date.parse('2026-10-03T15:00:00Z'),'weekend');
  assert.deepEqual(links.map(link=>link.key),['quali']);
  assert.match(links[0].href,/season=2026&round=16$/);
});

test('calendar uses one accessible header and mounts details only when expanded', () => {
  const source=readFileSync(new URL('../src/pages/season/SeasonPage.tsx',import.meta.url),'utf8');
  assert.equal((source.match(/<h1\b/g)||[]).length,1);
  assert.match(source,/ariaLabel="Сезон календаря"/);
  assert.match(source,/areFactsExpanded && <div/);
  assert.match(source,/isExpanded && renderPodium/);
  assert.match(source,/PageFeedback message=\{error\} retry=/);
  assert.match(source,/request !== calendarRequest.current/);
  assert.match(source,/<GlossaryText>\{session.label\}<\/GlossaryText>/);
  const styles=readFileSync(new URL('../src/pages/season/season-filters.css',import.meta.url),'utf8');
  assert.match(styles,/header\.season-page-head \.page-head-controls \{ display: flex !important/);
  assert.doesNotMatch(source,/desktopFactTitles|ТОЛЬКО ЧТО|"LIVE"/);
});

const consistencySource = readFileSync(new URL('../src/assets/ui-consistency.css', import.meta.url), 'utf8');
const consistency = postcss.parse(consistencySource);
const cssRule = selector => consistency.nodes.find(node => node.type === 'rule' && node.selector === selector);
const cssValue = (rule, property) => rule?.nodes.find(node => node.type === 'decl' && node.prop === property)?.value;

test('shared dropdown styling is eager and explicitly styles popup items, not just the trigger', () => {
  const app=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
  assert.match(app,/import "\.\/assets\/ui-consistency.css"/);
  assert.equal(cssValue(cssRule('#root select'),'color-scheme'),'dark');
  assert.equal(cssValue(cssRule('#root select'),'min-height'),'48px');
  const options = consistency.nodes.find(node => node.type === 'rule' && node.selector === '#root select option,\n#root select optgroup');
  assert.equal(cssValue(options,'color'),'var(--ui-select-text)');
  assert.equal(cssValue(options,'background-color'),'var(--ui-select-menu-bg)');
  assert.match(consistencySource,/@media \(forced-colors: active\)/);
  assert.match(consistencySource,/#root select:disabled,\s*#root select option:disabled/);
});

test('peer cards stretch by row across public and administrative sections without fixed heights', () => {
  const rows=consistency.nodes.filter(node => node.type === 'rule' && node.selector.includes('.ui-equal-card-row'));
  assert.equal(rows.length,2);
  assert.equal(cssValue(rows[0],'align-items'),'stretch');
  assert.equal(cssValue(rows[1],'align-self'),'stretch');
  assert.equal(cssValue(rows[1],'box-sizing'),'border-box');
  for (const group of ['season-desktop-facts-grid','season-desktop-stats','next-race-desktop-stats','driver-stats-grid',
    'compare-facts-grid','prediction-grid','settings-fields-grid','account-grid','community-grid','wiki-grid',
    'pa-scenarios','admin-metric-grid','at-columns','control-metrics']) {
    for (const rule of rows) assert.ok(rule.selector.includes(`.${group}`),group);
  }
  for (const rule of rows) {
    for (const prop of ['height','max-height','grid-auto-rows','overflow']) assert.equal(cssValue(rule,prop),undefined);
  }
});

test('dropdown text has sufficient contrast on both closed and open backgrounds', () => {
  const tokens=cssRule(':root');
  const luminance = hex => {
    const [r,g,b]=hex.slice(1).match(/.{2}/g).map(value=>parseInt(value,16)/255)
      .map(value=>value <= .04045 ? value/12.92 : ((value+.055)/1.055)**2.4);
    return .2126*r+.7152*g+.0722*b;
  };
  const foreground=luminance(cssValue(tokens,'--ui-select-text'));
  for (const background of ['--ui-select-bg','--ui-select-menu-bg']) {
    assert.ok((foreground+.05)/(luminance(cssValue(tokens,background))+.05) >= 4.5,background);
  }
});
