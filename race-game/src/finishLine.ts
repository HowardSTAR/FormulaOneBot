export type TrackPoint = { x: number; y: number }

// Painted stripe on emerald-loop-track.png, in world pixels.
export const FINISH_LINE = { x: 875, minY: 630, maxY: 700 }

export function finishCrossing(previous: TrackPoint, current: TrackPoint, line = FINISH_LINE): number | null {
  if (previous.x >= line.x || current.x < line.x) return null
  const fraction = (line.x - previous.x) / (current.x - previous.x)
  const y = previous.y + (current.y - previous.y) * fraction
  return y >= line.minY && y <= line.maxY ? fraction : null
}
