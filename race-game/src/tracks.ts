import definitions from '../../app/race_tracks.json'
import type { Collider, Point } from './collisions'
import { barrierContours } from './barrierGeometry'

export type TrackObject = { kind: string; x: number; y: number; width?: number; height?: number; radius?: number; facing?: string }
export type Track = {
  id: string; name: string; format: string; theme: string; accent: string; description: string
  roadHalfWidth: number; image?: string; autoBarriers: boolean
  centerLine: number[][]; checkpointIndexes: number[]
  finishLine: { x: number; minY: number; maxY: number }
  objects: TrackObject[]; barrierPaths: number[][][]
}
export const tracks: Track[] = definitions

const wallCache = new WeakMap<Track, Point[][]>()

export function trackWalls(track: Track): Point[][] {
  const cached = wallCache.get(track)
  if (cached) return cached
  const walls = track.barrierPaths.map(path => path.map(([x, y]) => ({ x, y })))
  if (track.autoBarriers) {
    const points = track.centerLine.map(([x, y]) => ({ x, y }))
    walls.push(...barrierContours(points, track.roadHalfWidth + 30))
  }
  wallCache.set(track, walls)
  return walls
}

export function trackColliders(track: Track): Collider[] {
  const props: Collider[] = track.objects.map(object => object.width !== undefined && object.height !== undefined
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
