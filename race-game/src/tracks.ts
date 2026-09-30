import definitions from '../../app/race_tracks.json'
import type { Collider, Point } from './collisions'

export type TrackObject = { kind: string; x: number; y: number; width?: number; height?: number; radius?: number }
export type Track = {
  id: string; name: string; format: string; theme: string; accent: string; description: string
  roadHalfWidth: number; image?: string; autoBarriers: boolean
  centerLine: number[][]; checkpointIndexes: number[]
  finishLine: { x: number; minY: number; maxY: number }
  objects: TrackObject[]; barrierPaths: number[][][]
}
export const tracks: Track[] = definitions

export function offsetLoop(points: Point[], offset: number): Point[] {
  return points.map((point, index) => {
    const before = points[(index + points.length - 1) % points.length]
    const after = points[(index + 1) % points.length]
    const ax = point.x - before.x, ay = point.y - before.y
    const bx = after.x - point.x, by = after.y - point.y
    const al = Math.hypot(ax, ay), bl = Math.hypot(bx, by)
    const nx = -ay / al - by / bl, ny = ax / al + bx / bl
    const length = Math.hypot(nx, ny)
    const ux = nx / length, uy = ny / length
    const miter = offset / Math.max(0.5, (ux * -by + uy * bx) / bl)
    return { x: point.x + ux * miter, y: point.y + uy * miter }
  })
}

export function trackWalls(track: Track): Point[][] {
  const walls = track.barrierPaths.map(path => path.map(([x, y]) => ({ x, y })))
  if (track.autoBarriers) {
    const points = track.centerLine.map(([x, y]) => ({ x, y }))
    for (const offset of [-track.roadHalfWidth - 30, track.roadHalfWidth + 30]) {
      const loop = offsetLoop(points, offset)
      walls.push([...loop, loop[0]])
    }
  }
  return walls
}

export function trackColliders(track: Track): Collider[] {
  const props: Collider[] = track.objects.map(object => object.kind === 'building'
    ? { type: 'rect', x: object.x, y: object.y, width: object.width!, height: object.height! }
    : { type: 'circle', x: object.x, y: object.y, radius: object.radius! })
  for (const path of trackWalls(track)) {
    for (let index = 1; index < path.length; index++) {
      props.push({ type: 'wall', a: path[index - 1], b: path[index], radius: 6 })
    }
  }
  // The edge of the world is a wall, not a place to disappear or clip through.
  const border = [{ x: 8, y: 8 }, { x: 1528, y: 8 }, { x: 1528, y: 1016 }, { x: 8, y: 1016 }, { x: 8, y: 8 }]
  for (let index = 1; index < border.length; index++) props.push({ type: 'wall', a: border[index - 1], b: border[index], radius: 6 })
  return props
}
