export type TrackPoint = { x: number; y: number }

// Painted stripe on emerald-loop-track.png, in world pixels.
export const FINISH_LINE = { x: 875, minY: 630, maxY: 700 }

export function finishCrossing(previous: TrackPoint, current: TrackPoint): number | null {
  if (previous.x >= FINISH_LINE.x || current.x < FINISH_LINE.x) return null
  const fraction = (FINISH_LINE.x - previous.x) / (current.x - previous.x)
  const y = previous.y + (current.y - previous.y) * fraction
  return y >= FINISH_LINE.minY && y <= FINISH_LINE.maxY ? fraction : null
}
