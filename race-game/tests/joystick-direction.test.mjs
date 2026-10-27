import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

const { outputText } = ts.transpileModule(await readFile(new URL('../src/joystickDirection.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
});
const { joystickDirection, aimJoystickHeading } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'));

test('joystick aims at all eight screen directions from every starting heading', () => {
  for (const [x, y] of [[1,0], [1,1], [0,1], [-1,1], [-1,0], [-1,-1], [0,-1], [1,-1]]) {
    const direction = joystickDirection(x * 40, y * 40, 50);
    for (const initial of [-Math.PI, -Math.PI / 2, 0, Math.PI / 2, Math.PI, 12 * Math.PI]) {
      let heading = initial;
      for (let step = 0; step < 120; step++) heading = aimJoystickHeading(heading, direction, 1 / 120);
      assert.ok(Math.cos(heading) * direction.x + Math.sin(heading) * direction.y > .999999);
    }
  }
});
test('centre, release and invalid pointer geometry do not change the direction', () => {
  for (const args of [[0,0,50], [2,2,50], [20,20,0], [NaN,0,50], [0,Infinity,50]]) assert.equal(joystickDirection(...args), null);
  assert.equal(aimJoystickHeading(1.2, null, .1), 1.2);
  assert.equal(aimJoystickHeading(1.2, {x:1,y:0}, 0), 1.2);
});
test('steering crosses the angle seam by the short arc and is consistent across frame rates', () => {
  assert.ok(aimJoystickHeading(Math.PI - .05, {x:-1,y:-.05}, .01) > Math.PI - .05);
  for (const fps of [30,60,120]) {
    let heading = 0;
    for (let frame = 0; frame < fps; frame++) heading = aimJoystickHeading(heading, {x:0,y:-1}, 1 / fps);
    assert.ok(Math.abs(heading + Math.PI / 2) < 1e-9);
  }
});
