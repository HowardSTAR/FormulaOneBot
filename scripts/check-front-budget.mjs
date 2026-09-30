/** Production startup budget includes static dependencies, not lazy routes. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { gzipSync } from 'node:zlib';

const root = resolve(process.argv[2] || 'front/dist');
const manifest = JSON.parse(readFileSync(resolve(root, '.vite/manifest.json'), 'utf8'));
const visited = new Set(), files = new Set();
function visit(key) {
  if (visited.has(key)) return;
  visited.add(key);
  const entry = manifest[key];
  assert.ok(entry, `Missing manifest entry: ${key}`);
  files.add(entry.file);
  (entry.css || []).forEach(file => files.add(file));
  (entry.imports || []).forEach(visit);
}
visit('index.html');
const totals = { js: 0, js_gzip: 0, css: 0, css_gzip: 0 };
for (const file of files) {
  const kind = file.endsWith('.js') ? 'js' : file.endsWith('.css') ? 'css' : null;
  if (!kind) continue;
  const data = readFileSync(resolve(root, file));
  totals[kind] += data.byteLength;
  totals[`${kind}_gzip`] += gzipSync(data).byteLength;
}
console.log(JSON.stringify({ root, startup_files: [...files], bytes: totals }, null, 2));
if (!process.argv.includes('--report-only')) {
  assert.ok(totals.js < 450000, 'Initial JS exceeds 450 KB; keep chart/game code lazy');
  assert.ok(totals.js_gzip < 145000, 'Initial compressed JS exceeds 145 KB');
  for (const key of visited) assert.ok(!/chart|ComparePage|GamePage|AdminPage|PredictionAnalyticsPage/.test(key), `Heavy code eagerly loaded: ${key}`);
  console.log('Startup performance budget passed.');
}
