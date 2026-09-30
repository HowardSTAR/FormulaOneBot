import Phaser from 'phaser'
import './style.css'
import { createTelemetrySample, interpolateGhost, type GhostSample } from './ghostTelemetry'
import { finishCrossing, type TrackPoint } from './finishLine'
import { simulationSteps } from './raceClock'
import { advanceWithCollisions, type Collider } from './collisions'
import { tracks, trackColliders, type Track } from './tracks'
import { drawTrack } from './trackRenderer'
const WORLD_WIDTH = 1536
const WORLD_HEIGHT = 1024

const TOTAL_LAPS = 3
const GHOST_ENABLED_KEY = 'emerald-loop-ghost-enabled'
const SELECTED_TRACK_KEY = 'emerald-loop-selected-track'
let selectedTrack = tracks[0]
const entryParams = new URLSearchParams(window.location.search)
let challengeToken = entryParams.get('challenge') || ''
if (!/^[A-Za-z0-9_-]{32}$/.test(challengeToken)) challengeToken = ''
let challengeRun: {track_id: string; name: string; time_ms: number; ghost: GhostRun; entries: {name: string; time_ms: number}[]} | null = null
let weeklyTrackId = ''
try {
  selectedTrack = tracks.find(track => track.id === localStorage.getItem(SELECTED_TRACK_KEY)) ?? tracks[0]
} catch { /* Storage is optional. */ }
selectedTrack = tracks.find(track => track.id === entryParams.get('track')) ?? selectedTrack
let centerLine: Phaser.Math.Vector2[] = []
let checkpoints: Phaser.Math.Vector2[] = []
let colliders: Collider[] = []
function activateTrack(track: Track): void {
  selectedTrack = track
  centerLine = track.centerLine.map(([x, y]) => new Phaser.Math.Vector2(x, y))
  checkpoints = track.checkpointIndexes.map(index => centerLine[index])
  colliders = trackColliders(track)
}
activateTrack(selectedTrack)
const TELEMETRY_SAMPLE_INTERVAL_MS = 100
const MAX_TELEMETRY_SAMPLES = 6000
let joystickSteer = 0

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
  progress?: { attempts:number;best_time_ms:number|null;improvement_ms:number|null;recent:{time_ms:number;created_at:string}[] } | null
  entries: LeaderboardEntry[]
  me: LeaderboardEntry | null
  ghost: GhostRun | null
  track_id: string
}

type ScoreSubmissionResult = {
  challenge?: {difference_ms?: number; beaten?: boolean; error?: string} | null
  saved: boolean
  leaderboard: LeaderboardResponse | null
  auto_enrolled?: boolean
  reason?: 'leaderboard_opted_out' | 'invalid_score' | string | null
  message?: string | null
}

type GhostRun = {
  is_challenge?: boolean
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
  restart: $('#restart-button') as HTMLButtonElement,
  menuRestart: $('#menu-restart-button') as HTMLButtonElement,
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
  trackName: $('#track-name'),
  trackFormat: $('#track-format'),
  trackSelect: $('#track-select') as HTMLSelectElement,
  trackDescription: $('#track-description'),
  trackPreview: $('#track-preview'),
  menuTrackName: $('#menu-track-name'),
  leaderboardTrackName: $('#leaderboard-track-name'),
  archive: $('#legacy-leaderboard-button') as HTMLButtonElement,
  currentRanking: $('#current-leaderboard-button') as HTMLButtonElement,
  shareRace: $('#share-race-button') as HTMLButtonElement,
  challengePanel: $('#challenge-panel'),
  challengeTitle: $('#challenge-title'),
  challengeCopy: $('#challenge-copy'),
  challengeRanking: $('#challenge-ranking'),
}

const syncTrackControls = (): void => {
  ui.trackName.textContent = selectedTrack.name.toUpperCase()
  ui.trackFormat.textContent = selectedTrack.format
  ui.menuTrackName.textContent = selectedTrack.name
  ui.trackSelect.value = selectedTrack.id
  ui.trackDescription.textContent = selectedTrack.description
  const namespace = 'http://www.w3.org/2000/svg'
  const map = document.createElementNS(namespace, 'svg')
  map.setAttribute('viewBox', '0 0 1536 1024')
  map.setAttribute('aria-hidden', 'true')
  const line = document.createElementNS(namespace, 'polyline')
  line.setAttribute('points', [...selectedTrack.centerLine, selectedTrack.centerLine[0]].map(point => point.join(',')).join(' '))
  line.setAttribute('fill', 'none')
  line.setAttribute('stroke', selectedTrack.accent)
  line.setAttribute('stroke-width', '42')
  line.setAttribute('stroke-linejoin', 'round')
  map.append(line)
  const start = document.createElementNS(namespace, 'circle')
  start.setAttribute('cx', String(selectedTrack.centerLine[0][0]))
  start.setAttribute('cy', String(selectedTrack.centerLine[0][1]))
  start.setAttribute('r', '38')
  start.setAttribute('fill', '#ffffff')
  map.append(start)
  ui.trackPreview.replaceChildren(map)
  ui.archive.hidden = selectedTrack.id !== 'emerald-loop-v2'
  ui.currentRanking.hidden = true
}
for (const track of tracks) {
  const option = document.createElement('option')
  option.value = track.id
  option.textContent = `${track.name} · ${track.format}`
  ui.trackSelect.append(option)
}
syncTrackControls()
ui.trackSelect.disabled = true
ui.start.disabled = true
ui.start.textContent = 'ЗАГРУЗКА…'
ui.introLeaderboard.disabled = true
ui.menuButton.disabled = true

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
  ui.ghostHudToggle.title = available && ghost
    ? `Призрак: ${ghost.name} · ${formatTime(ghost.time_ms)}`
    : 'Пока нет записанного пути. Завершите новый заезд с сохранением результата.'
  ui.ghostMenuLabel.textContent = `Ghost Racer: ${ghostEnabled ? 'ON' : 'OFF'}`
  ui.ghostMenuCopy.textContent = available && ghost
    ? `${ghost.is_challenge ? 'Вызов друга' : ghost.is_global_best ? '#1' : 'Лучший доступный'} ${ghost.name} · ${formatTime(ghost.time_ms)}`
    : 'Пока нет записанного пути. Завершите новый заезд с сохранением результата.'
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
      const payload = await response.json() as { detail?: string | { message?: string } | { loc?: (string|number)[];msg?:string }[] }
      if (Array.isArray(payload.detail) && response.status === 422) {
        const text = payload.detail.map(item=>item.msg || '').join(' ')
        message = text.includes('duration must match') ? 'Результат отклонён: время заезда не совпадает с длительностью записи призрака.'
          : text.includes('strictly increasing') || text.includes('time zero') ? 'Результат отклонён: нарушена последовательность времени в записи заезда.'
          : payload.detail.some(item=>item.loc?.includes('track_id')) ? 'Эта версия трассы не поддерживается. Обновите игру.'
          : payload.detail.some(item=>item.loc?.includes('time_ms')) ? 'Время заезда вне допустимого диапазона: от 15 секунд до 60 минут.'
          : text.includes('complete three laps') ? 'Результат отклонён: запись не подтверждает три полных круга через все контрольные точки.'
          : text.includes('implausible movement') ? 'Результат отклонён: запись содержит скачок позиции. Возврат на трассу доступен только для тренировки.'
          : 'Запись заезда содержит недопустимые данные. Обновите игру и попробуйте ещё раз.'
      } else message = typeof payload.detail === 'string' ? payload.detail : !Array.isArray(payload.detail) ? payload.detail?.message || message : message
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
  if (data.progress?.attempts) {
    const progress = document.createElement('div')
    progress.className = 'leaderboard-message'
    const heading = document.createElement('p')
    heading.textContent = `Ваш прогресс на этой трассе: ${data.progress.attempts} сохранённых заездов · улучшение от первого: ${formatTime(data.progress.improvement_ms ?? 0)}`
    progress.append(heading)
    const recent = document.createElement('details')
    const label = document.createElement('summary')
    label.textContent = 'Последние 10 заездов · только для вас'
    recent.append(label)
    data.progress.recent.forEach(run => {
      const row = document.createElement('p')
      row.textContent = `${formatTime(run.time_ms)} · ${run.created_at} UTC`
      recent.append(row)
    })
    progress.append(recent)
    ui.leaderboardList.append(progress)
  }

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

let leaderboardRequestVersion = 0
let leaderboardTrackId = selectedTrack.id
const loadLeaderboard = async (trackId = selectedTrack.id): Promise<void> => {
  const version = ++leaderboardRequestVersion
  leaderboardTrackId = trackId
  ui.leaderboardTrackName.textContent = trackId === 'emerald-loop-v1' ? 'Emerald Loop · архив без столкновений' : selectedTrack.name
  ui.currentRanking.hidden = trackId !== 'emerald-loop-v1'
  ui.archive.hidden = selectedTrack.id !== 'emerald-loop-v2' || trackId === 'emerald-loop-v1'
  ui.leaderboardList.innerHTML = '<div class="leaderboard-message">Загрузка результатов…</div>'
  ui.leaderboardMyPlace.textContent = '—'
  try {
    const data = await apiRequest<LeaderboardResponse>(`/api/race-game-leaderboard?track_id=${encodeURIComponent(trackId)}`)
    if (version !== leaderboardRequestVersion || data.track_id !== trackId) return
    if (trackId === selectedTrack.id) activeScene?.setGhost(data.ghost)
    // Loading the ranking must be read-only. Re-uploading localBest here
    // resurrected scores after an admin wipe (without their trajectory).
    renderLeaderboard(data)
  } catch (error) {
    if (version !== leaderboardRequestVersion) return
    ui.leaderboardMyPlace.textContent = '—'
    ui.leaderboardList.innerHTML = ''
    const message = document.createElement('div')
    message.className = 'leaderboard-message'
    message.textContent = error instanceof Error ? error.message : 'Не удалось загрузить таблицу лидеров.'
    ui.leaderboardList.append(message)
  }
}

let ghostRequestVersion = 0
const loadGhost = async (): Promise<void> => {
  const version = ++ghostRequestVersion
  const trackId = selectedTrack.id
  if (challengeRun && challengeRun.track_id === trackId) {
    activeScene?.setGhost(challengeRun.ghost)
    return
  }
  try {
    const response = await fetch(`/api/race-game/ghost?track_id=${encodeURIComponent(trackId)}`, {
      credentials: 'omit', cache: 'no-store', signal: AbortSignal.timeout(15000),
    })
    if (!response.ok) throw new Error(`Ghost request failed: ${response.status}`)
    const data = await response.json() as { track_id: string; ghost: GhostRun | null }
    if (version === ghostRequestVersion && trackId === selectedTrack.id && data.track_id === trackId) activeScene?.setGhost(data.ghost)
  } catch {
    // A temporary network failure must not remove an already loaded replay.
  }
}

async function submitRaceTime(timeMs: number, telemetry: GhostSample[], trackId: string): Promise<ScoreSubmissionResult> {
  try {
    return await apiRequest<ScoreSubmissionResult>('/api/race-game-leaderboard/score', {
      time_ms: Math.round(timeMs),
      track_id: trackId,
      telemetry,
      challenge_token: challengeRun?.track_id === trackId ? challengeToken : undefined,
    })
  } catch (error) {
    return {
      saved: false,
      leaderboard: null,
      message: error instanceof Error ? error.message : 'Не удалось сохранить результат в таблице лидеров.',
    }
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
  private telemetry: GhostSample[] = []
  private lastTelemetrySampleAt = -TELEMETRY_SAMPLE_INTERVAL_MS
  private practiceRun = false
  private collisionUntil = 0
  private runVersion = 0

  constructor() {
    super('race')
  }

  preload(): void {
    this.load.image('track', assetUrl('emerald-loop-track.png'))
    this.load.image('car', assetUrl('open-wheel-car.png'))
  }

  create(): void {
    drawTrack(this, selectedTrack)

    const dustPixel = this.make.graphics({ x: 0, y: 0 })
    dustPixel.fillStyle(0xd2b77d, 1)
    dustPixel.fillStyle(0xe0c48c, 0.92)
    dustPixel.fillCircle(9, 9, 9)
    if (!this.textures.exists('dust-pixel')) dustPixel.generateTexture('dust-pixel', 18, 18)
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
    ui.trackSelect.disabled = Boolean(challengeRun || weeklyTrackId)
    ui.start.disabled = false
    ui.introLeaderboard.disabled = false
    ui.menuButton.disabled = false
    syncGhostControls(null)
    void loadGhost()
    const refreshGhost = window.setInterval(() => {
      if (!document.hidden) void loadGhost()
    }, 30_000)
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      window.clearInterval(refreshGhost)
      ghostRequestVersion += 1
      leaderboardRequestVersion += 1
    })
  }

  update(_time: number, deltaMilliseconds: number): void {

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
      // Movement, stopwatch and replay must use the same time at every frame rate.
      for (const step of simulationSteps(deltaMilliseconds)) {
        if (this.raceState !== 'racing') break
        const previousPosition = { x: this.car.x, y: this.car.y }
        this.elapsedTime += step
        this.updateDriving(step / 1000)
        this.updateCheckpoints(previousPosition, step)
        this.recordTelemetry()
      }
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
    void loadGhost()

    ui.modal.classList.remove('is-visible')
    ui.countdown.classList.remove('is-go')
    this.raceState = 'countdown'
    this.countdownRemaining = 3000
    this.goFlashRemaining = 0
    ui.pause.textContent = 'Ⅱ'
  }

  setGhost(ghost: GhostRun | null): void {
    // Do not switch opponents mid-race when a background request completes.
    if (ghost && this.ghost && (this.raceState === 'racing' || this.raceState === 'paused')) return
    this.ghost = ghost?.samples?.length && ghost.samples.length >= 2 ? ghost : null
    this.ghostLabel?.setText(this.ghost ? `GHOST · ${this.ghost.name} · ${formatTime(this.ghost.time_ms)} / 3 круга` : '')
    syncGhostControls(this.ghost)
    this.updateGhost()
  }

  restartRace(): void {
    this.closeGameMenu()
    this.resetRace()
    this.input.keyboard?.resetKeys()
    this.cameras.main.centerOn(this.car.x, this.car.y)
    this.startRace()
  }

  selectTrack(track: Track): void {
    if (selectedTrack.id === track.id) return
    this.closeGameMenu()
    this.clearTouchState()
    this.input.keyboard?.resetKeys()
    this.runVersion += 1
    ghostRequestVersion += 1
    leaderboardRequestVersion += 1
    activateTrack(track)
    try { localStorage.setItem(SELECTED_TRACK_KEY, track.id) } catch { /* Storage is optional. */ }
    syncTrackControls()
    ui.trackSelect.disabled = true
    ui.start.disabled = true
    this.ghost = null
    this.scene.restart()
  }

  openTrackPicker(): void {
    this.closeGameMenu()
    this.input.keyboard?.resetKeys()
    this.resetRace()
    ui.trackSelect.focus()
  }

  setGhostEnabled(enabled: boolean): void {
    ghostEnabled = enabled
    persistGhostPreference()
    syncGhostControls(this.ghost)
    this.updateGhost()
    if (enabled) void loadGhost()
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
      ui.restart.hidden = false
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

  pauseWhenHidden(): void {
    this.clearTouchState()
    this.input.keyboard?.resetKeys()
    if (this.raceState === 'racing') this.togglePause()
    else if (this.raceState === 'countdown') this.openGameMenu()
  }

  resetToTrack(): void {
    if (!this.car) return
    // A rescue is useful, but cannot generate a competitive teleport shortcut.
    if (this.raceState === 'racing' || this.raceState === 'paused') this.practiceRun = true
    const nearest = nearestTrackPoint(this.car.x, this.car.y)
    this.car.setPosition(nearest.x, nearest.y)
    this.heading = nearest.heading
    this.velocity.set(0, 0)
    this.updateCarRotation()
    this.setSurfaceState(true)
    if (this.practiceRun) ui.surfaceLabel.textContent = 'ТРЕНИРОВКА · БЕЗ РЕКОРДА'
  }

  private resetRace(): void {
    this.runVersion += 1
    this.practiceRun = false
    this.collisionUntil = 0
    this.raceState = 'ready'
    this.elapsedTime = 0
    this.currentLap = 1
    this.nextCheckpoint = 1
    this.countdownRemaining = 0
    this.goFlashRemaining = 0
    this.heading = Math.atan2(centerLine[1].y - centerLine[0].y, centerLine[1].x - centerLine[0].x)
    this.velocity.set(0, 0)
    this.car.setPosition(centerLine[0].x, centerLine[0].y)
    this.updateCarRotation()
    this.clearTouchState()
    this.telemetry = []
    this.lastTelemetrySampleAt = -TELEMETRY_SAMPLE_INTERVAL_MS

    ui.lap.textContent = `1 / ${TOTAL_LAPS}`
    ui.time.textContent = formatTime(0)
    ui.speed.textContent = '0'
    ui.modalTitle.textContent = selectedTrack.name
    ui.modalCopy.textContent = 'Три круга · столкновения замедляют · возврат ↺ — тренировка без рекорда.'
    ui.start.textContent = 'НАЧАТЬ ЗАЕЗД'
    ui.restart.hidden = true
    ui.resultRow.hidden = true
    ui.shareRace.hidden = true
    ui.modal.classList.add('is-visible')
    ui.countdown.textContent = ''
    ui.countdown.classList.remove('is-go')
    ui.pause.textContent = 'Ⅱ'
    ui.surface.dataset.ready = 'false'
    this.setSurfaceState(true)
    this.updateGhost()
  }

  private updateDriving(delta: number): void {
    const throttlePressed = this.keys.up.isDown || this.keys.w.isDown || this.keys.space.isDown || touchState.throttle
    const brakePressed = this.keys.down.isDown || this.keys.s.isDown || touchState.brake
    const leftPressed = this.keys.left.isDown || this.keys.a.isDown || touchState.left
    const rightPressed = this.keys.right.isDown || this.keys.d.isDown || touchState.right
    const steer = Phaser.Math.Clamp(Number(rightPressed) - Number(leftPressed) + joystickSteer, -1, 1)

    const nearest = nearestTrackPoint(this.car.x, this.car.y)
    this.setSurfaceState(nearest.distance <= selectedTrack.roadHalfWidth)

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

    const movement = advanceWithCollisions(this.car, this.velocity, this.heading, delta, colliders)
    this.car.setPosition(movement.x, movement.y)
    this.velocity.set(movement.vx, movement.vy)
    if (movement.impact > 35) this.collisionUntil = this.elapsedTime + 550
    ui.surfaceLabel.textContent = this.elapsedTime < this.collisionUntil ? 'СТОЛКНОВЕНИЕ'
      : this.practiceRun ? 'ТРЕНИРОВКА · БЕЗ РЕКОРДА' : this.onRoad ? 'НА ТРАССЕ' : 'ВНЕ ТРАССЫ'

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

  private updateCheckpoints(previous: TrackPoint, deltaMilliseconds: number): void {
    const target = checkpoints[this.nextCheckpoint]

    if (this.nextCheckpoint === checkpoints.length - 1) {
      const crossing = finishCrossing(previous, this.car, selectedTrack.finishLine)
      if (crossing === null) return
      this.currentLap += 1
      if (this.currentLap > TOTAL_LAPS) {
        // Final timer and telemetry end at the actual crossing, between ticks.
        this.elapsedTime -= deltaMilliseconds * (1 - crossing)
        this.car.setPosition(
          previous.x + (this.car.x - previous.x) * crossing,
          previous.y + (this.car.y - previous.y) * crossing,
        )
        this.finishRace()
        return
      }

      ui.lap.textContent = `${this.currentLap} / ${TOTAL_LAPS}`
      this.nextCheckpoint = 1
      this.recordTelemetry(true)
    } else {
      if (Phaser.Math.Distance.Between(this.car.x, this.car.y, target.x, target.y) > selectedTrack.roadHalfWidth + 20) return
      this.nextCheckpoint += 1
      // Store every gate even when it falls between regular replay samples.
      this.recordTelemetry(true)
    }
  }

  private finishRace(): void {
    this.recordTelemetry(true)
    ui.shareRace.hidden = true
    this.raceState = 'finished'
    this.velocity.scale(0.4)
    const bestKey = `emerald-loop-best-time:${selectedTrack.id}`
    let previousBest = Number.POSITIVE_INFINITY
    try { previousBest = Number(localStorage.getItem(bestKey)) || Number.POSITIVE_INFINITY } catch { /* Storage is optional. */ }
    const best = Math.min(previousBest, this.elapsedTime)
    if (!this.practiceRun) {
      try { localStorage.setItem(bestKey, best.toString()) } catch { /* Storage is optional. */ }
    }

    ui.modalTitle.textContent = this.practiceRun ? 'Тренировка завершена' : previousBest > this.elapsedTime ? 'Новый рекорд!' : 'Финиш'
    ui.modalCopy.textContent = this.practiceRun ? 'Вы использовали возврат на трассу. Время не записано в рекорды; начните новый заезд для участия в рейтинге.' : 'Три круга завершены. Результат сохранён в этом браузере.'
    ui.resultTime.textContent = formatTime(this.elapsedTime)
    ui.bestTime.textContent = this.practiceRun ? Number.isFinite(previousBest) ? formatTime(previousBest) : '—' : formatTime(best)
    ui.resultRow.hidden = false
    ui.start.textContent = 'ЕЩЁ ОДИН ЗАЕЗД'
    ui.restart.hidden = true
    ui.modal.classList.add('is-visible')
    this.clearTouchState()
    const finishedTime = this.elapsedTime
    const finishedTelemetry = this.telemetry.slice()
    const trackId = selectedTrack.id
    const runVersion = this.runVersion
    if (this.practiceRun) return
    void submitRaceTime(finishedTime, finishedTelemetry, trackId).then((result) => {
      if (trackId !== selectedTrack.id || runVersion !== this.runVersion || !this.scene.isActive()) return
      if (result.saved) {
        if (result.leaderboard) {
          ghostRequestVersion += 1
          if (leaderboardTrackId === trackId) {
            leaderboardRequestVersion += 1
            renderLeaderboard(result.leaderboard)
          }
          this.setGhost(challengeRun?.track_id === trackId ? challengeRun.ghost : result.leaderboard.ghost)
        } else {
          void Promise.all([loadLeaderboard(), loadGhost()])
        }
        if (this.raceState === 'finished' && this.elapsedTime === finishedTime) {
          ui.modalCopy.textContent = 'Три круга завершены. Результат сохранён в браузере и таблице лидеров.'
          ui.shareRace.hidden = false
          if (result.challenge?.difference_ms !== undefined) {
            const difference = result.challenge.difference_ms
            ui.challengeCopy.textContent = difference < 0 ? `Вы быстрее друга на ${formatTime(-difference)}!` : difference === 0 ? 'Точное совпадение времени!' : `До времени друга — ${formatTime(difference)}.`
            void refreshChallenge()
          } else if (result.challenge?.error) ui.challengeCopy.textContent = result.challenge.error
        }
      } else if (this.raceState === 'finished' && this.elapsedTime === finishedTime) {
        ui.modalCopy.textContent = result.message
          ? `Результат сохранён только в браузере. ${result.message}`
          : 'Результат сохранён только в браузере. Включите участие в общей таблице лидеров.'
      }
    })
  }

  private recordTelemetry(force = false): void {
    if (this.telemetry.length >= MAX_TELEMETRY_SAMPLES) return
    if (!force && this.elapsedTime - this.lastTelemetrySampleAt < TELEMETRY_SAMPLE_INTERVAL_MS) return
    const t = Math.round(this.elapsedTime)
    if (this.telemetry.length && this.telemetry[this.telemetry.length - 1].t >= t) {
      if (force && this.telemetry[this.telemetry.length - 1].t === t) {
        this.telemetry[this.telemetry.length - 1] = createTelemetrySample(t, this.car.x, this.car.y, this.car.rotation)
      }
      return
    }
    this.telemetry.push(createTelemetrySample(t, this.car.x, this.car.y, this.car.rotation))
    this.lastTelemetrySampleAt = this.elapsedTime
  }

  private updateGhost(): void {
    const samples = this.ghost?.samples
    if (!ghostEnabled || !samples || samples.length < 2 || this.elapsedTime > (this.ghost?.time_ms ?? 0) + 200) {
      this.ghostCar?.setVisible(false)
      this.ghostLabel?.setVisible(false)
      return
    }
    const pose = interpolateGhost(samples, this.elapsedTime)
    if (!pose) return
    const { x: ghostX, y: ghostY, rotation } = pose
    this.ghostCar
      .setVisible(true)
      .setPosition(ghostX, ghostY)
      .setRotation(rotation)
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
    resetJoystick()
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

const joystick = $('#touch-joystick')
const joystickKnob = $('#joystick-knob')
let steeringPointer: number | null = null
function resetJoystick(): void {
  steeringPointer = null
  joystickSteer = 0
  joystickKnob.style.transform = 'translate(0px, 0px)'
}
const moveJoystick = (event: PointerEvent): void => {
  if (event.pointerId !== steeringPointer) return
  event.preventDefault()
  const rect = joystick.getBoundingClientRect()
  const radius = rect.width * 0.3
  const dx = event.clientX - rect.left - rect.width / 2
  const dy = event.clientY - rect.top - rect.height / 2
  const scale = Math.min(1, radius / Math.max(1, Math.hypot(dx, dy)))
  const x = dx * scale
  joystickSteer = Math.abs(x / radius) < 0.08 ? 0 : x / radius
  joystickKnob.style.transform = `translate(${x}px, ${dy * scale}px)`
}
joystick.addEventListener('pointerdown', (event) => {
  if (steeringPointer !== null) return
  steeringPointer = event.pointerId
  joystick.setPointerCapture(event.pointerId)
  moveJoystick(event)
})
joystick.addEventListener('pointermove', moveJoystick)
for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
  joystick.addEventListener(type, (event) => {
    if ((event as PointerEvent).pointerId === steeringPointer) resetJoystick()
  })
}
window.addEventListener('blur', resetJoystick)
bindHoldButton('#touch-throttle', 'throttle')
bindHoldButton('#touch-brake', 'brake')

ui.start.addEventListener('click', () => {
  const root = window.parent.document.documentElement
  if (window.matchMedia('(pointer: coarse)').matches && root.requestFullscreen && !window.parent.document.fullscreenElement) {
    void root.requestFullscreen().catch(() => {})
  }
  if (!activeScene) return
  if (ui.modalTitle.textContent === 'Пауза') activeScene.togglePause()
  else activeScene.startRace()
})
ui.reset.addEventListener('click', () => activeScene?.resetToTrack())
ui.restart.addEventListener('click', () => activeScene?.restartRace())
ui.menuRestart.addEventListener('click', () => activeScene?.restartRace())
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
$('#menu-tracks-button').addEventListener('click', () => activeScene?.openTrackPicker())
ui.archive.addEventListener('click', () => { void loadLeaderboard('emerald-loop-v1') })
ui.currentRanking.addEventListener('click', () => { void loadLeaderboard() })
ui.trackSelect.addEventListener('change', () => {
  const track = tracks.find(item => item.id === ui.trackSelect.value)
  if (track) activeScene?.selectTrack(track)
})

document.addEventListener('visibilitychange', () => {
  if (document.hidden) activeScene?.pauseWhenHidden()
})

async function refreshChallenge(): Promise<void> {
  if (!challengeToken) return
  try {
    const data = await apiRequest<NonNullable<typeof challengeRun>>(`/api/engagement/challenges/${challengeToken}`)
    challengeRun = data
    ui.challengeRanking.replaceChildren(...data.entries.slice(0, 8).map(entry => {
      const row = document.createElement('li')
      row.textContent = `${entry.name} · ${formatTime(entry.time_ms)}`
      return row
    }))
  } catch { /* The verified race remains saved even if an invitation expires. */ }
}
ui.shareRace.addEventListener('click', () => {
  if (window.parent !== window) window.parent.postMessage({type: 'f1hub-share-race', trackId: selectedTrack.id}, window.location.origin)
  else window.location.assign('/community')
})

async function bootGame(): Promise<void> {
  if (challengeToken) {
    ui.challengePanel.hidden = false
    ui.challengeTitle.textContent = 'Открываем вызов…'
    try {
      const response = await fetch(`/api/engagement/challenges/${challengeToken}`, {signal: AbortSignal.timeout(15000), cache: 'no-store'})
      if (!response.ok) throw new Error('Вызов недоступен')
      const data = await response.json() as NonNullable<typeof challengeRun>
      const track = tracks.find(track => track.id === data.track_id)
      if (!track) throw new Error('Версия трассы недоступна')
      challengeRun = data
      activateTrack(track); syncTrackControls()
      ui.challengeTitle.textContent = `Вызов: ${data.name}`
      ui.challengeCopy.textContent = `Цель — быстрее ${formatTime(data.time_ms)}. Призрак повторяет заезд друга; условия трассы одинаковы.`
      void refreshChallenge()
    } catch {
      challengeToken = ''
      ui.challengeTitle.textContent = 'Вызов истёк или отозван'
      ui.challengeCopy.textContent = 'Обычный заезд доступен. Выберите трассу и создайте собственный вызов.'
    }
  } else if (entryParams.get('weekly') === '1') {
    ui.challengePanel.hidden = false
    ui.challengeTitle.textContent = 'Загружаем трассу недели…'
    try {
      const response = await fetch('/api/engagement/weekly', {signal: AbortSignal.timeout(15000), cache: 'no-store'})
      if (!response.ok) throw new Error('Трасса недели недоступна')
      const data = await response.json() as {track_id: string; end: string}
      const track = tracks.find(track => track.id === data.track_id)
      if (!track) throw new Error('Версия трассы недоступна')
      weeklyTrackId = data.track_id
      activateTrack(track); syncTrackControls()
      ui.challengeTitle.textContent = 'Трасса недели'
      ui.challengeCopy.textContent = `Заезд участвует в недельном рейтинге до ${new Date(data.end).toLocaleString('ru-RU')}. Постоянные рекорды остаются без изменений.`
    } catch {
      ui.challengeTitle.textContent = 'Недельный рейтинг временно недоступен'
      ui.challengeCopy.textContent = 'Можно проехать обычный заезд. Трасса недели определяется сервером; её участие сейчас не подтверждено.'
    }
  }
const game = new Phaser.Game({
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
    mode: Phaser.Scale.NONE,
    width: window.innerWidth,
    height: window.innerHeight,
  },
  scene: RaceScene,
})

// Match drawing-buffer and CSS pixels on Android iframe/browser resizes.
const canvasHost = $('#game-canvas')
let resizeFrame = 0
const resizeGame = (): void => {
  cancelAnimationFrame(resizeFrame)
  resizeFrame = requestAnimationFrame(() => {
    const width = Math.round(canvasHost.clientWidth)
    const height = Math.round(canvasHost.clientHeight)
    if (width > 0 && height > 0 && (game.scale.width !== width || game.scale.height !== height)) {
      game.scale.resize(width, height)
    }
  })
}
const viewportObserver = new ResizeObserver(resizeGame)
viewportObserver.observe(canvasHost)
window.addEventListener('resize', resizeGame)
window.visualViewport?.addEventListener('resize', resizeGame)
game.events.once(Phaser.Core.Events.READY, resizeGame)
game.events.once(Phaser.Core.Events.DESTROY, () => {
  cancelAnimationFrame(resizeFrame)
  viewportObserver.disconnect()
  window.removeEventListener('resize', resizeGame)
  window.visualViewport?.removeEventListener('resize', resizeGame)
})
}
void bootGame()
