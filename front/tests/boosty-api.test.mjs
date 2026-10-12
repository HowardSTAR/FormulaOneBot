import test from 'node:test';
import assert from 'node:assert/strict';
import { loadTs } from './support/modules.mjs';

const apiModule = `data:text/javascript,${encodeURIComponent(`
  export class ApiError extends Error {
    constructor(message, status) { super(message); this.status = status; }
  }
  export const apiRequest = (...args) => globalThis.boostyRequestMock(...args);
`)}`;
const { ApiError } = await import(apiModule);
const { checkBoostySubscription } = await loadTs(new URL('../src/helpers/boostyApi.ts', import.meta.url),
  source => source.replace("from './api'", `from '${apiModule}'`));

test.afterEach(() => { delete globalThis.boostyRequestMock; });

test('successful check returns current status without another read', async () => {
  const calls = [];
  const status = { active: true, check_failed: false };
  globalThis.boostyRequestMock = async (...args) => { calls.push(args); return status; };
  assert.equal(await checkBoostySubscription(), status);
  assert.deepEqual(calls, [['/api/account/boosty/check', {}, 'POST', 120000]]);
});

test('upstream failure reads the retained status and reconnect category', async () => {
  const calls = [];
  const status = { active: true, check_failed: true, check_error_code: 'auth_required' };
  globalThis.boostyRequestMock = async endpoint => {
    calls.push(endpoint);
    if (endpoint.endsWith('/check')) throw new ApiError('generic error', 503);
    return status;
  };
  assert.equal(await checkBoostySubscription(), status);
  assert.deepEqual(calls, ['/api/account/boosty/check', '/api/account/boosty']);
});

for (const status of [401, 403, 500, 0]) {
  test(`HTTP ${status} is not masked by a saved status`, async () => {
    const error = new ApiError('original error', status);
    let calls = 0;
    globalThis.boostyRequestMock = async () => { calls++; throw error; };
    await assert.rejects(checkBoostySubscription(), value => value === error);
    assert.equal(calls, 1);
  });
}

for (const readFails of [true, false]) {
  test(`failed check preserves its error when status ${readFails ? 'cannot be read' : 'has no upstream failure'}`, async () => {
    const error = new ApiError('original error', 503);
    globalThis.boostyRequestMock = async endpoint => {
      if (endpoint.endsWith('/check')) throw error;
      if (readFails) throw new Error('status read failed');
      return { check_failed: false };
    };
    await assert.rejects(checkBoostySubscription(), value => value === error);
  });
}
