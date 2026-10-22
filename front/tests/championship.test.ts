import assert from 'node:assert/strict';
import test from 'node:test';
import { titleAnswersComplete, type Candidate, type ChampionshipContext } from '../src/pages/predictions/championship.ts';

const candidate = (id: string): Candidate => ({
  id, name: id, points: 350, wins: 7, remaining_points: 50,
  future_races: 2, scenarios: [], has_sprint: false,
});
const context: ChampionshipContext = {
  status: 'ok', drivers: [candidate('ANT'), candidate('RUS')], constructors: [candidate('mercedes')],
};

test('missing or unavailable title scenarios do not block the main forecast', () => {
  for (const value of [null, undefined, { ...context, status: 'unavailable' }, { status: 'ok', drivers: [], constructors: [] }]) {
    assert.equal(titleAnswersComplete(value, {}), true);
  }
});

test('every eligible competition requires an explicit yes or no for a current candidate', () => {
  const drivers = { id: 'ANT', yes: false };
  const constructors = { id: 'mercedes', yes: true };
  assert.equal(titleAnswersComplete(context, {}), false);
  assert.equal(titleAnswersComplete(context, { drivers }), false);
  assert.equal(titleAnswersComplete(context, { constructors }), false);
  assert.equal(titleAnswersComplete(context, { drivers, constructors }), true);
  assert.equal(titleAnswersComplete(context, { drivers: { id: 'RUS', yes: true }, constructors }), true);
  assert.equal(titleAnswersComplete(context, { drivers: { id: 'ANT', yes: null }, constructors }), false);
  assert.equal(titleAnswersComplete(context, { drivers: { id: 'NOR', yes: true }, constructors }), false);
  assert.equal(titleAnswersComplete(context, { drivers, constructors: { id: 'mclaren', yes: false } }), false);
});

test('a competition without a candidate requires no title answer', () => {
  assert.equal(titleAnswersComplete({ ...context, constructors: [] }, { drivers: { id: 'ANT', yes: false } }), true);
  assert.equal(titleAnswersComplete({ ...context, drivers: [] }, { constructors: { id: 'mercedes', yes: false } }), true);
});
