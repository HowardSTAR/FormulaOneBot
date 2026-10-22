import assert from 'node:assert/strict';
import test from 'node:test';
import { loadTs } from './support/modules.mjs';
const { stageSelection, sessionStart, sortedWeekend, availableResults, sessionResultsPath } = await loadTs(new URL('../src/pages/next-race/weekend-model.ts', import.meta.url));

test('weekend links preserve valid archives and reject partial or malformed selections', () => {
  assert.deepEqual(stageSelection(null, null), { kind: 'next' });
  assert.deepEqual(stageSelection('1997', '4'), { kind: 'selected', season: 1997, round: 4 });
  for (const [season, round] of [['2026', null], [null, '4'], ['2026x', '4'], ['1949', '1'], ['2101', '1'], ['2026', '0'], ['2026', '31'], ['2026', '1.0']]) assert.deepEqual(stageSelection(season, round), { kind: 'invalid' });
});
test('untimed sessions remain visible but cannot fabricate result availability', () => {
  const sessions = [{ name: 'Гонка', utc_iso: '2026-10-25T20:00:00Z' }, { name: 'Практика 1', utc_iso: 'bad' }, { name: 'Спринт', utc_iso: '2026-10-24T17:00:00Z' }];
  assert.equal(sortedWeekend(sessions).at(-1).name, 'Практика 1');
  assert.equal(sessions[0].name, 'Гонка');
  assert.equal(sessionStart({ name: 'Гонка', utc_iso: '2026-10-25' }), null);
  assert.equal(sessionStart({ name: 'Гонка', utc_iso: '2026-10-25T20:00:00' }), null);
  assert.deepEqual(availableResults(sessions, Date.parse('2026-10-24T16:59:59Z')), []);
  assert.deepEqual(availableResults(sessions, Date.parse('2026-10-24T17:00:00Z')), [{ path: '/sprint-results', title: 'Спринт' }]);
});
test('results distinguish sprint qualifying from sprint and group practices without duplicates', () => {
  assert.equal(sessionResultsPath('Спринт-квалификация'), '/sprint-quali-results');
  assert.equal(sessionResultsPath('Sprint Shootout'), '/sprint-quali-results');
  assert.equal(sessionResultsPath('Квалификация'), '/quali-results');
  assert.equal(sessionResultsPath('Пресс-конференция'), null);
  const sessions = ['Практика 1', 'Практика 2', 'Квалификация', 'Гонка'].map(name => ({ name, utc_iso: '2026-10-20T12:00:00+03:00' }));
  assert.equal(availableResults(sessions, Date.parse('2026-10-22T12:00:00Z')).length, 3);
});
