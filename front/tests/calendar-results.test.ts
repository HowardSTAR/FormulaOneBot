import { calendarWeekendLink, calendarResultsLink } from '../src/helpers/seasonCalendar.ts';
import { calendarPreviewStage } from './fixtures/calendar.ts';
import test from 'node:test';
import assert from 'node:assert/strict';
import { weekendResultGroups } from '../src/pages/next-race/weekend-model.ts';

test('sprint weekends group one practice, SQ/SR and qualifying/race', () => {
  const groups = weekendResultGroups(['Практика 1','Спринт-квалификация','Спринт','Квалификация','Гонка'].map(name => ({ name })));
  assert.deepEqual(groups.map(group => group.label), ['Практика','Спринт','Уик-энд']);
  assert.deepEqual(groups.map(group => group.sessions.map(item => item.label)), [['P1'],['SQ','SR'],['Квалификация','Гонка']]);
  assert.deepEqual(groups[1].sessions.map(item => item.id), ['sprint-quali','sprint']);
});

test('practice selector follows the actual schedule and normal weekends omit sprint', () => {
  const groups = weekendResultGroups(['Гонка','Практика 3','Практика 1','Квалификация','Практика 2','Практика 2'].map(name => ({ name })));
  assert.deepEqual(groups.map(group => group.id), ['practice','weekend']);
  assert.deepEqual(groups[0].sessions.map(item => item.label), ['P1','P2','P3']);
  assert.deepEqual(weekendResultGroups([{ name: 'Пресс-конференция' }]), []);
});

test('both calendar actions and demo data refer to the clicked Singapore stage, not Austin', () => {
  const race = calendarPreviewStage(2026, 18)!;
  assert.equal(calendarWeekendLink(race, 2026), '/next-race?season=2026&round=18');
  assert.equal(calendarResultsLink(race, 2026), '/next-race?season=2026&round=18&results=1&from=calendar');
  assert.equal(race.event_name, 'Singapore Grand Prix');
  assert.equal(race.country, 'Сингапур');
  assert.equal(race.sessions.some(session => session.name === 'Практика 3'), true);
  assert.equal(race.sessions.some(session => session.name === 'Спринт'), false);
  assert.equal(calendarPreviewStage(2026, 19)!.event_name, 'United States Grand Prix');
  assert.equal(calendarPreviewStage(2025, 18)!.season, 2025);
  assert.equal(calendarPreviewStage(2026, 1), null);
});
