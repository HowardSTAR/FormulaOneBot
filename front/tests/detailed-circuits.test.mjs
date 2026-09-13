import { readFile } from 'node:fs/promises';
import { transform } from 'esbuild';
import assert from 'node:assert/strict';
import test from 'node:test';
const source = await readFile(new URL('../src/assets/detailedCircuits.ts', import.meta.url), 'utf8');
const { code } = await transform(source, {loader:'ts',format:'esm'});
const { getDetailedCircuit, detailedCircuits } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
test('only reviewed season and circuit are matched',()=>{
  assert.equal(getDetailedCircuit('Hungarian Grand Prix',2025),null);
  assert.equal(getDetailedCircuit('Spanish Grand Prix',2026),null);
  assert.ok(getDetailedCircuit('Hungarian Grand Prix',2026));
  assert.equal(getDetailedCircuit('constructor',2026),null);
  for (const event of Object.keys(detailedCircuits)) {
    assert.equal(getDetailedCircuit(event,2025),null);
    assert.equal(getDetailedCircuit(event,2027),null);
  }
});
test('Hungary has complete numbering and all zone types',()=>{
  const data=getDetailedCircuit('Hungarian Grand Prix',2026);
  assert.deepEqual(data.corners.map(v=>v[0]),Array.from({length:14},(_,i)=>i+1));
  assert.equal(data.sectors.length,3);
  assert.equal(data.zones.length,4);
  assert.ok(data.pitLane && data.finish && data.activation && data.detection);
  assert.ok(data.source.startsWith('https://www.fia.com/'));
});
test('turn labels remain inside the viewport with margins',()=>{
  for (const data of Object.values(detailedCircuits)) {
  const [x,y,w,h]=data.viewBox.split(' ').map(Number);
  for(const [,cx,cy] of data.corners){
    assert.ok(cx-28>=x && cx+28<=x+w);
    assert.ok(cy-25>=y && cy+25<=y+h);
  }
  }
});

const expected = {
  'Hungarian Grand Prix': [14,4], 'Austrian Grand Prix': [10,4],
  'Italian Grand Prix': [11,4], 'Australian Grand Prix': [14,5],
};
for (const [event,[turnCount,zoneCount]] of Object.entries(expected)) {
  test(`${event}: complete, independent reviewed layers`,()=>{
    const data=getDetailedCircuit(event,2026);
    assert.deepEqual(data.corners.map(v=>v[0]),Array.from({length:turnCount},(_,i)=>i+1));
    assert.equal(data.sectors.length,3);
    assert.equal(data.zones.length,zoneCount);
    assert.ok(data.direction && Number.isFinite(data.finishAngle));
    assert.ok(data.detectionDescription && data.activationDescription && data.sectorDescription);
    assert.match(data.source,/^https:\/\/www\.fia\.com\/system\/files\//);
    assert.ok(data.pitLane);
    for (const [index,[n,x,y]] of data.corners.entries()) {
      for (const [m,mx,my] of data.corners.slice(index+1)) {
        assert.ok(Math.abs(x-mx)>=56 || Math.abs(y-my)>=48,`${event}: labels ${n}/${m} overlap`);
      }
    }
    const [x,y,w,h]=data.viewBox.split(' ').map(Number);
    for (const [px,py] of [data.detection,data.activation,data.finish]) {
      assert.ok(px>=x+14 && px<=x+w-14 && py>=y+14 && py<=y+h-14);
    }
  });
}
