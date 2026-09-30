import Phaser from 'phaser'
import { trackWalls, type Track } from './tracks'

// Draw once, bake to a texture, then dispose the graphics. No per-frame scenery work.
export function drawTrack(scene: Phaser.Scene, track: Track): void {
  if (track.image) {
    scene.add.image(0, 0, 'track').setOrigin(0).setDisplaySize(1536, 1024)
    return
  }
  const key = `scenery-${track.id}`
  if (!scene.textures.exists(key)) {
    const graphics = scene.make.graphics({ x: 0, y: 0 })
    const palettes: Record<string, { ground: number; verge: number; road: number; detail: number }> = {
      sunset: { ground: 0x644535, verge: 0xaa8354, road: 0x333b42, detail: 0x74563d },
      canyon: { ground: 0x775043, verge: 0xb98c64, road: 0x373b40, detail: 0x8b6150 },
      harbor: { ground: 0x243c47, verge: 0x6f7d80, road: 0x323942, detail: 0x2e4851 },
    }
    const palette = palettes[track.theme]
    graphics.fillStyle(palette.ground).fillRect(0, 0, 1536, 1024)
    // Deterministic low-cost pixel texture, not a live particle layer.
    for (let index = 0; index < 720; index++) {
      graphics.fillStyle(palette.detail, 0.6).fillRect((index * 127) % 1536, (index * 197) % 1024, 6, 4)
    }
    if (track.theme === 'harbor') {
      graphics.fillStyle(0x12364c).fillRect(1380, 0, 156, 1024)
      graphics.lineStyle(3, 0x32617b, 0.8)
      for (let y = 20; y < 1024; y += 32) graphics.lineBetween(1400, y, 1520, y)
    }
    const points = track.centerLine.map(([x, y]) => new Phaser.Math.Vector2(x, y))
    const strokeRoad = (width: number, color: number) => {
      graphics.lineStyle(width, color, 1)
      graphics.strokePoints(points, true)
      // Rounded joins make the rendered surface match distance-to-polyline driving.
      graphics.fillStyle(color)
      for (const point of points) graphics.fillCircle(point.x, point.y, width / 2)
    }
    strokeRoad(track.roadHalfWidth * 2 + 34, palette.verge)
    strokeRoad(track.roadHalfWidth * 2 + 10, 0xd9d4c2)
    strokeRoad(track.roadHalfWidth * 2, palette.road)
    graphics.lineStyle(2, 0x7e8686, 0.35)
    graphics.strokePoints(points, true)
    for (const path of trackWalls(track)) {
      graphics.lineStyle(14, 0x131d23, 1).strokePoints(path)
      for (let index = 1; index < path.length; index++) {
        const a = path[index - 1], b = path[index]
        const count = Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / 22)
        for (let part = 0; part < count; part++) {
          graphics.lineStyle(10, part % 2 ? 0xd9dad2 : 0xce534b)
          graphics.lineBetween(a.x + (b.x - a.x) * part / count, a.y + (b.y - a.y) * part / count,
            a.x + (b.x - a.x) * (part + 1) / count, a.y + (b.y - a.y) * (part + 1) / count)
        }
      }
    }
    for (const object of track.objects) {
      const { x, y } = object
      if (object.kind === 'building') {
        const width = object.width!, height = object.height!
        graphics.fillStyle(0x172126).fillRect(x + 5, y + 6, width, height)
        graphics.fillStyle(track.theme === 'harbor' ? 0x487483 : 0x70655b).fillRect(x, y, width, height)
        graphics.lineStyle(4, 0x18292e).strokeRect(x, y, width, height)
        graphics.lineStyle(2, 0x9eb0a6, 0.5)
        for (let row = y + 10; row < y + height; row += 14) graphics.lineBetween(x + 4, row, x + width - 4, row)
      } else if (object.kind === 'tree') {
        graphics.fillStyle(0x222e20).fillCircle(x + 4, y + 6, object.radius! + 2)
        graphics.fillStyle(0x3d6243).fillCircle(x, y, object.radius!)
        graphics.fillStyle(0x63844c).fillCircle(x - 5, y - 5, object.radius! * 0.6)
      } else {
        graphics.fillStyle(0x423834).fillCircle(x + 4, y + 5, object.radius!)
        graphics.fillStyle(track.theme === 'harbor' ? 0x617279 : 0xa07b64).fillCircle(x, y, object.radius!)
        graphics.fillStyle(0xc0a080, 0.5).fillCircle(x - 7, y - 6, object.radius! * 0.5)
      }
    }
    const { x, minY, maxY } = track.finishLine
    for (let y = minY; y < maxY; y += 8) {
      graphics.fillStyle(0xf8f0d8).fillRect(x - 8 + (Math.floor((y - minY) / 8) % 2) * 8, y, 8, Math.min(8, maxY - y))
      graphics.fillStyle(0x131d23).fillRect(x - (Math.floor((y - minY) / 8) % 2) * 8, y, 8, Math.min(8, maxY - y))
    }
    graphics.generateTexture(key, 1536, 1024)
    graphics.destroy()
  }
  scene.add.image(0, 0, key).setOrigin(0)
}
