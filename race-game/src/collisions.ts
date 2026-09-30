export type Point = { x: number; y: number }
export type Collider =
  | { type: 'circle'; x: number; y: number; radius: number }
  | { type: 'rect'; x: number; y: number; width: number; height: number }
  | { type: 'wall'; a: Point; b: Point; radius: number }

// A capsule matches the open-wheel car better than one large circular hitbox.
export const CAR_RADIUS = 17
const BODY_OFFSETS = [-16, 0, 16]
const EPSILON = 0.001

function contact(point: Point, radius: number, collider: Collider): { nx: number; ny: number; depth: number } | null {
  let x: number, y: number, combinedRadius = radius
  if (collider.type === 'rect') {
    x = Math.max(collider.x, Math.min(collider.x + collider.width, point.x))
    y = Math.max(collider.y, Math.min(collider.y + collider.height, point.y))
    if (x === point.x && y === point.y) {
      const sides = [
        { nx: -1, ny: 0, depth: point.x - collider.x + radius },
        { nx: 1, ny: 0, depth: collider.x + collider.width - point.x + radius },
        { nx: 0, ny: -1, depth: point.y - collider.y + radius },
        { nx: 0, ny: 1, depth: collider.y + collider.height - point.y + radius },
      ]
      return sides.reduce((nearest, side) => side.depth < nearest.depth ? side : nearest)
    }
  } else if (collider.type === 'wall') {
    const dx = collider.b.x - collider.a.x, dy = collider.b.y - collider.a.y
    const squaredLength = dx * dx + dy * dy
    const fraction = squaredLength ? Math.max(0, Math.min(1,
      ((point.x - collider.a.x) * dx + (point.y - collider.a.y) * dy) / squaredLength)) : 0
    x = collider.a.x + dx * fraction
    y = collider.a.y + dy * fraction
    combinedRadius += collider.radius
  } else {
    x = collider.x
    y = collider.y
    combinedRadius += collider.radius
  }
  const dx = point.x - x, dy = point.y - y
  // This cheap squared-distance rejection covers almost all static props.
  const squaredDistance = dx * dx + dy * dy
  if (squaredDistance >= combinedRadius * combinedRadius) return null
  const distance = Math.sqrt(squaredDistance)
  if (distance < EPSILON) return { nx: 1, ny: 0, depth: combinedRadius }
  return { nx: dx / distance, ny: dy / distance, depth: combinedRadius - distance }
}

export function advanceWithCollisions(position: Point, velocity: Point, heading: number, delta: number, colliders: readonly Collider[]) {
  const result = { x: position.x, y: position.y, vx: velocity.x, vy: velocity.y, impact: 0 }
  const fx = Math.cos(heading), fy = Math.sin(heading)
  // Subdivide long moves so a thin barrier cannot be skipped at high speed.
  const steps = Math.max(1, Math.ceil(Math.hypot(velocity.x, velocity.y) * delta / 4))
  for (let step = 0; step < steps; step++) {
    result.x += result.vx * delta / steps
    result.y += result.vy * delta / steps
    for (let pass = 0; pass < 4; pass++) {
      let touched = false
      for (const collider of colliders) {
        for (const offset of BODY_OFFSETS) {
          const hit = contact({ x: result.x + fx * offset, y: result.y + fy * offset }, CAR_RADIUS, collider)
          if (!hit) continue
          touched = true
          result.x += hit.nx * (hit.depth + EPSILON)
          result.y += hit.ny * (hit.depth + EPSILON)
          const inwardSpeed = result.vx * hit.nx + result.vy * hit.ny
          if (inwardSpeed < 0) {
            result.impact = Math.max(result.impact, -inwardSpeed)
            result.vx -= hit.nx * inwardSpeed * 1.12
            result.vy -= hit.ny * inwardSpeed * 1.12
            if (inwardSpeed < -20) { result.vx *= 0.85; result.vy *= 0.85 }
          }
        }
      }
      if (!touched) break
    }
  }
  return result
}
