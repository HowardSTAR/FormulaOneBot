// Bound catch-up after suspension, but never advance the clock without physics.
export function simulationSteps(frameMs: number): number[] {
  if (!Number.isFinite(frameMs) || frameMs <= 0) return []
  let remaining = Math.min(frameMs, 250)
  const steps: number[] = []
  while (remaining > 0) {
    const step = Math.min(remaining, 1000 / 120)
    steps.push(step)
    remaining -= step
  }
  return steps
}
