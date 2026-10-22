import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';

const bundle = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/index/Hero.tsx', import.meta.url))],
  bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic', external: ['react', 'react-router-dom'],
  plugins: [{ name: 'ignore-css', setup(builder) { builder.onLoad({ filter: /\.css$/ }, () => ({ contents: '', loader: 'js' })); } }],
});
const mod = { exports: {} };
new Function('require', 'module', 'exports', bundle.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports);
const Hero = mod.exports.default;
const future = new Date(Date.now() + 86400000).toISOString();
const race = { status: 'ok', event_name: 'Test Grand Prix', season: 2026, next_session_iso: future, next_session_name: 'Практика 1' };
const render = nextRace => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(Hero, {
  nextRace, schedule: [], userTz: 'UTC', loaded: true, onRetry() {},
})));

test('upcoming event is one named native link without a nested button or link', () => {
  const html = render(race);
  assert.equal((html.match(/<a\b/g) || []).length, 1);
  assert.match(html, /href="\/next-race"/);
  assert.match(html, /aria-label="Уик-энд: Test Grand Prix"/);
  assert.match(html, /<h2 id="home-race-title"><a\b/);
  assert.doesNotMatch(html, /<button|Открыть уик-энд/);
});

test('cancelled and completed seasons lead to the calendar; errors retain retry', () => {
  for (const state of [{ ...race, is_cancelled: true }, { ...race, status: 'season_finished' }]) {
    const html = render(state);
    assert.match(html, /href="\/season"/);
    assert.doesNotMatch(html, /home-race--upcoming/);
  }
  assert.match(render({ status: 'error' }), /<button[^>]*>Повторить загрузку<\/button>/);
});
