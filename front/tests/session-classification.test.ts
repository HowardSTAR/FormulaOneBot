import test from 'node:test';
import assert from 'node:assert/strict';
import { classificationRows, lapMilliseconds, practiceGap } from '../src/helpers/sessionClassification.ts';

test('practice sorts actual lap times and keeps untimed participants after timed drivers', () => {
  const input = [{ position: 1, driver: 'SLOW', best: '1:10.123', laps: 8, points: 25 }, { position: 2, driver: 'FAST', best: '1:09.999', laps: 2 }, { position: 3, driver: 'NONE', best: '—', laps: 0 }, { position: 4, driver: 'OUT', laps: 1 }];
  const rows = classificationRows(input, 'practice');
  assert.deepEqual(rows.map(row => row.driver), ['FAST','SLOW','NONE','OUT']);
  assert.equal(practiceGap(rows[0], rows[0]), '—');
  assert.equal(practiceGap(rows[1], rows[0]), '+0.124');
  assert.equal(input[0].driver, 'SLOW');
});

test('race and qualifying preserve official positions instead of sorting across sessions or by fastest lap', () => {
  const rows = [{ position: 11, best: '1:09.000', segment: 'Q2' }, { position: 1, best: '1:10.000', segment: 'Q3' }];
  assert.deepEqual(classificationRows(rows, 'quali').map(row => row.position), [1,11]);
  assert.deepEqual(classificationRows(rows, 'sprint').map(row => row.position), [1,11]);
});

test('missing and malformed times cannot become a lap or a fabricated gap', () => {
  for (const time of ['', '—', '-', 'DNF', '0.000']) assert.equal(lapMilliseconds(time), null);
  assert.equal(lapMilliseconds('59.123'), 59123);
  assert.equal(practiceGap({ position: 1, best: '—' }, { position: 2, best: '1:09.000' }), '—');
});
