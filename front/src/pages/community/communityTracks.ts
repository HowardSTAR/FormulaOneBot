import definitions from '../../../../app/race_tracks.json';
const scenery = import.meta.glob<string>('../../assets/community/*.webp', { eager: true, query: '?url', import: 'default' });
export const communityTracks = definitions;
export const communityTrackImage = (id: string) => scenery[`../../assets/community/${id}.webp`];

/** Constant-speed preview of the actual centre line, with no gameplay or score. */
export function sampleTrack(points: number[][], progress: number) {
  const segments = points.map((point, i) => {
    const next = points[(i + 1) % points.length];
    return { point, next, length: Math.hypot(next[0] - point[0], next[1] - point[1]) };
  });
  const position = progress >= 1 ? 0 : Math.max(0, progress);
  let distance = segments.reduce((sum, segment) => sum + segment.length, 0) * position;
  for (const { point, next, length } of segments) {
    if (distance <= length && length > 0) {
      return { x: point[0] + (next[0] - point[0]) * distance / length, y: point[1] + (next[1] - point[1]) * distance / length, heading: Math.atan2(next[1] - point[1], next[0] - point[0]) * 180 / Math.PI - 90 };
    }
    distance -= length;
  }
  return { x: points[0]?.[0] ?? 0, y: points[0]?.[1] ?? 0, heading: 0 };
}
