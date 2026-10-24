import assert from 'node:assert/strict';
import test from 'node:test';
import { loadTs } from './support/modules.mjs';
const { orderedSessions, upcomingSession, countdownLabel, raceStart } = await loadTs(new URL('../src/pages/index/home-session.ts', import.meta.url));
const now = Date.parse('2026-10-22T23:30:00Z');
const race = { status: 'ok', next_session_iso: '2026-10-24T12:00:00Z', next_session_name: 'Гонка' };

test('home selects the nearest valid session across dates without mutating the schedule', () => {
  const rows = [{ name: 'Позже', utc_iso: '2026-10-24T10:00:00Z' }, { name: 'Нет времени' }, { name: 'Ошибка', utc_iso: 'invalid' }, { name: 'Ближайшая', utc_iso: '2026-10-23T00:30:00Z' }, { name: 'Прошедшая', utc_iso: '2026-10-21T00:00:00Z' }];
  const original = structuredClone(rows);
  assert.equal(upcomingSession(rows, race, now).name, 'Ближайшая');
  assert.equal(orderedSessions(rows).length, 3);
  assert.deepEqual(rows, original);
});
test('published start times never fabricate a live session or resurrect an ended season', () => {
  assert.equal(upcomingSession([], race, Date.parse(race.next_session_iso)), null);
  for (const state of [{ ...race, is_cancelled: true }, { ...race, status: 'season_finished' }, { ...race, status: 'error' }, null]) assert.equal(upcomingSession([], state, now), null);
  assert.equal(upcomingSession([], { ...race, next_session_iso: 'bad' }, now), null);
  assert.deepEqual(upcomingSession([], race, now), { name: 'Гонка', utc_iso: race.next_session_iso });
});
test('countdowns round up at the last minute and handle midnight and invalid dates', () => {
  assert.equal(countdownLabel('2026-10-23T00:30:00Z', now), 'Через 1 ч');
  assert.equal(countdownLabel(new Date(now + 1).toISOString(), now), 'Через 1 мин');
  assert.equal(countdownLabel(new Date(now + 86400000).toISOString(), now), 'Через 1 д');
  assert.equal(countdownLabel(new Date(now - 1).toISOString(), now), 'Старт по расписанию');
  assert.equal(countdownLabel('bad', now), 'Время уточняется');
});
test('the headline shows the Grand Prix start, independently of the nearest practice or sprint', () => {
  const start = '2026-10-25T20:00:00Z';
  const sessions = [{ name: 'Практика 1', utc_iso: '2026-10-23T17:30:00Z' }, { name: 'Спринт', utc_iso: '2026-10-24T17:00:00Z' }, { name: 'Гонка', utc_iso: start }];
  assert.equal(raceStart(sessions, { status: 'ok', next_session_name: 'Практика 1', next_session_iso: sessions[0].utc_iso }), start);
  assert.equal(raceStart([], { status: 'ok', race_start_utc: start }), start);
  assert.equal(raceStart([], { status: 'ok', next_session_name: 'Race', next_session_iso: start }), start);
  assert.equal(raceStart([], { status: 'ok', race_start_utc: 'bad', date: start }), start);
  assert.equal(raceStart([], { status: 'ok', next_session_name: 'Практика 1', next_session_iso: sessions[0].utc_iso, date: '2026-10-25' }), null);
  assert.equal(raceStart([{ name: 'Гонка', utc_iso: '2026-10-25T20:00:00' }], { status: 'ok' }), null);
  for (const state of [{ status: 'ok', is_cancelled: true }, { status: 'season_finished' }, { status: 'error' }, null]) assert.equal(raceStart(sessions, state), null);
});
