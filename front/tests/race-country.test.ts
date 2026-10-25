import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { raceCountryCode } from '../src/helpers/raceCountry.ts';

test('race flags accept source country names, Russian labels and ISO codes', () => {
  for (const [country, code] of [['United States', 'us'], ['США', 'us'], ['U.S.A.', 'us'], ['Saudi Arabia', 'sa'], ['ОАЭ', 'ae'], ['Türkiye', 'tr'], ['GB', 'gb'], ['ЮАР', 'za'], [' Netherlands ', 'nl']]) {
    assert.equal(raceCountryCode(country), code);
    assert.ok(existsSync(new URL(`../public/flags/${code}.svg`, import.meta.url)));
  }
});
test('missing countries use unambiguous events; known country takes precedence', () => {
  assert.equal(raceCountryCode('', 'São Paulo Grand Prix'), 'br');
  assert.equal(raceCountryCode(undefined, 'Emilia Romagna Grand Prix'), 'it');
  assert.equal(raceCountryCode('Spain', 'European Grand Prix'), 'es');
  assert.equal(raceCountryCode('United Kingdom', 'European Grand Prix'), 'gb');
  assert.equal(raceCountryCode('', 'European Grand Prix'), null);
  assert.equal(raceCountryCode('', 'Pacific Grand Prix'), null);
});
test('unknown and unsafe country values never become guessed flags or asset paths', () => {
  for (const country of ['Atlantis', '../../us', 'https://example.test/us.svg']) {
    assert.equal(raceCountryCode(country, 'United States Grand Prix'), null);
  }
  assert.equal(raceCountryCode('', 'New Grand Prix'), null);
});
