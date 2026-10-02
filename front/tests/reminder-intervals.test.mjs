import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

const source = readFileSync(new URL('../src/helpers/reminderIntervals.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText;
const {selectedIntervals, toggleInterval, NOTIFY_OPTIONS} = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

test('all five intervals are offered; missing array preserves legacy', () => {
  assert.deepEqual(NOTIFY_OPTIONS.map(option => option.value), [15,30,60,120,1440]);
  assert.deepEqual(selectedIntervals(undefined, 1440), [1440]);
  assert.deepEqual(selectedIntervals([]), []);
});
test('multiple toggles preserve selections and canonical order', () => {
  const original = [60];
  assert.deepEqual(toggleInterval(toggleInterval(original, 1440), 15), [15,60,1440]);
  assert.deepEqual(original, [60]);
  assert.deepEqual(toggleInterval([15,60,1440], 60), [15,1440]);
  assert.deepEqual(toggleInterval([15], 15), []);
  assert.deepEqual(selectedIntervals([60,15,60]), [15,60]);
});
