import assert from 'node:assert/strict';
import test from 'node:test';
import {loadTs} from './support/modules.mjs';
const {visitReminders,reminderAllowed,dismissReminder} = await loadTs(new URL('../src/helpers/visitReminders.ts',import.meta.url));
const now = Date.parse('2026-10-05T12:00:00Z');
const data = {user_id:1,weekly:null,prediction:null,week:{track_id:'track',name:'Track',start:'2026-10-05T00:00:00Z',end:'2026-10-12T00:00:00Z'}};
const prediction = {status:'ok',season:2026,round:17,event_name:'Test GP',is_open:true,prediction:null,opens_at_utc:'2026-10-05T00:00:00Z',deadline_utc:'2026-10-10T00:00:00Z'};

test('new forecast and urgent missing forecast have different reminders; saved, closed and unopened do not nag',()=>{
  const first = visitReminders({...data,prediction},[],now)[0];
  assert.equal(first.title,'Доступен новый прогноз');
  assert.equal(visitReminders({...data,prediction},[],Date.parse('2026-10-09T12:00:00Z'))[0].title,'Не забудь сохранить прогноз');
  for (const patch of [{prediction:{}},{is_open:false},{deadline_utc:'bad'},{deadline_utc:'2026-10-04T00:00:00Z'},{opens_at_utc:'2026-10-06T00:00:00Z'}]) {
    assert.ok(!visitReminders({...data,prediction:{...prediction,...patch}},[],now).some(item=>item.to==='/predictions'));
  }
});
test('actual overtake has priority, ties/reclaimed/expired alerts are absent',()=>{
  const weekly={week:'2026-10-05',end:data.week.end,track_id:'track',name:'Track',time_ms:70000,place:2,alert_id:9,rival:{name:'Fast',time_ms:68000}};
  assert.equal(visitReminders({...data,weekly,prediction},[{name:'Race',utc_iso:'2026-10-05T13:00:00Z'}],now)[0].id,'overtaken:2026-10-05:9');
  for (const patch of [{alert_id:null},{rival:null},{end:'2026-10-04T00:00:00Z'}]) {
    assert.ok(!visitReminders({...data,weekly:{...weekly,...patch}},[],now).some(item=>item.id.startsWith('overtaken:')));
  }
});
test('only upcoming timestamped sessions show countdown; new week disappears after racing or two days',()=>{
  const sessions=[{name:'Old',utc_iso:'2026-10-04T13:00:00Z'},{name:'Race',utc_iso:'2026-10-05T13:00:00Z'},{name:'Unknown',utc_iso:'2026-10-05T12:30:00'}];
  assert.equal(visitReminders(data,sessions,now)[0].title,'Race через 1 ч');
  assert.ok(!visitReminders(data,sessions,now+86400000).some(item=>item.to==='/next-race'));
  assert.ok(!visitReminders(data,[],now+172800000).some(item=>item.id.startsWith('new-week')));
  assert.ok(!visitReminders({...data,weekly:{}},[],now).some(item=>item.id.startsWith('new-week')));
});
test('dismissal survives reload, is isolated by account, and expires; denied storage still works',t=>{
  const before = {session: Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage'), local: Object.getOwnPropertyDescriptor(globalThis, 'localStorage')};
  t.after(()=>{
    for (const [key, descriptor] of [['sessionStorage', before.session], ['localStorage', before.local]]) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key];
    }
  });
  const session = new Map(), local = new Map();
  globalThis.sessionStorage={getItem:key=>session.get(key),setItem:(key,value)=>session.set(key,value)};
  globalThis.localStorage={getItem:key=>local.get(key),setItem:(key,value)=>local.set(key,value)};
  const item = visitReminders(data,[],now)[0];
  assert.ok(reminderAllowed(item,1,now));
  dismissReminder(item,1,now);
  assert.equal(reminderAllowed(item,1,now),false);
  assert.ok(reminderAllowed(item,2,now));
  session.clear();
  assert.equal(reminderAllowed(item,1,now),false);
  assert.ok(reminderAllowed(item,1,now+86400001));
  globalThis.sessionStorage={getItem:()=>{throw Error('denied')},setItem:()=>{throw Error('denied')}};
  assert.doesNotThrow(()=>dismissReminder(item,1,now));
  assert.ok(reminderAllowed(item,1,now));
});
