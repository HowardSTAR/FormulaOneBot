import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(new URL('../src/ghostTelemetry.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
})
const { createTelemetrySample, interpolateGhost } = await import(
  'data:text/javascript;base64,' + Buffer.from(outputText).toString('base64')
)

test('opening the leaderboard cannot restore wiped local scores', async () => {
  const main = await readFile(new URL('../src/main.ts', import.meta.url), 'utf8')
  const loader = main.slice(main.indexOf('const loadLeaderboard ='), main.indexOf('let ghostRequestVersion'))
  assert.ok(loader.includes("apiRequest<LeaderboardResponse>('/api/race-game-leaderboard')"))
  assert.ok(!loader.includes('submitRaceTime('))
  assert.ok(!loader.includes('localStorage.getItem('))
})

test('all rotations during three laps fit the API signed-radian bounds', () => {
  for (let degrees = 0; degrees <= 1080; degrees++) {
    const frame = createTelemetrySample(degrees * 100, 875, 660, -Math.PI / 2 - degrees * Math.PI / 180)
    assert.ok(frame.rotation >= -3.142 && frame.rotation <= 3.142)
  }
  assert.equal(createTelemetrySample(0, 875, 660, -Math.PI / 2).rotation, -1.5708)
})

test('playback follows the recorded positions and crosses the angle seam without spinning', () => {
  const frames = [
    { t: 0, x: 10, y: 20, rotation: 3.1 },
    { t: 100, x: 30, y: 40, rotation: -3.1 },
    { t: 200, x: 80, y: 60, rotation: -2 },
  ]
  const halfway = interpolateGhost(frames, 50)
  assert.equal(halfway.x, 20)
  assert.equal(halfway.y, 30)
  assert.ok(Math.abs(Math.abs(halfway.rotation) - Math.PI) < 0.00001)
  assert.equal(interpolateGhost(frames, 150).x, 55)
  assert.equal(interpolateGhost(frames, 200).x, 80)
  assert.equal(interpolateGhost(frames, 0).x, 10) // restart after a previous replay
  assert.equal(interpolateGhost([], 0), null)
})
