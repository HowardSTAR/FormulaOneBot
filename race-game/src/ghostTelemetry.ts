export type GhostSample = { t: number; x: number; y: number; rotation: number }

// The API accepts signed radians. Phaser.Angle.Normalize returns 0..2pi
// instead, which made the old client's first sample fail validation.
const wrapAngle = (angle: number): number => Math.atan2(Math.sin(angle), Math.cos(angle))

export function createTelemetrySample(t: number, x: number, y: number, rotation: number): GhostSample {
  return {
    t: Math.round(t),
    x: Number(x.toFixed(2)),
    y: Number(y.toFixed(2)),
    rotation: Number(wrapAngle(rotation).toFixed(4)),
  }
}

export function interpolateGhost(samples: GhostSample[], elapsed: number): GhostSample | null {
  if (samples.length < 2) return null
  let low = 0
  let high = samples.length - 1
  while (low + 1 < high) {
    const middle = (low + high) >>> 1
    if (samples[middle].t <= elapsed) low = middle
    else high = middle
  }
  const start = samples[low]
  const end = samples[high]
  const progress = Math.max(0, Math.min(1, (elapsed - start.t) / Math.max(1, end.t - start.t)))
  return {
    t: elapsed,
    x: start.x + (end.x - start.x) * progress,
    y: start.y + (end.y - start.y) * progress,
    rotation: wrapAngle(start.rotation + wrapAngle(end.rotation - start.rotation) * progress),
  }
}
