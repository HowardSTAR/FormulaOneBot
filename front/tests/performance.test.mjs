import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

async function sourceModule(name) {
  const source = readFileSync(new URL(`../src/helpers/${name}.ts`, import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
}
const { SingleFlight } = await sourceModule('singleFlight');
const { visibleInterval } = await sourceModule('visibleInterval');
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };

test('simultaneous identical reads share one request, subsequent reads stay fresh', async () => {
  const flight = new SingleFlight(), pending = deferred();
  let calls = 0;
  const request = () => { calls++; return pending.promise; };
  const first = flight.run('same', request), second = flight.run('same', request);
  assert.equal(first, second);
  pending.resolve({ points: 20 });
  assert.deepEqual(await first, { points: 20 });
  assert.equal(calls, 1);
  assert.equal(await flight.run('same', async () => 21), 21);
});

test('different request keys do not mix seasons or identities', async () => {
  const flight = new SingleFlight();
  assert.deepEqual(await Promise.all([
    flight.run('2025:user1', async () => 1), flight.run('2026:user1', async () => 2), flight.run('2026:user2', async () => 3),
  ]), [1, 2, 3]);
});

test('a rejected or synchronously throwing request can be retried', async () => {
  const flight = new SingleFlight();
  await assert.rejects(flight.run('same', async () => { throw new Error('source unavailable'); }));
  assert.equal(await flight.run('same', async () => 2), 2);
  await assert.rejects(flight.run('same', () => { throw new Error('invalid'); }));
  assert.equal(await flight.run('same', async () => 3), 3);
});

test('identity invalidation never reuses an older pending response', async () => {
  const flight = new SingleFlight(), old = deferred(), current = deferred();
  const first = flight.run('same', () => old.promise);
  flight.clear();
  const second = flight.run('same', () => current.promise);
  old.resolve('old user');
  assert.equal(await first, 'old user');
  assert.equal(flight.run('same', async () => 'wrong'), second);
  current.resolve('new user');
  assert.equal(await second, 'new user');
});

function runtime(hidden = false) {
  const listeners = new Map(), timers = new Map();
  let id = 0;
  return {
    document: { hidden, addEventListener: (event, cb) => listeners.set(event, cb), removeEventListener: event => listeners.delete(event) },
    setInterval: (cb, delay) => { timers.set(++id, { cb, delay }); return id; },
    clearInterval: timer => timers.delete(timer),
    listeners, timers,
    change(value) { this.document.hidden = value; listeners.get('visibilitychange')?.(); },
  };
}

test('clock pauses while hidden and catches up once on return', () => {
  const env = runtime(); let ticks = 0;
  const stop = visibleInterval(() => ticks++, 1000, env);
  assert.equal(env.timers.size, 1);
  env.timers.values().next().value.cb();
  assert.equal(ticks, 1);
  env.change(true);
  assert.equal(env.timers.size, 0);
  assert.equal(ticks, 1);
  env.change(false);
  assert.equal(ticks, 2);
  assert.equal(env.timers.size, 1);
  env.change(false);
  assert.equal(env.timers.size, 1); // repeated events never duplicate timers
  stop();
  assert.equal(env.timers.size, 0);
  assert.equal(env.listeners.size, 0);
});

test('initially hidden tabs do not start a timer; unmounted clocks stay stopped', () => {
  const env = runtime(true); let ticks = 0;
  const stop = visibleInterval(() => ticks++, 30000, env);
  assert.equal(env.timers.size, 0);
  env.change(false);
  assert.equal(ticks, 1);
  assert.equal(env.timers.values().next().value.delay, 30000);
  stop(); env.change(false);
  assert.equal(ticks, 1);
  assert.equal(env.timers.size, 0);
});

test('home is eager, every other page is lazy and shell retains a suspense boundary', () => {
  const routes = readFileSync(new URL('../src/router.tsx', import.meta.url), 'utf8');
  assert.match(routes, /import IndexPage from/);
  assert.equal((routes.match(/^import .* from ["']\.\/pages\//gm) || []).length, 1);
  assert.match(routes, /const ComparePage = lazy/);
  assert.match(routes, /const RaceGamePage = lazy/);
  const shell = readFileSync(new URL('../src/components/SwipeBackLayout.tsx', import.meta.url), 'utf8');
  assert.match(shell, /<Suspense[\s\S]*<Outlet\s*\/>[\s\S]*<\/Suspense>/);
});

test('account, calendar and settings use the tested visibility-aware timer', () => {
  for (const page of ['account/AccountPage', 'season/SeasonPage', 'settings/SettingsPage']) {
    const source = readFileSync(new URL(`../src/pages/${page}.tsx`, import.meta.url), 'utf8');
    assert.match(source, /import \{ visibleInterval \}/);
    assert.match(source, /visibleInterval\(/);
    assert.doesNotMatch(source, /window\.setInterval\(/);
  }
});
