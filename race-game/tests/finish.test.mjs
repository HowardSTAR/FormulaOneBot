import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/finishLine.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
})
const { finishCrossing } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'))

test('approaching the old 88px finish radius does not complete a lap', () => {
  assert.equal(finishCrossing({ x: 780, y: 660 }, { x: 790, y: 660 }), null)
  assert.equal(finishCrossing({ x: 870, y: 660 }, { x: 874.9, y: 660 }), null)
})

test('the finish requires a forward crossing on the road', () => {
  assert.equal(finishCrossing({ x: 874, y: 660 }, { x: 876, y: 660 }), 0.5)
  assert.equal(finishCrossing({ x: 874, y: 660 }, { x: 875, y: 660 }), 1)
  assert.equal(finishCrossing({ x: 880, y: 660 }, { x: 870, y: 660 }), null)
  assert.equal(finishCrossing({ x: 875, y: 660 }, { x: 875, y: 660 }), null)
  assert.equal(finishCrossing({ x: 875, y: 660 }, { x: 885, y: 660 }), null)
  assert.equal(finishCrossing({ x: 870, y: 600 }, { x: 880, y: 600 }), null)
  assert.equal(finishCrossing({ x: 870, y: 710 }, { x: 880, y: 710 }), null)
})

test('a long frame still detects the line at the interpolated crossing position', () => {
  assert.equal(finishCrossing({ x: 855, y: 640 }, { x: 895, y: 680 }), 0.5)
  assert.equal(finishCrossing({ x: 855, y: 600 }, { x: 895, y: 620 }), null)
})
