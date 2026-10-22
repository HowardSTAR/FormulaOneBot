import assert from 'node:assert/strict';
import test from 'node:test';
import { loadTs } from './support/modules.mjs';
const theme = await loadTs(new URL('../src/helpers/theme.ts', import.meta.url));

test('theme defaults to system, ignores corrupt preferences and handles denied storage', () => {
  assert.equal(theme.resolveTheme(null, true), 'dark');
  assert.equal(theme.resolveTheme(null, false), 'light');
  assert.equal(theme.resolveTheme('light', true), 'light');
  assert.equal(theme.resolveTheme('dark', false), 'dark');
  for (const value of [null, '', 'system', '<script>', 'Dark']) assert.equal(theme.storedTheme({ getItem: () => value }), null);
  assert.equal(theme.storedTheme({ getItem() { throw new Error('denied'); } }), null);
});

test('theme follows system until chosen, persists across pages, syncs tabs and survives unavailable storage', () => {
  const memory = new Map();
  const mediaListeners = new Map(), windowListeners = new Map();
  const system = { matches: true, addEventListener: (name, callback) => mediaListeners.set(name, callback) };
  const root = { dataset: {} };
  let metaColor = '';
  globalThis.document = { documentElement: root, querySelector: () => ({ setAttribute: (_, value) => { metaColor = value; } }) };
  globalThis.window = { matchMedia: () => system, localStorage: { getItem: key => memory.get(key) ?? null, setItem: (key, value) => memory.set(key, value) }, addEventListener: (name, callback) => windowListeners.set(name, callback) };
  theme.initializeTheme();
  assert.equal(theme.getTheme(), 'dark');
  assert.equal(root.dataset.theme, 'dark');
  system.matches = false;
  mediaListeners.get('change')();
  assert.equal(theme.getTheme(), 'light');
  let notifications = 0;
  const stop = theme.subscribeTheme(() => notifications++);
  theme.setTheme('dark');
  assert.equal(memory.get(theme.THEME_KEY), 'dark');
  assert.equal(metaColor, '#141518');
  assert.equal(notifications, 1);
  mediaListeners.get('change')();
  assert.equal(theme.getTheme(), 'dark', 'explicit preference wins over system changes');
  memory.set(theme.THEME_KEY, 'light');
  windowListeners.get('storage')({ key: theme.THEME_KEY });
  assert.equal(theme.getTheme(), 'light');
  window.localStorage.setItem = () => { throw new Error('denied'); };
  assert.doesNotThrow(() => theme.setTheme('dark'));
  assert.equal(theme.getTheme(), 'dark');
  stop();
  delete globalThis.window;
  delete globalThis.document;
});
