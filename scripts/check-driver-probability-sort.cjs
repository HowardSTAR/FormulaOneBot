const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('../front/node_modules/typescript');
const source = fs.readFileSync(path.join(__dirname, '../front/src/pages/prediction-analytics/driver-sort.ts'), 'utf8');
const context = {exports: {}};
vm.runInNewContext(ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText, context);
const {sortDrivers, nextDriverSort} = context.exports;
const rows = [
  {code:'B', name:'Bravo', team:'Team B', win:.09, podium:.9, top10:.8, expected:10, dnf:.2},
  {code:'A', name:'Alpha', team:'Team C', win:.11, podium:.1, top10:.9, expected:2, dnf:.3},
  {code:'C', name:'Charlie', team:'Team A', win:.2, podium:.5, top10:.7, expected:5, dnf:.1},
];
const actual = new Map([['A',10], ['B',2]]);
const expected = {name:'ABC',team:'CBA',win:'BAC',podium:'ACB',top10:'CBA',expected:'ACB',dnf:'CBA',actual:'BAC'};
const codes = (key, direction) => Array.from(sortDrivers(rows, {key, direction}, actual), row => row.code).join('');
for (const [key, ascending] of Object.entries(expected)) {
  assert.equal(codes(key,'asc'), ascending, key);
  assert.equal(codes(key,'desc'), key === 'actual' ? 'ABC' : ascending.split('').reverse().join(''), key);
}
assert.equal(rows.map(row=>row.code).join(''), 'BAC', 'Input snapshot stays unchanged');
assert.equal(nextDriverSort({key:'name',direction:'asc'},'win').direction,'desc');
assert.equal(nextDriverSort({key:'win',direction:'desc'},'win').direction,'asc');
assert.equal(nextDriverSort({key:'win',direction:'asc'},'expected').direction,'asc');
const invalid = [...rows, {...rows[0], code:'X', win:NaN}];
for (const direction of ['asc','desc']) assert.equal(sortDrivers(invalid,{key:'win',direction},actual).at(-1).code,'X');
const tied = rows.map(row=>({...row,win:.1}));
assert.equal(Array.from(sortDrivers(tied,{key:'win',direction:'desc'},actual),row=>row.code).join(''),'ABC');
console.log('All 8 sort keys, both directions, numeric order, missing values, ties and immutability: passed');
