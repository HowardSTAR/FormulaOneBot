// Vite-only visual fixture. Uses the real app with deterministic, fictional data.
// No requests are sent to a backend, and no accounts or records are modified.
import gameTracks from '../../app/race_tracks.json';
import circuitProfiles from './fixtures/circuit-profiles.json';
import { entrantBiographyPreview } from './fixtures/entrant-biographies';
import { predictionPreview } from './fixtures/predictions';
import { historyPreview } from './fixtures/history';
import { profilePreview } from './fixtures/profile';
import { accountPreview } from './fixtures/account';
import { gamesPreview } from './fixtures/games';
import { notificationsPreview } from './fixtures/notifications';
import { settingsPreview } from './fixtures/settings';
import { calendarPreviewRaces, calendarPreviewStage } from './fixtures/calendar';
const calendarCircuits = import.meta.glob<string>('../public/static/circuit/*.svg', { query: '?raw', import: 'default' });
import { createRoot } from 'react-dom/client';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { HeroDataProvider } from '../src/context/HeroDataContext';
import { initializeTheme, setTheme, storedTheme } from '../src/helpers/theme';
import { ScrollToTop } from '../src/components/ScrollToTop';
const query = new URLSearchParams(location.search);
const scenario = query.get('state');
const communityTrack = gameTracks.find(track => track.id === query.get('track')) ?? gameTracks[0];
const venue = query.get('venue') === 'singapore' ? 'singapore' : query.get('venue') === 'mexico' ? 'mexico' : 'austin';
const fixtureProfile = circuitProfiles[venue];
const fixtureLocation = { austin: 'Остин', mexico: 'Мехико', singapore: 'Сингапур' }[venue];
const fixtureCountry = { austin: 'США', mexico: 'Мексика', singapore: 'Сингапур' }[venue];
let profileFailures = scenario === 'profile-error' ? 1 : 0;
const member = ['member', 'linked'].includes(query.get('auth') || '');
const linked = query.get('auth') === 'linked';
const demoVotes: Record<number, number> = {};
let previewRead = false;
let constructorFailures = scenario === 'constructors-error' ? 1 : 0;
let entrantFailures = scenario === 'entrant-error' ? 1 : 0;
let driverFailures = scenario === 'drivers-error' ? 1 : 0;
let compareFailures = scenario === 'compare-error' ? 1 : 0;
let calendarFailures = scenario === 'calendar-error' ? 1 : 0;
let resultFailures = scenario === 'results-error' ? 1 : 0;
let podiumFailures = scenario === 'podium-error' ? 1 : 0;
let contactFailures = scenario === 'contact-error' ? 1 : 0;
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
if (query.get('format') === 'standard') {
  sessions[1].name = 'Практика 2';
  sessions[2].name = 'Практика 3';
}
if (scenario === 'past') sessions.forEach(session => { session.utc_iso = session.utc_iso.replace('-10-23', '-10-16').replace('-10-24', '-10-17').replace('-10-25', '-10-18'); });
if (scenario === 'untimed') sessions[0].utc_iso = '';
if (scenario === 'race-untimed') sessions[4].utc_iso = '';
function requestedPreviewStage(season: number, round: number) {
  // Explicit venue demos keep their dedicated profile; calendar clicks always use the selected card.
  if (query.get('page') !== 'calendar' && query.has('venue') && season === fixtureProfile.season && round === fixtureProfile.round) {
    return { season, round, event_name: fixtureProfile.eventName, location: fixtureLocation, country: fixtureCountry,
      date: sessions[4].utc_iso.slice(0,10), race_start_utc: sessions[4].utc_iso, is_cancelled: false, sessions };
  }
  const stage = calendarPreviewStage(season, round);
  return stage && query.get('page') !== 'calendar' && query.get('format') === 'standard' && round === 19 ? { ...stage, sessions } : stage;
}
const portraitAssets = import.meta.glob<string>('../../app/assets/2026/pilots/*.{webp,jpg}', { query: '?url', import: 'default', eager: true });
// Complete illustrative field; portraits come from the verified originals in app-assets.zip.
const previewField = [
  ['NOR','4','norris','Ландо Норрис','McLaren'], ['PIA','81','piastri','Оскар Пиастри','McLaren'],
  ['VER','3','max_verstappen','Макс Ферстаппен','Red Bull Racing'], ['RUS','63','russell','Джордж Расселл','Mercedes'],
  ['LEC','16','leclerc','Шарль Леклер','Ferrari'], ['HAM','44','hamilton','Льюис Хэмилтон','Ferrari'],
  ['ANT','12','antonelli','Кими Антонелли','Mercedes'], ['HAD','6','hadjar','Исак Хаджар','Red Bull Racing'],
  ['GAS','10','gasly','Пьер Гасли','Alpine'], ['COL','43','colapinto','Франко Колапинто','Alpine'],
  ['ALB','23','albon','Александр Албон','Williams'], ['SAI','55','sainz','Карлос Сайнс','Williams'],
  ['ALO','14','alonso','Фернандо Алонсо','Aston Martin'], ['STR','18','stroll','Лэнс Стролл','Aston Martin'],
  ['LAW','30','lawson','Лиам Лоусон','Racing Bulls'], ['LIN','41','lindblad','Арвид Линдблад','Racing Bulls'],
  ['OCO','31','ocon','Эстебан Окон','Haas'], ['BEA','87','bearman','Оливер Берман','Haas'],
  ['HUL','27','hulkenberg','Нико Хюлькенберг','Audi'], ['BOR','5','bortoleto','Габриэл Бортолето','Audi'],
  ['PER','11','perez','Серхио Перес','Cadillac'], ['BOT','77','bottas','Валттери Боттас','Cadillac'],
];
const drivers = previewField.map(([code,number,driverId,name,constructorName], index) => ({
  position: index + 1, code, number, driverId, name, constructorName,
  imageUrl: portraitAssets[`../../app/assets/2026/pilots/${code}.webp`],
  points: [287,272,255,214,196][index] ?? Math.max(0,160 - index * 7),
}));
const constructorIds = ['mclaren', 'mercedes', 'ferrari', 'red_bull', 'williams', 'aston_martin', 'alpine', 'haas', 'rb', 'audi', 'cadillac'];
const constructors = [{ position: 1, name: 'McLaren', points: 559 }, { position: 2, name: 'Mercedes', points: 382 }, { position: 3, name: 'Ferrari', points: 361 }, { position: 4, name: 'Red Bull Racing', points: 329 }, { position: 5, name: 'Williams', points: 94 }, { position: 6, name: 'Aston Martin', points: 72 }, { position: 7, name: 'Alpine', points: 50 }, { position: 8, name: 'Haas', points: 38 }, { position: 9, name: 'Racing Bulls', points: 26 }, { position: 10, name: 'Audi', points: 12 }, { position: 11, name: 'Cadillac', points: 0 }].map((team, index) => ({ ...team, constructorId: constructorIds[index] }));
const previewStats = { grand_prix_races: 0, grand_prix_points: 0, grand_prix_wins: 0, grand_prix_podiums: 0, grand_prix_poles: 0, grand_prix_top10s: 0, fastest_laps: 0, dnfs: 0, sprint_races: 0, sprint_points: 0, sprint_wins: 0, sprint_podiums: 0, sprint_poles: 0, sprint_top10s: 0 };
const previewCareer = { available: false, grand_prix_entered: 0, career_points: 0, highest_race_finish: { position: '—', count: 0 }, podiums: 0, highest_grid: { position: '—', count: 0 }, pole_positions: 0, world_championships: 0, dnfs: 0 };
const predictionsFixture = predictionPreview(query, drivers);
const historyFixture = historyPreview(query, drivers, constructors);
const accountProfileFixture = profilePreview(query);
const accountFixture = accountPreview(query);
const settingsFixture = settingsPreview(query);
const notificationsFixture = notificationsPreview(query);
const gamesFixture = gamesPreview(query);
if (['driver-details', 'constructor-details'].includes(query.get('page') || '')) {
  new MutationObserver(() => {
    document.querySelectorAll<HTMLImageElement>('img[src*="/assets/country/"]').forEach(img => {
      const code = img.src.split('/').pop();
      img.src = `/flags/${code}`;
      img.style.visibility = '';
    });
  }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['src'] });
}
// Native image loads bypass the fetch fixture. Keep their substitute local too.
if (query.get('page') === 'profile' || query.get('tour') === '1') {
  const avatarImage = new URL('./fixtures/profile-avatar.png', import.meta.url).href;
  new MutationObserver(() => {
    document.querySelectorAll<HTMLImageElement>('img[src*="/api/profiles/avatar/v1.png"]').forEach(img => { img.src = avatarImage; });
    document.querySelectorAll<HTMLImageElement>('img[src*="/assets/2026/pilots/"]').forEach(img => {
      const code = img.src.split('/').pop()?.split('.')[0];
      const source = drivers.find(driver => driver.code === code)?.imageUrl;
      if (source && img.src !== new URL(source, location.href).href) img.src = source;
    });
  }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['src'] });
}
window.fetch = async (input, init) => {
  const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
  const url = new URL(input instanceof Request ? input.url : String(input), location.origin);
  if (url.pathname.startsWith('/static/circuit/')) {
    const asset = calendarCircuits[`../public${decodeURIComponent(url.pathname)}`];
    return asset ? new Response(await asset(), { headers: { 'Content-Type': 'image/svg+xml' } }) : new Response('', { status: 404 });
  }
  if (!url.pathname.startsWith('/api/')) return realFetch(input, init);
  if (['reaction-game', 'reflex-grid-game', 'race-game'].includes(query.get('page') || '')) {
    const response = await gamesFixture(url, init);
    if (response) return response;
  }
  if (query.get('page') === 'notifications') {
    const response = await notificationsFixture(url);
    if (response) return response;
  }
  if (url.pathname === '/api/contact-admin') {
    if (scenario === 'contact-sending') await new Promise(resolve => setTimeout(resolve, 1500));
    return contactFailures-- > 0 ? json({ detail: 'Сервис временно недоступен.' }, 503) : json({ status: 'sent', id: 1 });
  }
  if (query.get('page') === 'settings') {
    const response = await settingsFixture(url, init);
    if (response) return response;
  }
  if (query.get('tour') === '1' || ['account', 'settings'].includes(query.get('page') || '')) {
    const response = await accountFixture(url, init);
    if (response) return response;
  }
  if (query.get('page') === 'profile' || query.get('tour') === '1') {
    const response = await accountProfileFixture(url, init);
    if (response) return response;
  }
  if (query.get('page') === 'predictions' || query.get('tour') === '1') {
    const response = await predictionsFixture(url, init);
    if (response) return response;
  }
  if (query.get('page') === 'history') {
    const response = historyFixture(url);
    if (response) return response;
  }
  if ((init?.method || (input instanceof Request ? input.method : 'GET')) !== 'GET') {
    if (query.get('demoVotes') !== '0' && url.pathname === '/api/votes/race' && init?.method === 'POST') {
      const body = JSON.parse(String(init.body));
      if (voteFailures-- > 0) return json({ detail: 'Не удалось сохранить оценку' }, 503);
      if (!member || !Number.isInteger(body.rating) || body.rating < 1 || body.rating > 5) return json({}, 400);
      demoVotes[body.round] = body.rating;
      return json({ status: 'ok' }); // Local fixture only; no backend request.
    }
    if (query.get('demoVotes') === '1' && url.pathname === '/api/web-notifications/read' && init?.method === 'POST') { previewRead = true; return json({ ok: true }); }
    return new Response('Preview is read only', { status: 405 });
  }
  if (scenario === 'error' && ['/api/next-race', '/api/drivers', '/api/constructors'].includes(url.pathname)) return json({ detail: 'Демонстрация ошибки' }, 503);
  if (scenario === 'schedule-error' && url.pathname === '/api/weekend-schedule') return json({ detail: 'Демонстрация ошибки расписания' }, 503);
  if (['/api/practice-results', '/api/quali-results', '/api/sprint-quali-results', '/api/sprint-results', '/api/race-results'].includes(url.pathname)) {
    if (url.pathname === '/api/race-results' && podiumFailures-- > 0) return json({ detail: 'Не удалось получить подиум' }, 503);
    if (resultFailures-- > 0) return json({ detail: 'Демонстрация ошибки результатов' }, 503);
    const qualifying = url.pathname.includes('quali-results');
    const stage = requestedPreviewStage(Number(url.searchParams.get('season') || 2026), Number(url.searchParams.get('round') || 19));
    if (!stage) return json({ detail: 'Этап отсутствует в демо-календаре' }, 404);
    return json({ race_info: { event_name: stage.event_name }, season: Number(url.searchParams.get('season') || 2026), round: scenario === 'results-mismatch' ? 18 : Number(url.searchParams.get('round') || 19),
      session: Number(url.searchParams.get('session') || 1), available_sessions: stage.sessions.some(session => /Спринт/.test(session.name)) ? [1] : [1,2,3], is_sprint_weekend: stage.sessions.some(session => /Спринт/.test(session.name)),
      results: scenario === 'results-empty' ? [] : drivers.map((driver, index) => ({ position: index + 1, segment: qualifying ? (index < 10 ? 'Q3' : index < 16 ? 'Q2' : 'Q1') : undefined, time: index ? `+${index * 3}.084` : '1:32:14.052', driver: driver.code, code: driver.code, name: driver.name, team: driver.constructorName, points: (url.pathname === '/api/sprint-results' ? [8,7,6,5,4,3,2,1] : [25,18,15,12,10,8,6,4,2,1])[index] ?? 0,
        best: `1:${36 + Math.floor((52 + index * 84) / 1000)}.${String((52 + index * 84) % 1000).padStart(3, '0')}`, gap: index ? `+${(index * .084).toFixed(3)}` : null, laps: 26 - index, is_favorite_driver: member && index === 0 })) });
  }
  if (scenario === 'personal-error' && ['/api/predictions/current', '/api/web-notifications/unread-count', '/api/predictions/personal-season'].includes(url.pathname)) return json({ detail: 'Демонстрация ошибки личного раздела' }, 503);
  switch (url.pathname) {
    case '/api/compare/multi':
    case '/api/compare/teams/multi': {
      if (compareFailures-- > 0) return json({ detail: 'Сравнение временно недоступно. Попробуйте снова.' }, 503);
      if (scenario === 'compare-loading') return new Promise<Response>(() => {});
      if (scenario === 'compare-empty') return json({ labels: [], series: [] });
      const teamMode = url.pathname.includes('/teams/');
      const selected = (url.searchParams.get(teamMode ? 'teams' : 'drivers') || '').split(',').filter(Boolean);
      const labels = ['Австралия', 'Китай', 'Япония', 'Бахрейн', 'Саудовская Аравия', 'Майами', 'Эмилия-Романья', 'Монако', 'Испания', 'Канада', 'Австрия', 'Великобритания'];
      // Deterministic fictional values for layout and interaction checks only.
      const series = selected.map(code => {
        const index = teamMode ? constructors.findIndex(row => row.name === code) : drivers.findIndex(row => row.code === code);
        const history = labels.map((_, round) => Math.max(0, 25 - ((index * 5 + round * 7) % 26)));
        return { code, history, race_wins: Math.max(0, 7 - index), quali_wins: Math.max(0, 8 - index), quali_samples: labels.length, total_points: history.reduce((sum, value) => sum + value, 0) + 20 - index, average_points: history.reduce((sum, value) => sum + value, 0) / labels.length };
      });
      return json({ labels, series });
    }
    case '/api/race-recap': return json({ status: 'waiting', items: [], note: 'Демонстрационный обзор: ожидаем подтверждённые данные.' });
    case '/api/auth/me': return member ? json({ id: 1, email: null, telegram_id: linked ? 1 : null, role: 'user', email_verified: true, display_name: 'Болельщик' }) : json({}, 401);
    case '/api/favorites': return scenario === 'favorites-error' ? json({}, 503) : json(scenario === 'favorites-empty' ? { drivers: [], teams: [] } : scenario === 'favorites-missing' ? { drivers: ['OLD'], teams: ['Old Team'] } : { drivers: ['PIA', 'NOR'], teams: ['McLaren'] });
    case '/api/next-race': return json({ status: scenario === 'finished' ? 'season_finished' : 'ok', is_cancelled: scenario === 'cancelled', event_name: fixtureProfile.eventName, location: fixtureLocation, country: fixtureCountry, season: 2026, round: fixtureProfile.round, race_start_utc: sessions[4].utc_iso, next_session_iso: sessions[0].utc_iso, next_session_name: sessions[0].name });
    case '/api/race-details': {
      const stage = requestedPreviewStage(Number(url.searchParams.get('season')), Number(url.searchParams.get('round')));
      if (!stage) return json({ detail: 'Этап отсутствует в демо-календаре' }, 404);
      return json({ ...stage, ...(scenario === 'stage-mismatch' ? { round: stage.round + 1 } : {}), sessions: scenario === 'empty' ? [] : stage.sessions });
    }
    case '/api/circuit-profile': {
      if (profileFailures-- > 0) return json({ detail: 'Профиль временно недоступен' }, 503);
      const season = Number(url.searchParams.get('season'));
      const round = Number(url.searchParams.get('round'));
      const stage = requestedPreviewStage(season, round);
      const sample = Object.values(circuitProfiles).find(profile => profile.season === season && profile.eventName === stage?.event_name);
      const profile = scenario === 'profile-unavailable' || !sample ? null : { ...sample, round, stale: scenario === 'profile-stale' };
      return json({ status: profile ? profile.stale ? 'stale' : 'ok' : 'unavailable', season, round, profile });
    }
    case '/api/weekend-schedule': return json({ sessions: scenario === 'empty' ? [] : sessions });
    case '/api/drivers': {
      if (driverFailures-- > 0) return json({ detail: 'Зачёт временно недоступен. Попробуйте снова.' }, 503);
      if (scenario === 'drivers-loading') return new Promise<Response>((_, reject) => { init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))); });
      const season = Number(url.searchParams.get('season') || 2026);
      const field = scenario === 'drivers-single' ? drivers.slice(0, 1) : drivers;
      return json({ drivers: ['empty', 'drivers-empty'].includes(scenario || '') ? [] : field.map((driver, index) => ({
        ...driver, points: scenario === 'drivers-zero' ? 0 : scenario === 'drivers-missing' && index === 1 ? null : driver.points,
        is_favorite: member && driver.code === 'NOR', imageUrl: season === 2026 ? driver.imageUrl : undefined,
      })) });
    }
    case '/api/constructors': {
      if (constructorFailures-- > 0) return json({ detail: 'Зачёт команд временно недоступен. Попробуйте снова.' }, 503);
      if (scenario === 'constructors-loading') return new Promise<Response>((_, reject) => { init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))); });
      return json({ constructors: ['empty', 'constructors-empty'].includes(scenario || '') ? [] : constructors.map((team, index) => ({ ...team, points: scenario === 'constructors-zero' ? 0 : scenario === 'constructors-missing' && index === 1 ? null : scenario === 'constructors-tied' && index === 1 ? constructors[0].points : team.points, is_favorite: member && team.name === 'McLaren' })) });
    }
    case '/api/driver-details': {
      if (entrantFailures-- > 0) return json({ detail: 'Карточка временно недоступна' }, 503);
      if (scenario === 'entrant-loading') return new Promise<Response>(() => {});
      const row = drivers.find(driver => driver.code === url.searchParams.get('code') || driver.driverId === url.searchParams.get('driverId'));
      if (!row) return json({ detail: 'Нет пилота в демо' }, 404);
      const [givenName, ...familyName] = row.name.split(' ');
      return json({ driverId: row.driverId || row.code.toLowerCase(), code: row.code, givenName, familyName: familyName.join(' '), permanentNumber: row.number, ...entrantBiographyPreview('driver', row.code, scenario), headshot_url: row.imageUrl || '', season: Number(url.searchParams.get('season') || 2026), season_stats: scenario === 'entrant-zero' ? { ...previewStats, position: 0, points: 0 } : { ...previewStats, grand_prix_races: 18, grand_prix_points: 260, grand_prix_podiums: 10, grand_prix_poles: 4, grand_prix_top10s: 15, grand_prix_wins: 5, sprint_races: 4, sprint_points: 27, sprint_top10s: 3, position: row.position, points: row.points }, career_stats: scenario === 'entrant-empty' ? previewCareer : { ...previewCareer, available: true, grand_prix_entered: 120, career_points: 1112.5, podiums: 35, highest_race_finish: { position: 1, count: 9 }, highest_grid: { position: 1, count: 12 }, pole_positions: 12 } });
    }
    case '/api/constructor-details': {
      if (entrantFailures-- > 0) return json({ detail: 'Карточка временно недоступна' }, 503);
      if (scenario === 'entrant-loading') return new Promise<Response>(() => {});
      const normalize = (value: string) => value.toLowerCase().replace(/[^a-z]/g, '');
      const row = constructors.find(team => [normalize(team.name), normalize(team.constructorId)].includes(normalize(url.searchParams.get('constructorId') || '')));
      if (!row) return json({ detail: 'Нет команды в демо' }, 404);
      return json({ constructorId: normalize(row.name), name: row.name, ...entrantBiographyPreview('team', row.constructorId, scenario), drivers: scenario === 'entrant-empty' ? [] : drivers.filter(driver => driver.constructorName === row.name).map(driver => { const [givenName, ...familyName] = driver.name.split(' '); return { driverId: driver.driverId, code: driver.code, givenName, familyName: familyName.join(' '), permanentNumber: driver.number, nationality: entrantBiographyPreview('driver', driver.code, scenario).nationality, headshot_url: driver.imageUrl }; }), principal: scenario === 'entrant-empty' ? null : { id: 'demo-principal', name: 'Руководитель команды', role: 'Руководитель', photo_url: new URL('./fixtures/profile-avatar.png', import.meta.url).href }, season: Number(url.searchParams.get('season') || 2026), season_stats: { ...previewStats, grand_prix_races: 18, grand_prix_entries: 36, grand_prix_points_finishes: 30, grand_prix_unclassified: 3, highest_race_finish: { position: 1, count: 8 }, highest_grid: { position: 1, count: 7 }, grand_prix_wins: 8, grand_prix_podiums: 22, grand_prix_poles: 7, grand_prix_points: 502, position: row.position, points: row.points }, career_stats: scenario === 'entrant-empty' ? previewCareer : { ...previewCareer, available: true, grand_prix_entered: 1860, grand_prix_events: 930, career_points: 10200, podiums: 500, pole_positions: 140, world_championships: 8, highest_race_finish: { position: 1, count: 190 } } });
    }
    case '/api/predictions/preview':
    case '/api/predictions/current': return json({ status: 'ok', is_open: true, season: 2026, round: 19, event_name: 'United States Grand Prix', deadline_utc: sessions[4].utc_iso, prediction: null });
    case '/api/web-notifications/unread-count': return json({ unread: previewRead ? 0 : Number(query.get('unread') ?? 2) });
    case '/api/web-notifications': return json({ items: [{ id: 2, title: 'Открыты прогнозы', body: 'Выберите свою тройку на ближайшую гонку.', url: '/predictions', created_at: 1792742400, read_at: previewRead ? 1792828800 : null }, { id: 1, title: 'Как вам последний этап?', body: 'Оцените гонку и выберите пилота дня.', url: '/voting?season=2026&round=18', created_at: 1791806400, read_at: previewRead ? 1792828800 : null }], unread: previewRead ? 0 : 2, next_before: null, push: { enabled: false, public_key: '' } });
    case '/api/engagement/weekly/me': return json({ user_id: member ? 1 : null, weekly: null });
    case '/api/engagement/weekly': return json({ track_id: communityTrack.id, name: communityTrack.name, start: '2026-10-26T00:00:00Z', end: '2026-11-02T00:00:00Z', entries: [] });
    case '/api/predictions/leagues': return json({ leagues: [] });
    case '/api/engagement/mine': return json({ referrals: { arrived: 0, activated: 0, returned: 0 }, badges: [], shares: [] });
    case '/api/season': {
      if (!url.searchParams.has('completed_only') && calendarFailures-- > 0) return json({ detail: 'Календарь временно недоступен' }, 503);
      if (scenario === 'calendar-loading' && !url.searchParams.has('completed_only')) return new Promise<Response>((_, reject) => { init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))); });
      return json({ races: scenario === 'calendar-empty' ? [] : calendarPreviewRaces(Number(url.searchParams.get('season') || 2026)) });
    }
    case '/api/votes/me': return json({ race_votes: demoVotes, driver_votes: {} });
    case '/api/predictions/personal-season': return json({ latest: null });
    default: return json({});
  }
};
if (query.get('tour') === '1') localStorage.removeItem('turbotears-onboarding-v2');
else localStorage.setItem('turbotears-onboarding-v2', JSON.stringify({ status: 'skipped' }));
initializeTheme();
// An existing explicit user choice wins even if a preview link suggests a theme.
const suggestedTheme = query.get('theme');
if ((suggestedTheme === 'light' || suggestedTheme === 'dark') && !storedTheme(localStorage)) setTheme(suggestedTheme);
// Keep the fixture URL reloadable; use the exact production route tree in memory.
await import('../src/App');
const { router } = await import('../src/router');
const initialQuery = new URLSearchParams();
for (const key of ['standing', 'view', 'spotlight']) if (query.has(key)) initialQuery.set(key, query.get(key)!);
const weekendQuery = new URLSearchParams();
for (const key of ['season', 'round', 'session', 'tab', 'championship']) if (query.has(key)) weekendQuery.set(key, query.get(key)!);
const calendarQuery = new URLSearchParams();
for (const key of ['year', 'filter', 'round']) if (query.has(key)) calendarQuery.set(key, query.get(key)!);
const resultRoutes = ['community', 'notifications', 'driver-details', 'constructor-details', 'reaction-game', 'reflex-grid-game', 'race-game','contact-admin','settings','account','profile','history','compare','predictions','drivers','constructors','practice-results','quali-results','sprint-quali-results','sprint-results','race-results'];
const resultQuery = new URLSearchParams(weekendQuery);
for (const key of ['kind', 'ids', 'from', 'to', 'roster', 'code', 'driverId', 'constructorId']) if (query.has(key)) resultQuery.set(key, query.get(key)!);
if (query.has('tab')) resultQuery.set('tab', query.get('tab')!);
if (query.has('mode')) resultQuery.set('mode', query.get('mode')!);
if (query.has('year')) resultQuery.set('year', query.get('year')!);
const profileRoute = query.get('page') === 'profile' && query.get('owner') === '0' ? `/profile/1?${resultQuery}` : null;
const initialPath = resultRoutes.includes(query.get('page') || '') ? `/${query.get('page')}?${resultQuery}` : query.get('page') === 'menu' ? '/menu' : query.get('page') === 'calendar' ? `/season${calendarQuery.size ? `?${calendarQuery}` : ''}` : query.get('page') === 'weekend' ? `/next-race${weekendQuery.size ? `?${weekendQuery}` : ''}` : `/${initialQuery.size ? `?${initialQuery}` : ''}`;
createRoot(document.getElementById('root')!).render(<HeroDataProvider><div className="root"><RouterProvider router={createMemoryRouter(router.routes, { initialEntries: [profileRoute || initialPath] })} /></div><ScrollToTop /></HeroDataProvider>);
const note = document.createElement('aside');
note.textContent = ['driver-details', 'constructor-details'].includes(query.get('page') || '') ? 'Предпросмотр · статистика иллюстративная · биографии по Wikipedia' : 'Демо · данные вымышлены · оценки до перезагрузки';
note.style.cssText = 'padding:6px 16px;text-align:center;font:12px/1.5 system-ui;background:#faeeec;color:#78221d;position:relative;z-index:101';
document.body.prepend(note);
export {};
