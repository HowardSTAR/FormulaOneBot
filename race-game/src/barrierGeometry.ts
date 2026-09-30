export type Point = { x: number; y: number }

function segmentDistanceSquared(point: Point, a: Point, b: Point): number {
  const dx = b.x - a.x, dy = b.y - a.y
  const length = dx * dx + dy * dy
  const t = length ? Math.max(0, Math.min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / length)) : 0
  return (point.x - a.x - dx * t) ** 2 + (point.y - a.y - dy * t) ** 2
}

function simplify(points: Point[], tolerance = 1.2): Point[] {
  if (points.length <= 2) return points
  let farthest = 0, squaredDistance = tolerance * tolerance
  for (let index = 1; index < points.length - 1; index++) {
    const candidate = segmentDistanceSquared(points[index], points[0], points[points.length - 1])
    if (candidate > squaredDistance) { squaredDistance = candidate; farthest = index }
  }
  if (!farthest) return [points[0], points[points.length - 1]]
  return [...simplify(points.slice(0, farthest + 1), tolerance).slice(0, -1), ...simplify(points.slice(farthest), tolerance)]
}

/** Boundary of the UNION of road capsules, not independent vertex offsets.
 * Nearby hairpins therefore share a clean boundary instead of crossed spikes.
 * Called once per circuit; both scenery and collision use these same contours.
 */
export function barrierContours(points: Point[], radius: number): Point[][] {
  const step = 4
  const originX = Math.floor((Math.min(...points.map(point => point.x)) - radius - step * 2) / step) * step
  const originY = Math.floor((Math.min(...points.map(point => point.y)) - radius - step * 2) / step) * step
  const columns = Math.ceil((Math.max(...points.map(point => point.x)) + radius + step * 2 - originX) / step) + 1
  const rows = Math.ceil((Math.max(...points.map(point => point.y)) + radius + step * 2 - originY) / step) + 1
  const fieldAt = (x: number, y: number): number => {
    let nearest = Infinity
    for (let index = 0; index < points.length; index++) {
      nearest = Math.min(nearest, segmentDistanceSquared({ x, y }, points[index], points[(index + 1) % points.length]))
    }
    return nearest - radius * radius
  }
  const field = new Float64Array(columns * rows)
  for (let row = 0; row < rows; row++) {
    for (let column = 0; column < columns; column++) {
      field[row * columns + column] = fieldAt(originX + column * step, originY + row * step)
    }
  }
  const nodes = new Map<string, { point: Point; neighbors: string[] }>()
  const edge = (row: number, column: number, side: number): string => {
    const horizontal = side === 0 || side === 2
    const r = row + (side === 2 ? 1 : 0), c = column + (side === 1 ? 1 : 0)
    const key = `${horizontal ? 'h' : 'v'}:${r}:${c}`
    if (!nodes.has(key)) {
      const a = field[r * columns + c], b = field[(r + Number(!horizontal)) * columns + c + Number(horizontal)]
      const t = a / (a - b)
      nodes.set(key, { point: {
        x: originX + (c + (horizontal ? t : 0)) * step,
        y: originY + (r + (horizontal ? 0 : t)) * step,
      }, neighbors: [] })
    }
    return key
  }
  const cases: Record<number, number[][]> = {
    1: [[3, 0]], 2: [[0, 1]], 3: [[3, 1]], 4: [[1, 2]], 6: [[0, 2]], 7: [[3, 2]],
    8: [[2, 3]], 9: [[0, 2]], 11: [[1, 2]], 12: [[1, 3]], 13: [[0, 1]], 14: [[0, 3]],
  }
  for (let row = 0; row < rows - 1; row++) {
    for (let column = 0; column < columns - 1; column++) {
      const mask = Number(field[row * columns + column] <= 0)
        + Number(field[row * columns + column + 1] <= 0) * 2
        + Number(field[(row + 1) * columns + column + 1] <= 0) * 4
        + Number(field[(row + 1) * columns + column] <= 0) * 8
      if (!mask || mask === 15) continue
      let pairs = cases[mask]
      if (mask === 5 || mask === 10) {
        const connected = fieldAt(originX + (column + 0.5) * step, originY + (row + 0.5) * step) <= 0
        pairs = (mask === 5) === connected ? [[0, 1], [2, 3]] : [[3, 0], [1, 2]]
      }
      for (const [start, end] of pairs) {
        const a = edge(row, column, start), b = edge(row, column, end)
        nodes.get(a)!.neighbors.push(b)
        nodes.get(b)!.neighbors.push(a)
      }
    }
  }
  const contours: Point[][] = []
  const visited = new Set<string>()
  for (const start of nodes.keys()) {
    if (visited.has(start)) continue
    let current = start, previous = ''
    const contour: Point[] = []
    do {
      const node = nodes.get(current)!
      visited.add(current)
      contour.push(node.point)
      const next = node.neighbors.find(neighbor => neighbor !== previous)
      if (!next) break
      previous = current
      current = next
    } while (current !== start && !visited.has(current))
    if (current === start && contour.length > 3) {
      contour.push(contour[0])
      contours.push(simplify(contour))
    }
  }
  return contours
}
