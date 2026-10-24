import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { navigationFor } from '../src/helpers/navigation.ts';

const bundle = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/index/HomeIcon.tsx', import.meta.url))],
  bundle: true, write: false, format: 'cjs', platform: 'node', jsx: 'automatic', external: ['react'],
});
const mod = { exports: {} };
new Function('require', 'module', 'exports', bundle.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports);
const { HomeIcon } = mod.exports;
const render = icon => renderToStaticMarkup(React.createElement(HomeIcon, { name: icon }));
const nav = navigationFor({ signedIn: false, personalized: false, role: null });

test('weekend, each result type and racing game have distinct symbols', () => {
  const entries = [nav.primary.find(item => item.to === '/next-race'), ...nav.groups.find(group => group.id === 'results').items,
    nav.groups.find(group => group.id === 'games').items.find(item => item.to === '/race-game')];
  assert.equal(new Set(entries.map(item => render(item.icon))).size, entries.length);
});

test('history and comparison do not reuse the same symbol', () => {
  const entries = nav.groups.find(group => group.id === 'comparison').items;
  assert.notEqual(render(entries[0].icon), render(entries[1].icon));
});
