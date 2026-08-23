import Phaser from 'phaser'
import './style.css'

const WORLD_WIDTH = 1536
const WORLD_HEIGHT = 1024
const TOTAL_LAPS = 3
const ROAD_HALF_WIDTH = 54
const BEST_TIME_KEY = 'emerald-loop-best-time'
const GHOST_ENABLED_KEY = 'emerald-loop-ghost-enabled'
const TRACK_ID = 'emerald-loop-v1'
const TELEMETRY_SAMPLE_INTERVAL_MS = 100
const MAX_TELEMETRY_SAMPLES = 6000

type RaceState = 'ready' | 'countdown' | 'racing' | 'paused' | 'finished'

type TouchControl = 'left' | 'right' | 'throttle' | 'brake'

type LeaderboardEntry = {
  place: number
  telegram_id: number
  name: string
  time_ms: number
  is_me: boolean
}

type LeaderboardResponse = {
  entries: LeaderboardEntry[]
  me: LeaderboardEntry | null
  ghost: GhostRun | null
  track_id: string
}

type GhostSample = {
  t: number
  x: number
  y: number
  rotation: number
}

type GhostRun = {
  name: string
  time_ms: number
  samples: GhostSample[]
  leaderboard_place?: number | null
  is_global_best?: boolean
}

const touchState: Record<TouchControl, boolean> = {
  left: false,
  right: false,
  throttle: false,
  brake: false,
}

const centerLine = [
  new Phaser.Math.Vector2(875, 660),
  new Phaser.Math.Vector2(1080, 660),
  new Phaser.Math.Vector2(1190, 655),
  new Phaser.Math.Vector2(1260, 630),
  new Phaser.Math.Vector2(1295, 580),
  new Phaser.Math.Vector2(1310, 515),
  new Phaser.Math.Vector2(1310, 410),
  new Phaser.Math.Vector2(1307, 320),
  new Phaser.Math.Vector2(1290, 250),
  new Phaser.Math.Vector2(1250, 205),
  new Phaser.Math.Vector2(1180, 181),
  new Phaser.Math.Vector2(1090, 180),
  new Phaser.Math.Vector2(1015, 193),
  new Phaser.Math.Vector2(930, 225),
  new Phaser.Math.Vector2(840, 267),
  new Phaser.Math.Vector2(755, 304),
  new Phaser.Math.Vector2(680, 320),
  new Phaser.Math.Vector2(600, 320),
  new Phaser.Math.Vector2(530, 300),
  new Phaser.Math.Vector2(465, 266),
  new Phaser.Math.Vector2(405, 229),
  new Phaser.Math.Vector2(345, 193),
  new Phaser.Math.Vector2(295, 179),
  new Phaser.Math.Vector2(251, 188),
  new Phaser.Math.Vector2(218, 221),
  new Phaser.Math.Vector2(198, 275),
  new Phaser.Math.Vector2(192, 350),
  new Phaser.Math.Vector2(192, 455),
  new Phaser.Math.Vector2(198, 535),
  new Phaser.Math.Vector2(220, 595),
  new Phaser.Math.Vector2(266, 634),
  new Phaser.Math.Vector2(340, 655),
  new Phaser.Math.Vector2(510, 660),
  new Phaser.Math.Vector2(690, 660),
]

const checkpointIndexes = [0, 7, 16, 24, 31, 0]
const checkpoints = checkpointIndexes.map((index) => centerLine[index])

const $ = <T extends HTMLElement>(selector: string): T => {
  const element = document.querySelector<T>(selector)
  if (!element) throw new Error(`Не найден элемент интерфейса: ${selector}`)
  return element
}

const ui = {
  lap: $('#lap-value'),
  time: $('#time-value'),
  speed: $('#speed-value'),
  surface: $('#surface-chip'),
  surfaceLabel: $('#surface-chip b'),
  countdown: $('#countdown'),
  modal: $('#race-modal'),
  modalTitle: $('#modal-title'),
  modalCopy: $('#modal-copy'),
  resultRow: $('#result-row'),
  resultTime: $('#result-time'),
  bestTime: $('#best-time'),
  start: $('#start-button') as HTMLButtonElement,
  menu: $('#game-menu'),
  menuButton: $('#menu-button') as HTMLButtonElement,
  menuClose: $('#menu-close-button') as HTMLButtonElement,
  menuBackdrop: $('#menu-backdrop') as HTMLButtonElement,
  menuContinue: $('#menu-continue-button') as HTMLButtonElement,
  menuLeaderboard: $('#menu-leaderboard-button') as HTMLButtonElement,
  introLeaderboard: $('#intro-leaderboard-button') as HTMLButtonElement,
  menuMainView: $('#menu-main-view'),
  leaderboardView: $('#menu-leaderboard-view'),
  leaderboardBack: $('#leaderboard-back-button') as HTMLButtonElement,
  leaderboardList: $('#leaderboard-list'),
  leaderboardMyPlace: $('#leaderboard-my-place'),
  reset: $('#reset-button') as HTMLButtonElement,
  pause: $('#pause-button') as HTMLButtonElement,
  ghostHudToggle: $('#ghost-hud-toggle') as HTMLButtonElement,
  ghostMenuToggle: $('#menu-ghost-toggle') as HTMLButtonElement,
  ghostMenuLabel: $('#menu-ghost-label'),
  ghostMenuCopy: $('#menu-ghost-copy'),
}

const readGhostPreference = (): boolean => {
  try {
    return localStorage.getItem(GHOST_ENABLED_KEY) !== 'false'
  } catch {
    return true
  }
}

let ghostEnabled = readGhostPreference()

const persistGhostPreference = (): void => {
  try {
    localStorage.setItem(GHOST_ENABLED_KEY, String(ghostEnabled))
  } catch { /* localStorage can be unavailable in privacy mode */ }
}

const syncGhostControls = (ghost: GhostRun | null): void => {
  const available = Boolean(ghost?.samples?.length)
  const pressed = String(ghostEnabled)
  ui.ghostHudToggle.setAttribute('aria-pressed', pressed)
  ui.ghostMenuToggle.setAttribute('aria-pressed', pressed)
  ui.ghostHudToggle.classList.toggle('is-unavailable', !available)
  ui.ghostHudToggle.textContent = `GHOST ${ghostEnabled ? 'ON' : 'OFF'}`
  ui.ghostMenuLabel.textContent = `Ghost Racer: ${ghostEnabled ? 'ON' : 'OFF'}`
  ui.ghostMenuCopy.textContent = available && ghost
    ? `${ghost.is_global_best ? '#1' : 'Лучший доступный'} ${ghost.name} · ${formatTime(ghost.time_ms)}`
    : 'Лучший заезд с телеметрией пока недоступен'
}

const formatTime = (milliseconds: number): string => {
  const safeMilliseconds = Math.max(0, milliseconds)
  const minutes = Math.floor(safeMilliseconds / 60_000)
  const seconds = Math.floor((safeMilliseconds % 60_000) / 1_000)
  const millis = Math.floor(safeMilliseconds % 1_000)
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}.${millis.toString().padStart(3, '0')}`
}

const assetUrl = (filename: string): string => new URL(`./assets/${filename}`, window.location.href).toString()

const readCookie = (name: string): string | null => {
  const prefix = `${encodeURIComponent(name)}=`
  const item = document.cookie.split('; ').find((value) => value.startsWith(prefix))
  return item ? decodeURIComponent(item.slice(prefix.length)) : null
}

const getTelegramInitData = (): string => {
  type TelegramWindow = Window & { Telegram?: { WebApp?: { initData?: string } } }
  const current = (window as TelegramWindow).Telegram?.WebApp?.initData
  if (current) return current
  try {
    return ((window.parent as TelegramWindow).Telegram?.WebApp?.initData) ?? ''
  } catch {
    return ''
  }
}

const apiRequest = async <T>(endpoint: string, body?: unknown): Promise<T> => {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const initData = getTelegramInitData()
  const csrf = readCookie('turbotears_csrf')
  if (initData) headers['X-Telegram-Init-Data'] = initData
  if (csrf) headers['X-CSRF-Token'] = csrf

  const response = await fetch(endpoint, {
    method: body ? 'POST' : 'GET',
    headers,
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) {
    let message = response.status === 401
      ? 'Войдите в аккаунт, чтобы сохранить результат.'
      : `Не удалось загрузить рейтинг (${response.status}).`
    try {
      const payload = await response.json() as { detail?: string | { message?: string } }
      message = typeof payload.detail === 'string' ? payload.detail : payload.detail?.message || message
    } catch { /* ответ без JSON */ }
    throw new Error(message)
  }
  return await response.json() as T
}

const showMenuView = (view: 'main' | 'leaderboard'): void => {
  ui.menuMainView.hidden = view !== 'main'
  ui.leaderboardView.hidden = view !== 'leaderboard'
}

const renderLeaderboard = (data: LeaderboardResponse): void => {
  ui.leaderboardList.replaceChildren()
  ui.leaderboardMyPlace.textContent = data.me ? `Ваше место: #${data.me.place}` : 'Нет результата'

  if (data.entries.length === 0) {
    const message = document.createElement('div')
    message.className = 'leaderboard-message'
    message.textContent = 'Пока нет результатов. Станьте первым на трассе!'
    ui.leaderboardList.append(message)
    return
  }

  data.entries.forEach((entry) => {
    const row = document.createElement('div')
    row.className = `leaderboard-row${entry.is_me ? ' is-me' : ''}${entry.place <= 3 ? ' is-top' : ''}`

    const place = document.createElement('span')
    place.className = 'leaderboard-place'
    place.textContent = `#${entry.place}`

    const name = document.createElement('span')
    name.className = 'leaderboard-name'
    name.textContent = entry.name

    const time = document.createElement('span')
    time.className = 'leaderboard-time'
    time.textContent = formatTime(entry.time_ms)

    row.append(place, name, time)
    ui.leaderboardList.append(row)
  })
}

const loadLeaderboard = async (): Promise<void> => {
  ui.leaderboardList.innerHTML = '<div class="leaderboard-message">Загрузка результатов…</div>'
  try {
    renderLeaderboard(await apiRequest<LeaderboardResponse>('/api/race-game-leaderboard'))
  } catch (error) {
    ui.leaderboardMyPlace.textContent = '—'
    ui.leaderboardList.innerHTML = ''
    const message = document.createElement('div')
    message.className = 'leaderboard-message'
    message.textContent = error instanceof Error ? error.message : 'Не удалось загрузить таблицу лидеров.'
    ui.leaderboardList.append(message)
  }
}

const loadGhost = async (): Promise<void> => {
  try {
    const data = await apiRequest<LeaderboardResponse>(`/api/race-game-leaderboard?track_id=${encodeURIComponent(TRACK_ID)}`)
    activeScene?.setGhost(data.ghost)
  } catch {
    activeScene?.setGhost(null)
  }
}

const submitRaceTime = async (timeMs: number, telemetry: GhostSample[]): Promise<boolean> => {
  try {
    const response = await apiRequest<{ saved: boolean }>('/api/race-game-leaderboard/score', {
      time_ms: Math.round(timeMs),
      track_id: TRACK_ID,
      telemetry,
    })
    return response.saved
  } catch {
    return false
  }
}

const distanceToSegment = (
  pointX: number,
  pointY: number,
  start: Phaser.Math.Vector2,
  end: Phaser.Math.Vector2,
): { distance: number; x: number; y: number; heading: number } => {
  const segmentX = end.x - start.x
  const segmentY = end.y - start.y
  const lengthSquared = segmentX * segmentX + segmentY * segmentY
  const projection = lengthSquared === 0
    ? 0
    : Phaser.Math.Clamp(((pointX - start.x) * segmentX + (pointY - start.y) * segmentY) / lengthSquared, 0, 1)
  const nearestX = start.x + segmentX * projection
  const nearestY = start.y + segmentY * projection

  return {
    distance: Phaser.Math.Distance.Between(pointX, pointY, nearestX, nearestY),
    x: nearestX,
    y: nearestY,
    heading: Math.atan2(segmentY, segmentX),
  }
}

const nearestTrackPoint = (x: number, y: number) => {
  let nearest = { distance: Number.POSITIVE_INFINITY, x: centerLine[0].x, y: centerLine[0].y, heading: 0 }

  for (let index = 0; index < centerLine.length; index += 1) {
    const candidate = distanceToSegment(x, y, centerLine[index], centerLine[(index + 1) % centerLine.length])
    if (candidate.distance < nearest.distance) nearest = candidate
  }

  return nearest
}

class RaceScene extends Phaser.Scene {
  private car!: Phaser.GameObjects.Image
  private ghostCar!: Phaser.GameObjects.Image
  private ghostLabel!: Phaser.GameObjects.Text
  private dust!: Phaser.GameObjects.Particles.ParticleEmitter
  private keys!: Record<'up' | 'down' | 'left' | 'right' | 'w' | 'a' | 's' | 'd' | 'space' | 'p' | 'r', Phaser.Input.Keyboard.Key>
  private velocity = new Phaser.Math.Vector2()
  private heading = 0
  private raceState: RaceState = 'ready'
  private countdownRemaining = 0
  private goFlashRemaining = 0
  private elapsedTime = 0
  private currentLap = 1
  private nextCheckpoint = 1
  private onRoad = true
  private stateBeforeMenu: RaceState | null = null
  private ghost: GhostRun | null = null
  private ghostSampleIndex = 0
  private telemetry: GhostSample[] = []
  private lastTelemetrySampleAt = -TELEMETRY_SAMPLE_INTERVAL_MS

  constructor() {
    super('race')
  }

  preload(): void {
    this.load.image('track', assetUrl('emerald-loop-track.png'))
    this.load.image('car', assetUrl('open-wheel-car.png'))
  }

  create(): void {
    this.add.image(0, 0, 'track').setOrigin(0).setDisplaySize(WORLD_WIDTH, WORLD_HEIGHT)

    const dustPixel = this.make.graphics({ x: 0, y: 0 })
    dustPixel.fillStyle(0xd2b77d, 1)
    dustPixel.fillStyle(0xe0c48c, 0.92)
    dustPixel.fillCircle(9, 9, 9)
    dustPixel.generateTexture('dust-pixel', 18, 18)
    dustPixel.destroy()

    this.dust = this.add.particles(0, 0, 'dust-pixel', {
      speed: { min: 22, max: 72 },
      lifespan: { min: 520, max: 980 },
      scale: { start: 1.25, end: 0.18 },
      alpha: { start: 0.78, end: 0 },
      quantity: 0,
      frequency: -1,
      blendMode: Phaser.BlendModes.NORMAL,
    }).setDepth(8)

    this.car = this.add.image(centerLine[0].x, centerLine[0].y, 'car')
      .setDisplaySize(46, 69)
      .setDepth(10)

    this.ghostCar = this.add.image(centerLine[0].x, centerLine[0].y, 'car')
      .setDisplaySize(50, 75)
      .setDepth(11)
      .setTint(0x79e9ff)
      .setAlpha(0.5)
      .setVisible(false)

    this.ghostLabel = this.add.text(centerLine[0].x, centerLine[0].y - 44, '', {
      color: '#b9f6ff',
      backgroundColor: 'rgba(2, 20, 25, 0.78)',
      fontFamily: 'Inter, system-ui, sans-serif',
      fontSize: '11px',
      fontStyle: 'bold',
      padding: { x: 6, y: 3 },
    })
      .setOrigin(0.5, 1)
      .setDepth(12)
      .setAlpha(0.9)
      .setVisible(false)

    this.keys = this.input.keyboard!.addKeys({
      up: Phaser.Input.Keyboard.KeyCodes.UP,
      down: Phaser.Input.Keyboard.KeyCodes.DOWN,
      left: Phaser.Input.Keyboard.KeyCodes.LEFT,
      right: Phaser.Input.Keyboard.KeyCodes.RIGHT,
      w: Phaser.Input.Keyboard.KeyCodes.W,
      a: Phaser.Input.Keyboard.KeyCodes.A,
      s: Phaser.Input.Keyboard.KeyCodes.S,
      d: Phaser.Input.Keyboard.KeyCodes.D,
      space: Phaser.Input.Keyboard.KeyCodes.SPACE,
      p: Phaser.Input.Keyboard.KeyCodes.P,
      r: Phaser.Input.Keyboard.KeyCodes.R,
    }) as RaceScene['keys']

    this.input.keyboard!.addCapture([
      Phaser.Input.Keyboard.KeyCodes.UP,
      Phaser.Input.Keyboard.KeyCodes.DOWN,
      Phaser.Input.Keyboard.KeyCodes.LEFT,
      Phaser.Input.Keyboard.KeyCodes.RIGHT,
      Phaser.Input.Keyboard.KeyCodes.SPACE,
    ])

    this.cameras.main
      .setBounds(0, 0, WORLD_WIDTH, WORLD_HEIGHT)
      .startFollow(this.car, true, 0.1, 0.1)
      .setRoundPixels(true)

    this.scale.on(Phaser.Scale.Events.RESIZE, this.updateCameraZoom, this)
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      this.scale.off(Phaser.Scale.Events.RESIZE, this.updateCameraZoom, this)
    })

    this.resetRace()
    this.updateCameraZoom()
    activeScene = this
    syncGhostControls(null)
    void loadGhost()
  }

  update(_time: number, deltaMilliseconds: number): void {
    const delta = Math.min(deltaMilliseconds / 1000, 0.034)

    if (Phaser.Input.Keyboard.JustDown(this.keys.r)) this.resetToTrack()
    if (Phaser.Input.Keyboard.JustDown(this.keys.p)) this.togglePause()

    if (this.raceState === 'ready' && (Phaser.Input.Keyboard.JustDown(this.keys.space) || this.keys.up.isDown || this.keys.w.isDown)) {
      this.startRace()
    }

    if (this.raceState === 'countdown') {
      this.countdownRemaining -= deltaMilliseconds
      const count = Math.max(1, Math.ceil(this.countdownRemaining / 1000))
      ui.countdown.textContent = count.toString()
      if (this.countdownRemaining <= 0) {
        this.raceState = 'racing'
        this.goFlashRemaining = 720
        ui.countdown.textContent = 'СТАРТ!'
        ui.countdown.classList.add('is-go')
        this.recordTelemetry(true)
        this.updateGhost()
      }
    } else if (this.raceState === 'racing') {
      this.elapsedTime += deltaMilliseconds
      this.updateDriving(delta)
      this.updateCheckpoints()
      this.recordTelemetry()
      this.updateGhost()
    }

    if (this.goFlashRemaining > 0) {
      this.goFlashRemaining -= deltaMilliseconds
      if (this.goFlashRemaining <= 0) {
        ui.countdown.textContent = ''
        ui.countdown.classList.remove('is-go')
      }
    }

    ui.time.textContent = formatTime(this.elapsedTime)
    const forward = new Phaser.Math.Vector2(Math.cos(this.heading), Math.sin(this.heading))
    const speed = Math.max(0, this.velocity.dot(forward))
    ui.speed.textContent = Math.round(speed * 0.86).toString()
  }

  startRace(): void {
    if (this.raceState === 'racing' || this.raceState === 'countdown') return
    if (this.raceState === 'finished') this.resetRace()

    ui.modal.classList.remove('is-visible')
    ui.countdown.classList.remove('is-go')
    this.raceState = 'countdown'
    this.countdownRemaining = 3000
    this.goFlashRemaining = 0
    ui.pause.textContent = 'Ⅱ'
  }

  setGhost(ghost: GhostRun | null): void {
    this.ghost = ghost?.samples?.length && ghost.samples.length >= 2 ? ghost : null
    this.ghostSampleIndex = 0
    this.ghostLabel?.setText(this.ghost ? `GHOST · ${this.ghost.name}` : '')
    syncGhostControls(this.ghost)
    this.updateGhost()
  }

  setGhostEnabled(enabled: boolean): void {
    ghostEnabled = enabled
    persistGhostPreference()
    syncGhostControls(this.ghost)
    this.updateGhost()
  }

  openGameMenu(showLeaderboard = false): void {
    if (!ui.menu.classList.contains('is-visible')) {
      this.stateBeforeMenu = this.raceState
      if (this.raceState === 'racing' || this.raceState === 'countdown') this.raceState = 'paused'
    }
    this.clearTouchState()
    showMenuView(showLeaderboard ? 'leaderboard' : 'main')
    ui.menu.classList.add('is-visible')
    ui.menu.setAttribute('aria-hidden', 'false')
    if (showLeaderboard) void loadLeaderboard()
  }

  closeGameMenu(): void {
    ui.menu.classList.remove('is-visible')
    ui.menu.setAttribute('aria-hidden', 'true')
    if (this.stateBeforeMenu) this.raceState = this.stateBeforeMenu
    this.stateBeforeMenu = null
  }

  togglePause(): void {
    if (this.raceState === 'racing') {
      this.raceState = 'paused'
      ui.modalTitle.textContent = 'Пауза'
      ui.modalCopy.textContent = 'Заезд остановлен. Продолжите, когда будете готовы.'
      ui.start.textContent = 'ПРОДОЛЖИТЬ'
      ui.resultRow.hidden = true
      ui.modal.classList.add('is-visible')
      ui.pause.textContent = '▶'
      this.clearTouchState()
    } else if (this.raceState === 'paused') {
      this.raceState = 'racing'
      ui.modal.classList.remove('is-visible')
      ui.pause.textContent = 'Ⅱ'
    }
  }

  resetToTrack(): void {
    if (!this.car) return
    const nearest = nearestTrackPoint(this.car.x, this.car.y)
    this.car.setPosition(nearest.x, nearest.y)
    this.heading = nearest.heading
    this.velocity.set(0, 0)
    this.updateCarRotation()
  }

  private resetRace(): void {
    this.raceState = 'ready'
    this.elapsedTime = 0
    this.currentLap = 1
    this.nextCheckpoint = 1
    this.countdownRemaining = 0
    this.goFlashRemaining = 0
    this.heading = 0
    this.velocity.set(0, 0)
    this.car.setPosition(centerLine[0].x, centerLine[0].y)
    this.updateCarRotation()
    this.clearTouchState()
    this.telemetry = []
    this.lastTelemetrySampleAt = -TELEMETRY_SAMPLE_INTERVAL_MS
    this.ghostSampleIndex = 0

    ui.lap.textContent = `1 / ${TOTAL_LAPS}`
    ui.time.textContent = formatTime(0)
    ui.speed.textContent = '0'
    ui.modalTitle.textContent = 'Emerald Loop'
    ui.modalCopy.textContent = 'Три круга по оригинальной трассе. Удерживайте скорость, аккуратно проходите повороты и не теряйте время на траве.'
    ui.start.textContent = 'НАЧАТЬ ЗАЕЗД'
    ui.resultRow.hidden = true
    ui.modal.classList.add('is-visible')
    ui.countdown.textContent = ''
    ui.countdown.classList.remove('is-go')
    ui.pause.textContent = 'Ⅱ'
    this.setSurfaceState(true)
    this.updateGhost()
  }

  private updateDriving(delta: number): void {
    const throttlePressed = this.keys.up.isDown || this.keys.w.isDown || this.keys.space.isDown || touchState.throttle
    const brakePressed = this.keys.down.isDown || this.keys.s.isDown || touchState.brake
    const leftPressed = this.keys.left.isDown || this.keys.a.isDown || touchState.left
    const rightPressed = this.keys.right.isDown || this.keys.d.isDown || touchState.right
    const steer = Number(rightPressed) - Number(leftPressed)

    const nearest = nearestTrackPoint(this.car.x, this.car.y)
    this.setSurfaceState(nearest.distance <= ROAD_HALF_WIDTH)

    let forward = new Phaser.Math.Vector2(Math.cos(this.heading), Math.sin(this.heading))
    let forwardSpeed = this.velocity.dot(forward)
    const acceleration = this.onRoad ? 265 : 125

    if (throttlePressed) {
      this.velocity.add(forward.clone().scale(acceleration * delta))
    }

    if (brakePressed) {
      if (forwardSpeed > 12) {
        this.velocity.add(forward.clone().scale(-410 * delta))
      } else {
        this.velocity.add(forward.clone().scale(-110 * delta))
      }
    }

    forwardSpeed = this.velocity.dot(forward)
    const steeringStrength = Phaser.Math.Clamp(Math.abs(forwardSpeed) / 155, 0.16, 1)
    const direction = forwardSpeed < -2 ? -1 : 1
    this.heading += steer * 2.15 * steeringStrength * direction * delta

    forward = new Phaser.Math.Vector2(Math.cos(this.heading), Math.sin(this.heading))
    const side = new Phaser.Math.Vector2(-forward.y, forward.x)
    let longitudinal = this.velocity.dot(forward)
    let lateral = this.velocity.dot(side)

    const grip = this.onRoad ? 0.76 : 0.9
    lateral *= Math.pow(grip, delta * 60)
    const drag = this.onRoad ? 0.18 : 1.65
    longitudinal *= Math.max(0, 1 - drag * delta)

    const maximumForwardSpeed = this.onRoad ? 350 : 112
    longitudinal = Phaser.Math.Clamp(longitudinal, -76, maximumForwardSpeed)
    this.velocity.copy(forward.scale(longitudinal).add(side.scale(lateral)))

    this.car.x += this.velocity.x * delta
    this.car.y += this.velocity.y * delta

    if (this.car.x < 20 || this.car.x > WORLD_WIDTH - 20) {
      this.car.x = Phaser.Math.Clamp(this.car.x, 20, WORLD_WIDTH - 20)
      this.velocity.x *= -0.25
    }
    if (this.car.y < 20 || this.car.y > WORLD_HEIGHT - 20) {
      this.car.y = Phaser.Math.Clamp(this.car.y, 20, WORLD_HEIGHT - 20)
      this.velocity.y *= -0.25
    }

    if (!this.onRoad && this.velocity.lengthSq() > 2_500 && Math.random() < delta * 26) {
      const backX = this.car.x - Math.cos(this.heading) * 24
      const backY = this.car.y - Math.sin(this.heading) * 24
      this.dust.emitParticleAt(backX, backY, Phaser.Math.Between(2, 4))
    }

    this.updateCarRotation()
  }

  private updateCarRotation(): void {
    this.car.setRotation(this.heading - Math.PI / 2)
  }

  private updateCheckpoints(): void {
    const target = checkpoints[this.nextCheckpoint]
    if (Phaser.Math.Distance.Between(this.car.x, this.car.y, target.x, target.y) > 88) return

    if (this.nextCheckpoint === checkpoints.length - 1) {
      this.currentLap += 1
      if (this.currentLap > TOTAL_LAPS) {
        this.finishRace()
        return
      }

      ui.lap.textContent = `${this.currentLap} / ${TOTAL_LAPS}`
      this.nextCheckpoint = 1
    } else {
      this.nextCheckpoint += 1
    }
  }

  private finishRace(): void {
    this.recordTelemetry(true)
    this.raceState = 'finished'
    this.velocity.scale(0.4)
    const previousBest = Number(localStorage.getItem(BEST_TIME_KEY)) || Number.POSITIVE_INFINITY
    const best = Math.min(previousBest, this.elapsedTime)
    localStorage.setItem(BEST_TIME_KEY, best.toString())

    ui.modalTitle.textContent = previousBest > this.elapsedTime ? 'Новый рекорд!' : 'Финиш'
    ui.modalCopy.textContent = 'Три круга завершены. Результат сохранён в этом браузере.'
    ui.resultTime.textContent = formatTime(this.elapsedTime)
    ui.bestTime.textContent = formatTime(best)
    ui.resultRow.hidden = false
    ui.start.textContent = 'ЕЩЁ ОДИН ЗАЕЗД'
    ui.modal.classList.add('is-visible')
    this.clearTouchState()
    const finishedTime = this.elapsedTime
    const finishedTelemetry = this.telemetry.slice()
    void submitRaceTime(finishedTime, finishedTelemetry).then((saved) => {
      if (saved && this.raceState === 'finished' && this.elapsedTime === finishedTime) {
        ui.modalCopy.textContent = 'Три круга завершены. Результат сохранён в браузере и таблице лидеров.'
        void loadGhost()
      }
    })
  }

  private recordTelemetry(force = false): void {
    if (this.telemetry.length >= MAX_TELEMETRY_SAMPLES) return
    if (!force && this.elapsedTime - this.lastTelemetrySampleAt < TELEMETRY_SAMPLE_INTERVAL_MS) return
    const t = Math.round(this.elapsedTime)
    if (this.telemetry.length && this.telemetry[this.telemetry.length - 1].t >= t) return
    this.telemetry.push({
      t,
      x: Number(this.car.x.toFixed(2)),
      y: Number(this.car.y.toFixed(2)),
      rotation: Number(Phaser.Math.Angle.Normalize(this.car.rotation).toFixed(4)),
    })
    this.lastTelemetrySampleAt = this.elapsedTime
  }

  private updateGhost(): void {
    const samples = this.ghost?.samples
    if (!ghostEnabled || !samples || samples.length < 2 || this.elapsedTime > (this.ghost?.time_ms ?? 0) + 200) {
      this.ghostCar?.setVisible(false)
      this.ghostLabel?.setVisible(false)
      return
    }
    while (
      this.ghostSampleIndex < samples.length - 2
      && samples[this.ghostSampleIndex + 1].t <= this.elapsedTime
    ) {
      this.ghostSampleIndex += 1
    }
    if (samples[this.ghostSampleIndex].t > this.elapsedTime) this.ghostSampleIndex = 0
    const start = samples[this.ghostSampleIndex]
    const end = samples[Math.min(this.ghostSampleIndex + 1, samples.length - 1)]
    const duration = Math.max(1, end.t - start.t)
    const progress = Phaser.Math.Clamp((this.elapsedTime - start.t) / duration, 0, 1)
    const ghostX = Phaser.Math.Linear(start.x, end.x, progress)
    const ghostY = Phaser.Math.Linear(start.y, end.y, progress)
    this.ghostCar
      .setVisible(true)
      .setPosition(ghostX, ghostY)
      .setRotation(Phaser.Math.Angle.Wrap(
        start.rotation + Phaser.Math.Angle.Wrap(end.rotation - start.rotation) * progress,
      ))
    this.ghostLabel
      .setVisible(true)
      .setPosition(ghostX, ghostY - 42)
  }

  private setSurfaceState(onRoad: boolean): void {
    if (this.onRoad === onRoad && ui.surface.dataset.ready === 'true') return
    this.onRoad = onRoad
    ui.surface.dataset.ready = 'true'
    ui.surface.classList.toggle('is-offroad', !onRoad)
    ui.surfaceLabel.textContent = onRoad ? 'НА ТРАССЕ' : 'ВНЕ ТРАССЫ'
  }

  private clearTouchState(): void {
    Object.keys(touchState).forEach((key) => {
      touchState[key as TouchControl] = false
    })
    document.querySelectorAll('.touch-button').forEach((button) => button.classList.remove('is-pressed'))
  }

  private updateCameraZoom(): void {
    const width = this.scale.width
    const height = this.scale.height
    const portrait = height > width
    const zoom = portrait
      ? Phaser.Math.Clamp(width / 310, 1.1, 1.55)
      : Phaser.Math.Clamp(height / 480, 1.18, 1.6)
    this.cameras.main.setZoom(zoom)
  }
}

let activeScene: RaceScene | undefined

const bindHoldButton = (id: string, control: TouchControl): void => {
  const button = $<HTMLButtonElement>(id)
  const setPressed = (pressed: boolean, event?: PointerEvent): void => {
    event?.preventDefault()
    touchState[control] = pressed
    button.classList.toggle('is-pressed', pressed)
    if (pressed && event) button.setPointerCapture(event.pointerId)
  }

  button.addEventListener('pointerdown', (event) => setPressed(true, event))
  button.addEventListener('pointerup', (event) => setPressed(false, event))
  button.addEventListener('pointercancel', (event) => setPressed(false, event))
  button.addEventListener('lostpointercapture', () => setPressed(false))
}

bindHoldButton('#touch-left', 'left')
bindHoldButton('#touch-right', 'right')
bindHoldButton('#touch-throttle', 'throttle')
bindHoldButton('#touch-brake', 'brake')

ui.start.addEventListener('click', () => {
  if (!activeScene) return
  if (ui.modalTitle.textContent === 'Пауза') activeScene.togglePause()
  else activeScene.startRace()
})
ui.reset.addEventListener('click', () => activeScene?.resetToTrack())
ui.pause.addEventListener('click', () => activeScene?.togglePause())
const toggleGhost = (): void => activeScene?.setGhostEnabled(!ghostEnabled)
ui.ghostHudToggle.addEventListener('click', toggleGhost)
ui.ghostMenuToggle.addEventListener('click', toggleGhost)
ui.menuButton.addEventListener('click', () => activeScene?.openGameMenu())
ui.menuClose.addEventListener('click', () => activeScene?.closeGameMenu())
ui.menuBackdrop.addEventListener('click', () => activeScene?.closeGameMenu())
ui.menuContinue.addEventListener('click', () => activeScene?.closeGameMenu())
ui.menuLeaderboard.addEventListener('click', () => {
  showMenuView('leaderboard')
  void loadLeaderboard()
})
ui.introLeaderboard.addEventListener('click', () => activeScene?.openGameMenu(true))
ui.leaderboardBack.addEventListener('click', () => showMenuView('main'))

document.addEventListener('visibilitychange', () => {
  if (document.hidden) activeScene?.togglePause()
})

new Phaser.Game({
  type: Phaser.AUTO,
  parent: 'game-canvas',
  backgroundColor: '#07100d',
  pixelArt: true,
  render: {
    antialias: false,
    roundPixels: true,
    powerPreference: 'high-performance',
  },
  scale: {
    mode: Phaser.Scale.RESIZE,
    width: window.innerWidth,
    height: window.innerHeight,
  },
  scene: RaceScene,
})
