import assert from 'node:assert/strict';
import test from 'node:test';
import {loadTs} from './support/modules.mjs';
const {predictionSummary} = await loadTs(new URL('../src/pages/index/personal-summary.ts',import.meta.url));
const {visitReminders} = await loadTs(new URL('../src/helpers/visitReminders.ts',import.meta.url));
const {reminderClock} = await loadTs(new URL('../src/helpers/reminderClock.ts',import.meta.url));
const now = Date.parse('2026-10-05T12:00:00Z');
const iso = offset => new Date(now+offset).toISOString();
const prediction = {status:'ok',season:2026,round:17,is_open:true,opens_at_utc:iso(-1000),deadline_utc:iso(86400000),prediction:null};
const data = {user_id:1,weekly:null,prediction,week:null};

for (const [name,offset,title,urgent] of [
  ['just-before-urgency',7200001,'Вы ещё не сделали прогноз',false],
  ['urgency-exactly-two-hours',7200000,'Вы ещё не сделали прогноз',true],
  ['one-ms-before-close',1,'Вы ещё не сделали прогноз',true],
  ['at-close',0,'Приём закрыт',false],['after-close',-1,'Приём закрыт',false],
]) test(`prediction summary boundary: ${name}`,()=>{
  assert.deepEqual(predictionSummary({...prediction,deadline_utc:iso(offset)},now),{
    title,urgent,action:offset>0?'Сделать прогноз':'Открыть прогнозы',
  });
});

for (const [name,offset,title] of [
  ['above-one-day',86400001,'Доступен новый прогноз'],
  ['exactly-one-day',86400000,'Не забудь сохранить прогноз'],
  ['one-ms-before-close',1,'Не забудь сохранить прогноз'],['at-close',0,null],['after-close',-1,null],
]) test(`visit prediction boundary: ${name}`,()=>{
  const hints = visitReminders({...data,prediction:{...prediction,deadline_utc:iso(offset)}},[],now);
  assert.equal(hints.length,title?1:0);
  if (title) assert.equal(hints[0].title,title);
});

for (const [name,offset,phase] of [
  ['before-start',-1,'before'],['at-start',0,'live'],['before-end',3599999,'live'],
  ['at-end',3600000,'finished'],['after-end',3600001,'finished'],
]) test(`notification clock boundary: ${name}`,()=>{
  const result = reminderClock({kind:'race',start_utc:iso(0),duration_minutes:60},now+offset);
  assert.equal(result.phase,phase);
  assert.equal(result.estimated,phase!=='before');
});

for (const [name,offset,expected] of [
  ['already-started',0,null],['one-ms-away',1,'Сессия через 1 мин'],
  ['exactly-two-hours',7200000,'Сессия через 2 ч'],
  ['exactly-one-day',86400000,'Сессия через 24 ч'],['beyond-one-day',86400001,null],
]) test(`next session boundary: ${name}`,()=>{
  const hints = visitReminders({...data,prediction:null},[{name:'Сессия',utc_iso:iso(offset)}],now);
  assert.equal(hints.length,expected?1:0);
  if (expected) assert.equal(hints[0].title,expected);
});

test('simultaneous actionable events follow business priority without mutating input',()=>{
  const input = {...data,weekly:{week:'2026-10-05',end:iso(86400000),track_id:'track',name:'Track',time_ms:70000,place:2,alert_id:9,rival:{name:'Fast',time_ms:68000}}};
  const before = structuredClone(input);
  assert.deepEqual(visitReminders(input,[{name:'Race',utc_iso:iso(3600000)}],now).map(hint=>hint.priority),[100,90,80]);
  assert.deepEqual(input,before);
});
