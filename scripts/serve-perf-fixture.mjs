/** Isolated browser QA: static build + deterministic API fixtures, no real DB/API. */
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, resolve, sep } from 'node:path';

const root = resolve(process.argv[2] || '.tmp/perf-after');
const port = Number(process.argv[3] || 4179);
const signed = process.argv.includes('--signed');
const raceQA = process.argv.includes('--race');
const raceTracks = raceQA ? JSON.parse(await readFile(new URL('../app/race_tracks.json', import.meta.url), 'utf8')) : [];
const counts = new Map();
const start = new Date(Date.now() + 2 * 86400000).toISOString();
const race = { status: 'ok', event_name: 'Bahrain Grand Prix', location: 'Sakhir', country: 'Bahrain', season: 2026, round: 16, next_session_name: 'Практика 1', next_session_iso: start, race_start_utc: start, date: start.slice(0, 10) };
const drivers = ['RUS', 'ANT', 'HAM', 'NOR', 'LEC'].map((code, i) => ({
  code, position: i + 1, driverId: code.toLowerCase(), name: ['George Russell', 'Andrea Kimi Antonelli', 'Lewis Hamilton', 'Lando Norris', 'Charles Leclerc'][i],
  points: 300 - i * 20, constructorId: i < 2 ? 'mercedes' : 'ferrari', constructorName: i < 2 ? 'Mercedes' : 'Ferrari',
}));
const fixtures = {
  '/api/auth/me': signed ? { id: 1, email: null, telegram_id: null, role: 'user', display_name: 'QA', email_verified: true } : null,
  '/api/next-race': race,
  '/api/settings': { timezone: 'Europe/Moscow' },
  '/api/weekend-schedule': { sessions: [{ name: 'Практика 1', utc_iso: start }] },
  '/api/drivers': { drivers },
  '/api/constructors': { constructors: [{ position: 1, constructorId: 'mercedes', name: 'Mercedes', points: 580 }] },
  '/api/web-notifications/unread-count': { unread: 2 },
  '/api/predictions/current': { ...race, is_open: true, deadline_utc: start, prediction: null },
  '/api/predictions/personal-season': { latest: null },
  '/api/season': { races: [{ ...race, date: start.slice(0, 10), race_start_utc: start }] },
};
const mime = { '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.html': 'text/html', '.webmanifest': 'application/manifest+json' };
const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${port}`);
  if (url.pathname === '/__perf/report') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    return res.end(JSON.stringify({ signed, requests: Object.fromEntries(counts) }));
  }
  counts.set(url.pathname, (counts.get(url.pathname) || 0) + 1);
  if (url.pathname.startsWith('/api/')) {
    if (raceQA && req.method === 'GET' && ['/api/race-game-leaderboard', '/api/race-game/ghost'].includes(url.pathname)) {
      const trackId = url.searchParams.get('track_id') || 'emerald-loop-v1';
      const index = raceTracks.findIndex(track => track.id === trackId);
      const valid = index >= 0 || trackId === 'emerald-loop-v1';
      res.writeHead(valid ? 200 : 422, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
      return res.end(JSON.stringify(!valid ? { detail: 'Unsupported track_id' } : url.pathname.endsWith('/ghost')
        ? { track_id: trackId, ghost: null }
        : { track_id: trackId, ghost: null, me: null, progress: null,
          entries: [{ place: 1, telegram_id: 1, name: 'Тестовый рекорд · ' + trackId, time_ms: 72000 + (index + 1) * 10000, is_me: false }] }));
    }
    // Normal visit/error analytics are consumed locally and never forwarded.
    if (req.method !== 'GET' && !url.pathname.startsWith('/api/analytics/')) {
      res.writeHead(405); return res.end();
    }
    if (['/api/team-logo', '/api/pilot-portrait'].includes(url.pathname)) {
      res.writeHead(200, { 'Content-Type': 'image/svg+xml' });
      return res.end('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="#c33"/></svg>');
    }
    const value = fixtures[url.pathname];
    res.writeHead(value === null ? 401 : value === undefined && !url.pathname.startsWith('/api/analytics/') ? 404 : 200,
      { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    return setTimeout(() => res.end(JSON.stringify(value ?? { detail: 'Fixture endpoint unavailable' })), 150);
  }
  try {
    const target = resolve(root, url.pathname === '/' ? 'index.html' : '.' + decodeURIComponent(url.pathname));
    if (!target.startsWith(root + sep)) { res.writeHead(403); return res.end(); }
    let file = target;
    try { if (!(await stat(file)).isFile()) file = resolve(root, 'index.html'); }
    catch { if (!extname(url.pathname)) file = resolve(root, 'index.html'); else throw new Error('Not found'); }
    const data = await readFile(file);
    res.writeHead(200, { 'Content-Type': mime[extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
    res.end(data);
  } catch { res.writeHead(404); res.end(); }
});
server.listen(port, '127.0.0.1', () => console.log(`Isolated fixture: http://127.0.0.1:${port} (${signed ? 'test account' : 'guest'})`));
