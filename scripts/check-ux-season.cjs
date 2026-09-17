const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('../front/node_modules/typescript');
function load(relative) {
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '..', relative), 'utf8'), {
    compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
  }).outputText;
  const context = {exports: {}, TextEncoder};
  vm.runInNewContext(code, context);
  return context.exports;
}
const {calendarText} = load('front/src/helpers/calendar.ts');
assert.equal(calendarText('Test', 'invalid', ''), null);
const title = 'Квалификация; тест, проверка\n'.repeat(7);
const ics = calendarText(title, '2026-09-25T15:00:00+03:00', 'https://f1hub.ru/next-race');
assert.ok(ics.includes('DTSTART:20260925T120000Z'));
for (const line of ics.split('\r\n')) assert.ok(Buffer.byteLength(line) <= 75);
const unfolded = ics.replace(/\r\n /g, '');
assert.ok(unfolded.includes('SUMMARY:Квалификация\\; тест\\, проверка\\n'));
assert.ok(ics.endsWith('END:VCALENDAR\r\n'));
const {getCircuitInsightsRu: insights} = load('front/src/assets/circuitInsightsRu.ts');
const circuit = (location, eventName, country, season = 2026) => insights({location, eventName, country, season});
assert.equal(circuit('Madrid', 'Spanish Grand Prix', 'Spain').stats[0].value, '5.414 км');
assert.equal(circuit('Barcelona', 'Barcelona-Catalunya Grand Prix', 'Spain').stats[0].value, '4.657 км');
assert.match(circuit('Barcelona', 'Spanish Grand Prix', 'Spain', 2001).stats[0].value, /Уточняются/);
assert.equal(circuit('Lusail', 'Qatar Grand Prix', 'Qatar').stats[0].value, '5.380 км');
assert.equal(circuit('Las Vegas', 'Las Vegas Grand Prix', 'USA').stats[0].value, '6.201 км');
assert.equal(circuit('Miami', 'Miami Grand Prix', 'United States').stats[0].value, '5.412 км');
assert.equal(circuit('Spielberg', 'Austrian Grand Prix', 'Austria').stats[0].value, '4.318 км');
console.log('UX checks passed: calendar UTC/escaping/UTF-8 and unambiguous circuit matching.');
