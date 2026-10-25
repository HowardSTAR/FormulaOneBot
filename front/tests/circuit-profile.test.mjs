import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';

const bundle = await build({ entryPoints: [fileURLToPath(new URL('../src/pages/next-race/circuit-profile.ts', import.meta.url))], bundle: true, write: false, format: 'esm', platform: 'node' });
const { matchingProfile, ratingTone } = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString('base64')}`);

test('automatic profile is bound to the selected season, round and event', () => {
  const profile = { season: 2026, round: 18, eventName: 'United States Grand Prix' };
  const response = { status: 'ok', season: 2026, round: 18, profile };
  assert.equal(matchingProfile(response, 2026, 18, profile.eventName), profile);
  assert.equal(matchingProfile(response, 2025, 18, profile.eventName), null);
  assert.equal(matchingProfile(response, 2026, 19, profile.eventName), null);
  assert.equal(matchingProfile(response, 2026, 18, 'Miami Grand Prix'), null);
  assert.equal(matchingProfile({ ...response, profile: null }, 2026, 18, profile.eventName), null);
  assert.equal(matchingProfile({ ...response, profile: { ...profile, season: 2025 } }, 2026, 18, profile.eventName), null);
});

test('scale thresholds distinguish all five intensities without replacing the numeric value', () => {
  assert.deepEqual([1, 2, 3, 4, 5].map(ratingTone), ['low', 'low', 'medium', 'high', 'high']);
});
