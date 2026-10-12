import assert from 'node:assert/strict';
import test from 'node:test';
import {selectRaceHighlights, type RaceHighlight} from '../src/helpers/raceHighlights.ts';

const event = (category: string, driver_code = '', published = 1, title = category): RaceHighlight => ({
  title, category, driver_code, published, score: category === 'incident' ? 100 : category === 'penalty' ? 90 : 80,
  url: `${category}-${driver_code}-${published}`, publisher: 'OpenF1', published_at: '2026-10-11T12:00:00Z',
});

test('general accidents and penalties plus only the followed drivers retained passes', () => {
  const rows = [event('incident'), event('penalty'), event('retained_overtake', 'VER'), event('retained_overtake', 'NOR'), event('position_change', 'VER')];
  assert.equal(selectRaceHighlights(rows, ['ver']).length, 3);
  assert.equal(selectRaceHighlights(rows, []).length, 2);
  assert(!selectRaceHighlights(rows, ['VER']).some(row => row.driver_code === 'NOR'));
  assert(!selectRaceHighlights(rows, ['VER']).some(row => row.category === 'position_change'));
  assert.equal(rows.length, 5);
});

test('deduplicates notices, preserves category diversity and displays selected events in time order', () => {
  const rows = [event('incident', '', 5), event('incident', '', 6), event('incident', '', 7, 'Second crash'),
    event('incident', '', 8, 'Third crash'), event('penalty', '', 4), event('retained_overtake', 'VER', 3)];
  const selected = selectRaceHighlights(rows, ['VER']);
  assert.equal(selected.length, 4);
  assert.deepEqual(selected.map(row => row.published), [3, 4, 5, 7]);
  assert.equal(new Set(selected.map(row => row.category)).size, 3);
});
