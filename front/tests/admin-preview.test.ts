import assert from 'node:assert/strict';
import test from 'node:test';
import { adminPreview } from './fixtures/admin.ts';

const users = new URL('http://preview.test/api/admin/users?role=all');
const emailUrl = new URL('http://preview.test/api/admin/users/42/email');
const save = { method: 'PATCH', body: JSON.stringify({ email: 'changed@example.test' }) };

test('failed preview save preserves the old email; retry updates only the fixture', async () => {
  const request = adminPreview(new URLSearchParams('state=admin-save-error'));
  assert.equal((await request(emailUrl, save))?.status, 503);
  assert.equal((await (await request(users))!.json()).items[0].email, 'alex@example.test');
  assert.equal((await request(emailUrl, save))?.status, 200);
  assert.equal((await (await request(users))!.json()).items[0].email, 'changed@example.test');
  const fresh = adminPreview(new URLSearchParams());
  assert.equal((await (await fresh(users))!.json()).items[0].email, 'alex@example.test');
});

test('destructive preview actions remain blocked and non-admin requests fall through', async () => {
  const request = adminPreview(new URLSearchParams());
  assert.equal((await request(new URL('http://preview.test/api/admin/game-records/all'), { method: 'DELETE' }))?.status, 403);
  assert.equal(await request(new URL('http://preview.test/api/race-results')), null);
});
