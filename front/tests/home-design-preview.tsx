// Vite-only visual fixture. Uses the real app with deterministic, fictional data.
// No requests are sent to a backend, and no accounts or records are modified.
import circuitSvg from '../public/static/circuit/United States Grand Prix.svg?raw';
import { createRoot } from 'react-dom/client';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { HeroDataProvider } from '../src/context/HeroDataContext';
import { initializeTheme, setTheme, storedTheme } from '../src/helpers/theme';
import { ScrollToTop } from '../src/components/ScrollToTop';
const query = new URLSearchParams(location.search);
const scenario = query.get('state');
const member = ['member', 'linked'].includes(query.get('auth') || '');
const linked = query.get('auth') === 'linked';
const demoVotes: Record<number, number> = {};
let previewRead = false;
let voteFailures = scenario === 'rating-error' ? 1 : 0;
if (query.get('scale') === '2') document.documentElement.style.fontSize = '200%';
const realFetch = window.fetch.bind(window);
const sessions = [
  { name: 'Практика 1', utc_iso: '2026-10-23T17:30:00Z' },
  { name: 'Спринт-квалификация', utc_iso: '2026-10-23T21:30:00Z' },
  { name: 'Спринт', utc_iso: '2026-10-24T17:00:00Z' },
  { name: 'Квалификация', utc_iso: '2026-10-24T21:00:00Z' },
  { name: 'Гонка', utc_iso: '2026-10-25T20:00:00Z' },
];
if (scenario === 'past') sessions.forEach(session => { session.utc_iso = session.utc_iso.replace('-10-23', '-10-16').replace('-10-24', '-10-17').replace('-10-25', '-10-18'); });
if (scenario === 'untimed') sessions[0].utc_iso = '';
if (scenario === 'race-untimed') sessions[4].utc_iso = '';
const drivers = [
  { position: 1, code: 'NOR', number: '4', imageUrl: 'https://media.formula1.com/image/upload/c_fill,w_720/q_auto/v1740000001/common/f1/2026/mclaren/lannor01/2026mclarenlannor01right.webp', driverId: 'norris', name: 'Ландо Норрис', constructorName: 'McLaren', points: 287 },
  { position: 2, code: 'PIA', number: '81', imageUrl: 'https://media.formula1.com/image/upload/c_fill,w_720/q_auto/v1740000001/common/f1/2026/mclaren/oscpia01/2026mclarenoscpia01right.webp', driverId: 'piastri', name: 'Оскар Пиастри', constructorName: 'McLaren', points: 272 },
  { position: 3, name: 'Макс Ферстаппен', constructorName: 'Red Bull Racing', points: 255 },
  { position: 4, name: 'Джордж Расселл', constructorName: 'Mercedes', points: 214 },
  { position: 5, name: 'Шарль Леклер', constructorName: 'Ferrari', points: 196 },
];
window.fetch = async (input, init) => {
  const url = new URL(input instanceof Request ? input.url : String(input), location.origin);
  if (url.pathname.startsWith('/static/circuit/')) return new Response(circuitSvg, { headers: { 'Content-Type': 'image/svg+xml' } });
  if (!url.pathname.startsWith('/api/')) return realFetch(input, init);
  const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
  if ((init?.method || (input instanceof Request ? input.method : 'GET')) !== 'GET') {
    if (query.get('demoVotes') === '1' && url.pathname === '/api/votes/race' && init?.method === 'POST') {
      const body = JSON.parse(String(init.body));
      if (voteFailures-- > 0) return json({ detail: 'Не удалось сохранить оценку' }, 503);
      if (!linked || !Number.isInteger(body.rating) || body.rating < 1 || body.rating > 5) return json({}, 400);
      demoVotes[body.round] = body.rating;
      return json({ status: 'ok' }); // Local fixture only; no backend request.
    }
    if (query.get('demoVotes') === '1' && url.pathname === '/api/web-notifications/read' && init?.method === 'POST') { previewRead = true; return json({ ok: true }); }
    return new Response('Preview is read only', { status: 405 });
  }
  if (scenario === 'error' && ['/api/next-race', '/api/drivers', '/api/constructors'].includes(url.pathname)) return json({ detail: 'Демонстрация ошибки' }, 503);
  if (scenario === 'schedule-error' && url.pathname === '/api/weekend-schedule') return json({ detail: 'Демонстрация ошибки расписания' }, 503);
  if (scenario === 'personal-error' && ['/api/predictions/current', '/api/web-notifications/unread-count', '/api/predictions/personal-season'].includes(url.pathname)) return json({ detail: 'Демонстрация ошибки личного раздела' }, 503);
  switch (url.pathname) {
    case '/api/auth/me': return member ? json({ id: 1, email: null, telegram_id: linked ? 1 : null, role: 'user', email_verified: true, display_name: 'Болельщик' }) : json({}, 401);
    case '/api/favorites': return scenario === 'favorites-error' ? json({}, 503) : json(scenario === 'favorites-empty' ? { drivers: [], teams: [] } : scenario === 'favorites-missing' ? { drivers: ['OLD'], teams: ['Old Team'] } : { drivers: ['PIA', 'NOR'], teams: ['McLaren'] });
    case '/api/next-race': return json({ status: scenario === 'finished' ? 'season_finished' : 'ok', is_cancelled: scenario === 'cancelled', event_name: 'United States Grand Prix', location: 'Остин', country: 'США', season: 2026, round: 19, race_start_utc: sessions[4].utc_iso, next_session_iso: sessions[0].utc_iso, next_session_name: sessions[0].name });
    case '/api/race-details': return json({ event_name: 'United States Grand Prix', location: 'Остин', country: 'США', season: Number(url.searchParams.get('season')), round: Number(url.searchParams.get('round')), sessions: scenario === 'empty' ? [] : sessions });
    case '/api/weekend-schedule': return json({ sessions: scenario === 'empty' ? [] : sessions });
    case '/api/drivers': return json({ drivers: scenario === 'empty' ? [] : drivers });
    case '/api/constructors': return json({ constructors: scenario === 'empty' ? [] : [{ position: 1, name: 'McLaren', points: 559 }, { position: 2, name: 'Mercedes', points: 382 }, { position: 3, name: 'Ferrari', points: 361 }, { position: 4, name: 'Red Bull Racing', points: 329 }, { position: 5, name: 'Williams', points: 94 }] });
    case '/api/predictions/preview':
    case '/api/predictions/current': return json({ status: 'ok', is_open: true, season: 2026, round: 19, event_name: 'United States Grand Prix', deadline_utc: sessions[4].utc_iso, prediction: null });
    case '/api/web-notifications/unread-count': return json({ unread: previewRead ? 0 : Number(query.get('unread') ?? 2) });
    case '/api/web-notifications': return json({ items: [{ id: 2, title: 'Открыты прогнозы', body: 'Выберите свою тройку на ближайшую гонку.', url: '/predictions', created_at: 1792742400, read_at: previewRead ? 1792828800 : null }, { id: 1, title: 'Как вам последний этап?', body: 'Оцените гонку и выберите пилота дня.', url: '/voting?season=2026&round=18', created_at: 1791806400, read_at: previewRead ? 1792828800 : null }], unread: previewRead ? 0 : 2, next_before: null, push: { enabled: false, public_key: '' } });
    case '/api/engagement/weekly/me': return json({ user_id: member ? 1 : null, weekly: null });
    case '/api/engagement/weekly': return json({});
    case '/api/season': return json({ races: [{ round: 18, event_name: 'Singapore Grand Prix', race_start_utc: '2026-10-11T12:00:00Z', date: '2026-10-11' }, { round: 19, event_name: 'United States Grand Prix', race_start_utc: '2026-10-25T20:00:00Z', date: '2026-10-25' }] });
    case '/api/votes/me': return json({ race_votes: demoVotes, driver_votes: {} });
    case '/api/predictions/personal-season': return json({ latest: null });
    default: return json({});
  }
};
localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'skipped' }));
initializeTheme();
// An existing explicit user choice wins even if a preview link suggests a theme.
const suggestedTheme = query.get('theme');
if ((suggestedTheme === 'light' || suggestedTheme === 'dark') && !storedTheme(localStorage)) setTheme(suggestedTheme);
// Keep the fixture URL reloadable; use the exact production route tree in memory.
await import('../src/App');
const { router } = await import('../src/router');
const initialQuery = new URLSearchParams();
for (const key of ['standing', 'view', 'spotlight']) if (query.has(key)) initialQuery.set(key, query.get(key)!);
const initialPath = query.get('page') === 'menu' ? '/menu' : query.get('page') === 'weekend' ? `/next-race${query.has('season') || query.has('round') ? `?season=${query.get('season') || ''}&round=${query.get('round') || ''}` : ''}` : `/${initialQuery.size ? `?${initialQuery}` : ''}`;
createRoot(document.getElementById('root')!).render(<HeroDataProvider><div className="root"><RouterProvider router={createMemoryRouter(router.routes, { initialEntries: [initialPath] })} /></div><ScrollToTop /></HeroDataProvider>);
const note = document.createElement('aside');
note.textContent = 'Демонстрация дизайна · расписание и очки вымышлены';
note.style.cssText = 'padding:6px 16px;text-align:center;font:12px/1.5 system-ui;background:#faeeec;color:#78221d;position:relative;z-index:101';
document.body.prepend(note);
export {};
