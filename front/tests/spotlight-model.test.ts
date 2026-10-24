import test from 'node:test';
import assert from 'node:assert/strict';
import { spotlightSlots } from '../src/pages/index/spotlight-model.ts';
const drivers = [{ code: 'NOR', name: 'Lando Norris', points: 0 }, { code: 'PIA', name: 'Oscar Piastri', points: 100 }, { code: 'RUS', name: 'George Russell', points: 90 }];
const teams = [{ name: 'McLaren', constructorId: 'mclaren' }, { name: 'Mercedes', constructorId: 'mercedes' }];
test('saved favorites keep their order and the two-driver limit', () => {
  const result = spotlightSlots(drivers, teams, { drivers: ['pia', 'NOR', 'RUS'], teams: ['Mercedes'] });
  assert.deepEqual(result.map(slot => slot.entry?.name), ['Oscar Piastri', 'Lando Norris', 'Mercedes']);
  assert.ok(result.every(slot => slot.favorite));
  assert.equal(result[1].entry?.points, 0);
});
test('unknown saved favorites do not silently turn into season leaders', () => {
  const result = spotlightSlots(drivers, teams, { drivers: ['OLD'], teams: ['Old Team'] });
  assert.deepEqual(result.map(slot => slot.entry), [null, null, null]);
  assert.equal(result[0].unavailable, true);
  assert.equal(result[1].favorite, false);
  assert.equal(result[2].unavailable, true);
});
test('empty favorites show available leaders without marking them as favorites', () => {
  const result = spotlightSlots(drivers, teams, { drivers: [], teams: [] });
  assert.deepEqual(result.map(slot => slot.entry?.name), ['Lando Norris', 'Oscar Piastri', 'McLaren']);
  assert.ok(result.every(slot => !slot.favorite));
  assert.deepEqual(spotlightSlots([], [], { drivers: [], teams: [] }).map(slot => slot.entry), [null, null, null]);
});
test('team selections resolve by either identity or display name', () => {
  assert.equal(spotlightSlots(drivers, teams, { drivers: [], teams: ['MERCEDES'] })[2].entry, teams[1]);
});
