import assert from 'node:assert/strict';
import test from 'node:test';
import { loadTs } from './support/modules.mjs';

const { useAuthState, ApiError } = await loadTs(new URL('../src/helpers/auth.ts', import.meta.url), source =>
  `
const useState = initial => globalThis.authHarness.useState(initial);
const useEffect = effect => globalThis.authHarness.useEffect(effect);
const apiRequest = () => globalThis.authHarness.request();
export class ApiError extends Error { constructor(status) { super(); this.status = status; } }
class SingleFlight { run(key, action) { return action(); } clear() {} }
const invalidateApiReads = () => {};
` + source.replace(/^import .*;$/gm, ''));

test('auth state survives network/server errors and clears on a confirmed 401', async () => {
  let state;
  const events = new EventTarget();
  globalThis.window = events;
  let response = { id: 1, role: 'admin', telegram_id: null };
  globalThis.authHarness = {
    useState(initial) { state ??= initial(); return [state, value => { state = typeof value === 'function' ? value(state) : value; }]; },
    useEffect(effect) { effect(); },
    async request() { if (response instanceof Error) throw response; return response; },
  };
  try {
    useAuthState();
    const settle = () => new Promise(resolve => setImmediate(resolve));
    await settle();
    assert.equal(state.signedIn, true);
    for (const error of [new Error('offline'), Object.assign(new Error('unavailable'), { status: 503 })]) {
      response = error;
      events.dispatchEvent(new Event('turbotears-auth-changed'));
      await settle();
      assert.equal(state.signedIn, true);
      assert.equal(state.role, 'admin');
    }
    response = new ApiError(401);
    events.dispatchEvent(new Event('turbotears-auth-changed'));
    await settle();
    assert.equal(state.signedIn, false);
  } finally {
    delete globalThis.window;
    delete globalThis.authHarness;
  }
});
