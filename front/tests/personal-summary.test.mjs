import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

const source = readFileSync(new URL('../src/pages/index/personal-summary.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { predictionSummary } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const now = Date.parse('2026-09-14T10:00:00Z');
const base = { status: 'ok', is_open: true, deadline_utc: '2026-09-14T11:00:00Z', prediction: null };

test('open missing prediction is urgent in final two hours', () => {
  assert.equal(predictionSummary(base, now).urgent, true);
  assert.equal(predictionSummary(base, now).action, 'Сделать прогноз');
});
test('saved prediction is not shown as missing', () => {
  assert.equal(predictionSummary({ ...base, prediction: {} }, now).title, 'Прогноз сохранён');
});
test('deadline closes locally even with stale server flag', () => {
  assert.equal(predictionSummary(base, Date.parse(base.deadline_utc)).title, 'Приём закрыт');
});
test('zero points is a calculated result', () => {
  assert.equal(predictionSummary({ ...base, prediction: { points: 0 } }, now).title, 'Ваш результат: 0 очк.');
});
test('future window is not described as closed', () => {
  assert.equal(predictionSummary({ ...base, is_open: false, opens_at_utc: '2026-09-15T10:00:00Z' }, now).title, 'Приём ещё не открыт');
});
test('unavailable round and malformed deadline never invite submission', () => {
  assert.equal(predictionSummary({ ...base, status: 'unavailable' }, now).urgent, false);
  assert.notEqual(predictionSummary({ ...base, deadline_utc: 'invalid' }, now).action, 'Сделать прогноз');
});
