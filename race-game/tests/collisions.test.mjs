import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

async function loadModule(path, replace = source => source) {
  const source = replace(await readFile(new URL(path, import.meta.url), 'utf8'))
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  })
  return import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'))
}
const { advanceWithCollisions } = await loadModule('../src/collisions.ts')
const definitions = await readFile(new URL('../../app/race_tracks.json', import.meta.url), 'utf8')
const { tracks, trackColliders } = await loadModule('../src/tracks.ts', source =>
  source.replace("import definitions from '../../app/race_tracks.json'", `const definitions = ${definitions}`))

test('frontal impact stops the nose at a building, even with a long frame', () => {
  const result = advanceWithCollisions({ x: 0, y: 0 }, { x: 350, y: 0 }, 0, 1,
    [{ type: 'rect', x: 100, y: -50, width: 30, height: 100 }])
  assert.ok(result.x <= 67.001)
  assert.ok(result.vx <= 0)
  assert.ok(result.impact > 300)
})

test('thin walls cannot be tunnelled through; sliding keeps tangential movement', () => {
  const wall = { type: 'wall', a: { x: 100, y: -200 }, b: { x: 100, y: 200 }, radius: 6 }
  const result = advanceWithCollisions({ x: 0, y: 0 }, { x: 350, y: 90 }, 0, 0.5, [wall])
  assert.ok(result.x <= 61.001)
  assert.ok(result.y > 25)
  assert.ok(result.vy > 0)
})

test('tree collision and reversing away do not trap the car', () => {
  const tree = { type: 'circle', x: 100, y: 0, radius: 25 }
  const stopped = advanceWithCollisions({ x: 0, y: 0 }, { x: 300, y: 0 }, 0, 0.4, [tree])
  assert.ok(stopped.x <= 42.001)
  const reversed = advanceWithCollisions(stopped, { x: -60, y: 0 }, 0, 0.2, [tree])
  assert.ok(reversed.x < stopped.x)
  assert.equal(reversed.impact, 0)
})

test('grass and curbs remain driveable; no obstacle means unchanged movement', () => {
  const result = advanceWithCollisions({ x: 300, y: 300 }, { x: 100, y: 50 }, 1, 0.2, [])
  assert.ok(Math.abs(result.x - 320) < 0.0001)
  assert.ok(Math.abs(result.y - 310) < 0.0001)
  assert.equal(result.impact, 0)
})

test('holding throttle against a wall cannot push the car through it', () => {
  const obstacle = { type: 'rect', x: 100, y: -100, width: 80, height: 200 }
  let position = { x: 50, y: 0 }
  for (let frame = 0; frame < 1000; frame++) {
    position = advanceWithCollisions(position, { x: 350, y: 0 }, 0, 1 / 120, [obstacle])
    assert.ok(position.x <= 67.001)
  }
})

test('rotating next to a building resolves overlap using the car body, not its centre', () => {
  const result = advanceWithCollisions({ x: 80, y: 0 }, { x: 0, y: 0 }, 0, 0,
    [{ type: 'rect', x: 100, y: -50, width: 40, height: 100 }])
  assert.ok(result.x <= 67.001)
})

test('four distinct circuits have a clear driveable centreline and start', () => {
  assert.equal(tracks.length, 4)
  assert.equal(new Set(tracks.map(track => track.id)).size, 4)
  for (const track of tracks) {
    const colliders = trackColliders(track)
    assert.ok(colliders.length > 20)
    for (let index = 0; index < track.centerLine.length; index++) {
      const [x, y] = track.centerLine[index]
      const [bx, by] = track.centerLine[(index + 1) % track.centerLine.length]
      const heading = Math.atan2(by - y, bx - x)
      const steps = Math.ceil(Math.hypot(bx - x, by - y) / 12)
      for (let step = 0; step < steps; step++) {
        const point = { x: x + (bx - x) * step / steps, y: y + (by - y) * step / steps }
        const result = advanceWithCollisions(point, { x: 0, y: 0 }, heading, 0, colliders)
        assert.ok(Math.hypot(result.x - point.x, result.y - point.y) < 0.01,
          `${track.name}: blocked centreline at ${point.x}, ${point.y}`)
      }
    }
  }
})
