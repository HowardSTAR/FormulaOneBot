import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const { outputText } = ts.transpileModule(await readFile(new URL('../src/raceClock.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
})
const { simulationSteps } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'))

test('10, 30, 60 and 120 FPS give the same movement and stopwatch duration', () => {
  for (const fps of [10, 30, 60, 120]) {
    let elapsed = 0
    let distance = 0
    for (let frame = 0; frame < fps * 10; frame++) {
      for (const dt of simulationSteps(1000 / fps)) {
        elapsed += dt
        distance += 100 * dt / 1000
      }
    }
    assert.ok(Math.abs(elapsed - 10000) < 0.001)
    assert.ok(Math.abs(distance - 1000) < 0.001)
  }
})
test('suspended or malformed frames cannot jump the clock without movement', () => {
  assert.deepEqual(simulationSteps(NaN), [])
  assert.deepEqual(simulationSteps(-1), [])
  assert.ok(Math.abs(simulationSteps(10000).reduce((a, b) => a + b, 0) - 250) < 0.001)
  assert.ok(simulationSteps(100).every(dt => dt <= 1000 / 120))
})
