import Phaser from 'phaser'
import { trackWalls, type Track, type TrackObject } from './tracks'

function drawGrandstand(graphics: Phaser.GameObjects.Graphics, object: TrackObject): void {
  const { x, y } = object, width = object.width!, height = object.height!
  const north = object.facing === 'north'
  graphics.fillStyle(0x18272a).fillRect(x + 5, y + 6, width, height)
  graphics.fillStyle(0xa59c83).fillRect(x, y, width, height)
  graphics.lineStyle(3, 0x253b3a).strokeRect(x, y, width, height)
  const roofY = north ? y + height - 14 : y
  const seatingY = north ? y + 5 : y + 19
  graphics.fillStyle(0x244f53).fillRect(x - 4, roofY, width + 8, 14)
  graphics.lineStyle(1, 0x65949a)
  for (let beam = x + 8; beam < x + width; beam += 18) graphics.lineBetween(beam, roofY + 2, beam, roofY + 12)
  const fans = [0xf0ce80, 0xe9e2cc, 0xd45c4b, 0x367e93, 0x222c38, 0x95ad82]
  for (let row = 0; row < 4; row++) {
    const seatY = seatingY + row * 8
    graphics.fillStyle(row % 2 ? 0x566768 : 0x71807b).fillRect(x + 4, seatY, width - 8, 7)
    for (let column = 0; column < Math.floor((width - 12) / 9); column++) {
      const seatX = x + 7 + column * 9
      // Aisles stay empty; deterministic crowd is baked, not animated.
      if (column % 16 < 2) { graphics.fillStyle(0xc5b997).fillRect(seatX, seatY, 7, 7); continue }
      graphics.fillStyle(fans[(column * 7 + row * 11) % fans.length]).fillRect(seatX, seatY + 2, 5, 4)
      graphics.fillStyle(0xe0b69a).fillRect(seatX + 1, seatY, 3, 2)
    }
  }
  const frontY = north ? y + 2 : y + height - 3
  graphics.lineStyle(3, 0xe7d9b5).lineBetween(x, frontY, x + width, frontY)
  graphics.lineStyle(2, 0x233a36)
  for (let post = x + 8; post < x + width; post += 35) graphics.lineBetween(post, frontY - 3, post, frontY + 3)
}

function drawPitBuilding(graphics: Phaser.GameObjects.Graphics, object: TrackObject): void {
  const { x, y } = object, width = object.width!, height = object.height!
  graphics.fillStyle(0x192b2b).fillRect(x + 6, y + 6, width, height)
  graphics.fillStyle(0xafa994).fillRect(x, y, width, height)
  graphics.fillStyle(0x355b5c).fillRect(x - 3, y - 3, width + 6, height * 0.48)
  graphics.lineStyle(2, 0x75999a)
  for (let rib = x + 6; rib < x + width; rib += 13) graphics.lineBetween(rib, y + 1, rib, y + height * 0.42)
  const colors = [0xe2bd63, 0x59a8bb, 0xc86054, 0x7ca885, 0xddd7bf]
  for (let bay = 0; bay < 10; bay++) {
    const bayX = x + 7 + bay * (width - 14) / 10, bayWidth = (width - 14) / 10 - 5
    graphics.fillStyle(0x1d2d32).fillRect(bayX, y + height * 0.53, bayWidth, height * 0.37)
    graphics.fillStyle(colors[bay % colors.length]).fillRect(bayX, y + height * 0.48, bayWidth, 6)
    graphics.lineStyle(1, 0x667978)
    for (let stripe = y + height * 0.58; stripe < y + height * 0.9; stripe += 7) graphics.lineBetween(bayX + 2, stripe, bayX + bayWidth - 2, stripe)
  }
}

function drawOvalGround(graphics: Phaser.GameObjects.Graphics): void {
  // Mown infield, walking paths and service parking are all non-solid scenery.
  graphics.fillStyle(0x566d45).fillEllipse(768, 500, 1100, 500)
  for (let stripe = 0; stripe < 11; stripe++) {
    graphics.fillStyle(stripe % 2 ? 0x5d764a : 0x516944).fillRect(325 + stripe * 80, 305, 80, 390)
  }
  graphics.fillStyle(0xb29e75).fillRect(380, 408, 760, 35).fillRect(395, 561, 730, 34)
  graphics.fillStyle(0x8f947e).fillRect(403, 445, 700, 111)
  graphics.lineStyle(2, 0xd5c7a2)
  for (let x = 470; x < 1040; x += 50) {
    graphics.lineBetween(x, 418, x, 438)
    graphics.lineBetween(x, 568, x, 590)
  }
  // Planters, plazas and sun-faded patches break up the empty brown ground.
  for (const x of [365, 1160]) {
    for (const y of [340, 605]) {
      graphics.fillStyle(0xc3b187).fillRoundedRect(x - 24, y - 17, 48, 34, 5)
      graphics.fillStyle(0x3f6347).fillRoundedRect(x - 20, y - 13, 40, 26, 4)
      for (let flower = 0; flower < 9; flower++) graphics.fillStyle(flower % 2 ? 0xf3d677 : 0xd77e59).fillRect(x - 15 + flower * 4, y - 7 + flower % 3 * 5, 3, 3)
    }
  }
}

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
      sunset: { ground: 0x8b7551, verge: 0xb69a67, road: 0x333b42, detail: 0x9c835b },
      canyon: { ground: 0x775043, verge: 0xb98c64, road: 0x373b40, detail: 0x8b6150 },
      harbor: { ground: 0x243c47, verge: 0x6f7d80, road: 0x323942, detail: 0x2e4851 },
    }
    const palette = palettes[track.theme]
    graphics.fillStyle(palette.ground).fillRect(0, 0, 1536, 1024)
    // Deterministic low-cost pixel texture, not a live particle layer.
    for (let index = 0; index < 720; index++) {
      graphics.fillStyle(palette.detail, 0.6).fillRect((index * 127) % 1536, (index * 197) % 1024, 6, 4)
    }
    if (track.theme === 'sunset') drawOvalGround(graphics)
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
      // Round joins prevent the renderer itself from producing miter spikes.
      graphics.lineStyle(14, 0x131d23, 1)
      for (let index = 1; index < path.length; index++) graphics.lineBetween(path[index - 1].x, path[index - 1].y, path[index].x, path[index].y)
      graphics.fillStyle(0x131d23)
      for (const point of path) graphics.fillCircle(point.x, point.y, 7)
      let travelled = 0
      for (let index = 1; index < path.length; index++) {
        const a = path[index - 1], b = path[index]
        const length = Math.hypot(b.x - a.x, b.y - a.y)
        for (let at = 0; at < length - 1e-7;) {
          const stripe = Math.floor((travelled + at + 1e-7) / 22)
          const color = stripe % 2 ? 0xd9dad2 : 0xce534b
          const until = Math.min(length, (stripe + 1) * 22 - travelled)
          const x = a.x + (b.x - a.x) * at / length, y = a.y + (b.y - a.y) * at / length
          graphics.lineStyle(10, color).lineBetween(x, y,
            a.x + (b.x - a.x) * until / length, a.y + (b.y - a.y) * until / length)
          graphics.fillStyle(color).fillCircle(x, y, 5)
          at = until
        }
        travelled += length
      }
    }
    for (const object of track.objects) {
      const { x, y } = object
      if (object.kind === 'grandstand') {
        drawGrandstand(graphics, object)
      } else if (object.kind === 'pitbuilding') {
        drawPitBuilding(graphics, object)
      } else if (object.kind === 'scoreboard') {
        const boardHeight = object.height! - 20
        graphics.fillStyle(0x192c30).fillRect(x + 12, y + boardHeight, 6, 20).fillRect(x + object.width! - 18, y + boardHeight, 6, 20)
        graphics.fillStyle(0x15252a).fillRect(x, y, object.width!, boardHeight)
        graphics.lineStyle(3, 0xb0b197).strokeRect(x, y, object.width!, boardHeight)
        for (let row = 0; row < 3; row++) {
          graphics.fillStyle(row ? 0xd8ba6d : 0xf48358).fillRect(x + 7, y + 6 + row * 11, 9, 5)
          graphics.fillStyle(0x81bc9b).fillRect(x + 23, y + 6 + row * 11, 36 - row * 6, 5)
        }
      } else if (object.kind === 'servicevehicle') {
        const colors = [0xe5d7b6, 0x4e8390, 0xd58e56, 0xe6cf80, 0x667b6c]
        graphics.fillStyle(0x283836).fillRect(x + 2, y + 3, object.width!, object.height!)
        graphics.fillStyle(colors[Math.floor(x / 64) % colors.length]).fillRect(x, y, object.width!, object.height!)
        graphics.fillStyle(0x234651).fillRect(x + object.width! - 8, y + 2, 6, object.height! - 4)
        graphics.fillStyle(0x17282b).fillRect(x + 5, y - 2, 5, 3).fillRect(x + object.width! - 9, y + object.height! - 2, 5, 3)
      } else if (object.kind === 'marshal') {
        graphics.fillStyle(0x243b39).fillRect(x, y, object.width!, object.height!)
        graphics.fillStyle(0xd8d0ad).fillRect(x + 3, y + 8, object.width! - 6, object.height! - 8)
        graphics.fillStyle(0x456769).fillRect(x - 3, y, object.width! + 6, 9)
        graphics.fillStyle(0xdf854e).fillRect(x + 9, y + 14, 7, 11)
        graphics.fillStyle(0xf1cf96).fillRect(x + 10, y + 12, 5, 3)
      } else if (object.kind === 'light') {
        graphics.fillStyle(0x243637).fillCircle(x, y, 5)
        graphics.lineStyle(3, 0x52615c).lineBetween(x, y, x - 9, y - 22)
        graphics.fillStyle(0xe6dec0).fillRect(x - 18, y - 26, 23, 6)
      } else if (object.kind === 'building') {
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
