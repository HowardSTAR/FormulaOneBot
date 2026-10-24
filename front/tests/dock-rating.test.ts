import test from 'node:test';
import assert from 'node:assert/strict';
import { latestDockRace } from '../src/helpers/dockRating.ts';
const now = Date.parse('2026-10-24T12:00:00Z');
test('rating prompt excludes future and ongoing races', () => {
  const races = [{ round: 18, event_name: 'Finished', race_start_utc: '2026-10-11T12:00:00Z' }, { round: 19, event_name: 'Ongoing', race_start_utc: '2026-10-24T10:00:00Z' }, { round: 20, event_name: 'Future', race_start_utc: '2026-10-25T12:00:00Z' }];
  assert.equal(latestDockRace(races, now)?.round, 18);
});
test('latest rating follows the actual schedule rather than array or round order', () => {
  const earlier = { round: 20, event_name: 'Rescheduled earlier', race_start_utc: '2026-10-01T12:00:00Z' };
  const latest = { round: 18, event_name: 'Latest', race_start_utc: '2026-10-11T12:00:00Z' };
  assert.equal(latestDockRace([latest, earlier], now), latest);
});
test('cancelled and invalid dates do not produce a rating target', () => {
  assert.equal(latestDockRace([{ round: 19, event_name: 'Cancelled', is_cancelled: true, race_start_utc: '2026-10-11T12:00:00Z' }, { round: 20, event_name: 'Unknown', date: 'unknown' }], now), undefined);
});
test('date-only schedules wait until the next UTC day', () => {
  const race = { round: 18, event_name: 'No start time', date: '2026-10-24' };
  assert.equal(latestDockRace([race], now), undefined);
  assert.equal(latestDockRace([race], Date.parse('2026-10-25T00:00:00Z')), race);
});
