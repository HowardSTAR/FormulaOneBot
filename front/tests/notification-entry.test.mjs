import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import ts from 'typescript';

async function tracker() {
  const calls = [];
  let fail = false;
  const mock = async (...args) => {
    calls.push(args);
    if (fail) throw new Error('Response lost');
    return {ok:true};
  };
  const key = 'notificationEntryTest'+Math.random();
  const source = readFileSync(new URL('../src/helpers/notificationEntry.ts', import.meta.url), 'utf8')
    .replace("import { apiRequest } from './api';", `const apiRequest = globalThis[${JSON.stringify(key)}];`);
  globalThis[key] = mock;
  try {
    const compiled = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.ESNext, target:ts.ScriptTarget.ES2022}}).outputText;
    const module = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
    return {track:module.trackNotificationEntry, calls, setFailure:value=>{fail=value;}};
  } finally {delete globalThis[key];}
}

test('an opening counts once under effect replay, while a second opening counts again', async () => {
  const {track, calls} = await tracker();
  const token = 'a'.repeat(32);
  const first = track(token, '/predictions', 'opening-1');
  assert.equal(first, track(token, '/predictions', 'opening-1'));
  assert.equal(await first, true);
  await track(token, '/predictions', 'opening-1');
  assert.equal(calls.length, 1);
  await track(token, '/predictions', 'opening-2');
  assert.equal(calls.length, 2);
  assert.notEqual(calls[0][1].event_id, calls[1][1].event_id);
  assert.deepEqual(calls[0].slice(2), ['POST', 5000]);
});

test('lost response can retry with the same event ID so the server deduplicates it', async () => {
  const {track, calls, setFailure} = await tracker();
  setFailure(true);
  assert.equal(await track('b'.repeat(32), '/community', 'opening-1'), false);
  setFailure(false);
  assert.equal(await track('b'.repeat(32), '/community', 'opening-1'), true);
  assert.equal(calls.length, 2);
  assert.equal(calls[0][1].event_id, calls[1][1].event_id);
});

test('invalid tokens and unrelated pages never send an attribution request', async () => {
  const {track, calls} = await tracker();
  for (const token of ['', 'a'.repeat(31), 'a'.repeat(33), '/'.repeat(32)]) {
    assert.equal(await track(token, '/community', 'opening'), false);
  }
  assert.equal(await track('c'.repeat(32), '/admin', 'opening'), false);
  assert.equal(calls.length, 0);
});
