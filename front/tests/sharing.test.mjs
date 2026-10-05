import assert from 'node:assert/strict';
import test from 'node:test';
import {loadTs} from './support/modules.mjs';
// Replace just the HTTP boundary; exercise real helper logic without a browser or Telegram.
const {validShareToken, rememberInvitation, pendingInvitation, sendCard} = await loadTs(new URL('../src/helpers/sharing.ts',import.meta.url),
  source=>source.replace("import { apiRequest } from './api';", 'const apiRequest = (...args) => globalThis.qaSharingRequest(...args);'));

const token = 'a'.repeat(32);
const card = {token, share_url: 'https://t.me/example_bot?startapp=share_' + token, web_url: 'https://f1hub.ru/share/' + token, title:'Мой прогноз', headline:'27 / 37 очков'};
function setup(telegram) {
  const calls = [], opened = [], items = new Map();
  globalThis.window = {Telegram: telegram ? {WebApp: telegram} : undefined, open: (...args) => opened.push(args)};
  globalThis.localStorage = {getItem:key=>items.get(key) ?? null, setItem:(key,value)=>items.set(key,value)};
  globalThis.qaSharingRequest = async (...args) => {calls.push(args); return {id:'prepared-test-id'};};
  return {calls, opened, items};
}

test('only bounded opaque tokens are accepted; first invitation wins until expiry', () => {
  const {items} = setup();
  assert.ok(validShareToken(token));
  assert.ok(!validShareToken(token + '?redirect=evil'));
  assert.ok(!validShareToken('../etc'));
  rememberInvitation(token); rememberInvitation('b'.repeat(32));
  assert.equal(pendingInvitation(), token);
  items.set('f1hub-pending-invitation', JSON.stringify({token, expires:Date.now()-1}));
  assert.equal(pendingInvitation(), null);
  rememberInvitation('b'.repeat(32));
  assert.equal(pendingInvitation(), 'b'.repeat(32));
});
test('denied storage does not break invitation navigation', () => {
  setup(); globalThis.localStorage = {getItem:()=>{throw Error('denied');}};
  assert.doesNotThrow(() => rememberInvitation(token));
  assert.equal(pendingInvitation(), null);
});
test('native Telegram send is user-controlled; only confirmed send records sent', async () => {
  const {calls, opened} = setup({initData:'signed', isVersionAtLeast:()=>true, shareMessage:(id,done)=>{assert.equal(id,'prepared-test-id');done(true);}});
  assert.equal(await sendCard(card), 'sent');
  assert.equal(calls[0][0], `/api/engagement/shares/${token}/telegram`);
  assert.equal(calls[1][1].event, 'share_sent');
  assert.equal(opened.length,0);
});
test('cancelled native dialog is not an invitation sent or an automatic fallback', async () => {
  const {calls, opened} = setup({initData:'signed', isVersionAtLeast:()=>true, shareMessage:(_id,done)=>done(false)});
  assert.equal(await sendCard(card), 'cancelled');
  assert.equal(calls.length,1); assert.equal(opened.length,0);
});
test('browser and old Telegram fallback record an opened dialog, never a confirmed send', async () => {
  const {calls, opened} = setup();
  assert.equal(await sendCard(card), 'opened');
  assert.equal(new URL(opened[0][0]).searchParams.get('url'), card.web_url);
  assert.equal(opened[0][2], 'noopener,noreferrer');
  assert.equal(calls[0][1].event, 'share_opened');
});
test('failed photo preparation reports an error without silently sending a bare link', async () => {
  const {opened} = setup({initData:'signed', isVersionAtLeast:()=>true, shareMessage:()=>assert.fail('not prepared')});
  globalThis.qaSharingRequest = async (...args) => {if(args[0].endsWith('/telegram')) throw Error('not configured');return {};};
  await assert.rejects(sendCard(card), /not configured/); assert.equal(opened.length,0);
});

test('browser file sharing includes the card image and preserves cancellation', async () => {
  const {calls, opened} = setup();
  const image = new File(['photo'], 'f1hub-card.jpg', {type: 'image/jpeg'});
  Object.defineProperty(globalThis, 'navigator', {configurable: true, value: {
    canShare: ({files}) => files[0] === image,
    share: async data => { assert.deepEqual(data.files, [image]); assert.ok(data.text.includes(card.web_url)); },
  }});
  assert.equal(await sendCard(card, image), 'sent');
  assert.equal(calls[0][1].event, 'share_sent'); assert.equal(opened.length, 0);
  navigator.share = async () => {throw new DOMException('Cancelled', 'AbortError');};
  assert.equal(await sendCard(card, image), 'cancelled');
  assert.equal(calls.length, 1); assert.equal(opened.length, 0);
});
