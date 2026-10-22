import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';

const bundle = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/index/PersonalHome.tsx', import.meta.url))],
  bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic', external: ['react', 'react-router-dom'],
  define: { 'import.meta.env': '{}' },
  plugins: [{ name: 'ignore-css', setup(builder) { builder.onLoad({ filter: /\.css$/ }, () => ({ contents: '', loader: 'js' })); } }],
});
const mod = { exports: {} };
new Function('require', 'module', 'exports', bundle.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports);
const { PersonalHome } = mod.exports;
const render = (signedIn, personalized = false) => renderToStaticMarkup(React.createElement(MemoryRouter, null,
  React.createElement(PersonalHome, { auth: { loaded: true, signedIn, personalized }, timezone: 'UTC' })));

test('personal navigation is a closed native disclosure with labelled link rows', () => {
  const html = render(true);
  assert.match(html, /<details class="personal-home-details"><summary>Личные разделы/);
  assert.match(html, /<nav aria-label="Личные разделы"><ul class="home-link-list">/);
  for (const href of ['/account', '/settings', '/predictions?tab=history', '/community']) assert.ok(html.includes(`href="${href}"`));
  assert.equal((html.match(/<summary/g) || []).length, 1);
  assert.doesNotMatch(html, /aria-controls="personal-home-more"|personal-home-toggle|<details[^>]*\sopen/);
});

test('guests do not get member links and favorites retain their access condition', () => {
  const guest = render(false);
  assert.match(guest, /Попробовать/);
  assert.doesNotMatch(guest, /<details|href="\/account"|href="\/favorites"/);
  assert.doesNotMatch(render(true), /href="\/favorites"/);
  assert.match(render(true, true), /href="\/favorites"/);
});
