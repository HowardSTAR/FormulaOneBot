export type CalendarRace = {
  round: number;
  event_name: string;
  location: string;
  country?: string;
  date: string;
  is_cancelled?: boolean;
  first_session_start_utc?: string | null;
  race_start_utc?: string | null;
  quali_start_utc?: string | null;
  sprint_start_utc?: string | null;
  sprint_quali_start_utc?: string | null;
  practice1_start_utc?: string | null;
  practice2_start_utc?: string | null;
  practice3_start_utc?: string | null;
};
export type CalendarFilter = 'upcoming' | 'past' | 'all';
export type CalendarRaceStatus = 'cancelled' | 'weekend' | 'live' | 'pending' | 'recent' | 'next' | 'finished' | 'future' | 'unknown';
const HOUR = 3_600_000;

export function parseRaceTime(value?: string | null): number | null {
  const time = value ? Date.parse(value) : NaN;
  return Number.isFinite(time) ? time : null;
}
export function readCalendarQuery(params: URLSearchParams, currentYear = new Date().getFullYear()) {
  const year = Number(params.get('year'));
  const season = Number.isInteger(year) && year >= 1950 && year <= currentYear ? year : currentYear;
  const round = Number(params.get('round'));
  const filter = params.get('filter');
  return {year: season, round: Number.isInteger(round) && round > 0 && round <= 40 ? round : null,
    filter: (filter === 'upcoming' || filter === 'past' || filter === 'all' ? filter : season === currentYear ? 'upcoming' : 'all') as CalendarFilter};
}
export function isCompletedStatus(status?: CalendarRaceStatus) {
  return status === 'finished' || status === 'recent' || status === 'pending';
}
export function sessionHasStarted(value: string | null | undefined, nowMs: number, fallback = false) {
  const start = parseRaceTime(value);
  return start === null ? fallback : start <= nowMs;
}
export function calendarState(races: CalendarRace[], year: number, nowMs: number, latestReadyRound: number | null = null, currentYear = new Date(nowMs).getFullYear()) {
  const statusByRound = new Map<number, CalendarRaceStatus>();
  const upcoming = races.filter(race => !race.is_cancelled && (parseRaceTime(race.race_start_utc) ?? parseRaceTime(race.date) ?? -Infinity) > nowMs);
  const nextRace = [...upcoming].sort((a, b) => (parseRaceTime(a.race_start_utc) ?? parseRaceTime(a.date)!) - (parseRaceTime(b.race_start_utc) ?? parseRaceTime(b.date)!))[0];
  for (const race of races) {
    const start = parseRaceTime(race.race_start_utc);
    const date = parseRaceTime(race.date);
    const end = start !== null ? start + 4 * HOUR : date !== null ? date + 24 * HOUR : null;
    const sessions = [race.first_session_start_utc, ...raceSessions(race).map(session => session.iso)].map(parseRaceTime).filter((time): time is number => time !== null);
    const weekendStart = sessions.length ? Math.min(...sessions) : null;
    let status: CalendarRaceStatus;
    if (race.is_cancelled) status = 'cancelled';
    else if (year < currentYear) status = 'finished';
    else if (race.round === latestReadyRound && start !== null && start <= nowMs) status = nowMs - start <= 24 * HOUR ? 'recent' : 'finished';
    else if (end !== null && nowMs >= end) status = start !== null && nowMs - start <= 24 * HOUR ? 'pending' : 'finished';
    else if (start !== null && start <= nowMs) status = 'live';
    else if (weekendStart !== null && weekendStart <= nowMs) status = 'weekend';
    else if (race.round === nextRace?.round) status = 'next';
    else status = date !== null || start !== null ? 'future' : 'unknown';
    statusByRound.set(race.round, status);
  }
  return {statusByRound, nextRound: nextRace?.round ?? null};
}
export function filteredCalendar(races: CalendarRace[], statuses: Map<number, CalendarRaceStatus>, filter: CalendarFilter) {
  return races.filter(race => filter === 'all' || (filter === 'past'
    ? isCompletedStatus(statuses.get(race.round))
    : !race.is_cancelled && !isCompletedStatus(statuses.get(race.round))));
}
export function selectedCalendarRace(races: CalendarRace[], round: number | null, filter: CalendarFilter, statuses: Map<number, CalendarRaceStatus>) {
  return races.find(race => race.round === round)
    ?? (filter === 'past' ? races.at(-1) : races.find(race => ['live', 'weekend', 'next'].includes(statuses.get(race.round) ?? '')))
    ?? races[0] ?? null;
}
export const calendarStatusLabel: Record<CalendarRaceStatus, string> = {
  cancelled: 'Отменён', weekend: 'Уик-энд идёт', live: 'Гонка по расписанию', pending: 'Итоги уточняются', recent: 'Гонка завершена',
  next: 'Ближайший этап', finished: 'Прошёл', future: 'Предстоящий этап', unknown: 'Дата уточняется',
};
export function raceDateParts(race: CalendarRace, timeZone: string) {
  const hasTime = parseRaceTime(race.race_start_utc) !== null;
  const value = hasTime ? race.race_start_utc : race.date;
  const timestamp = parseRaceTime(value);
  if (timestamp === null) return {day: '—', month: '', label: 'Дата уточняется'};
  // A date without a time is a calendar date, not midnight in the viewer's timezone.
  const zone = hasTime ? timeZone : 'UTC';
  const date = new Date(timestamp);
  return {day: date.toLocaleDateString('ru-RU', {timeZone: zone, day: 'numeric'}),
    month: date.toLocaleDateString('ru-RU', {timeZone: zone, month: 'short'}).replace('.', ''),
    label: date.toLocaleDateString('ru-RU', {timeZone: zone, day: '2-digit', month: 'short'}).replace('.', '')};
}
export function raceSessions(race: CalendarRace) {
  return [
    {key: 'practice1', label: 'Практика 1', iso: race.practice1_start_utc},
    {key: 'practice2', label: 'Практика 2', iso: race.practice2_start_utc},
    {key: 'practice3', label: 'Практика 3', iso: race.practice3_start_utc},
    {key: 'sprintQuali', label: 'Спринт-квалификация', iso: race.sprint_quali_start_utc},
    {key: 'sprint', label: 'Спринт', iso: race.sprint_start_utc},
    {key: 'quali', label: 'Квалификация', iso: race.quali_start_utc},
    {key: 'race', label: 'Гонка', iso: race.race_start_utc},
  ].filter(session => session.iso || session.key === 'quali' || session.key === 'race');
}
export function calendarResultLinks(race: CalendarRace, year: number, nowMs: number, status?: CalendarRaceStatus) {
  if (race.is_cancelled) return [];
  const fallback = isCompletedStatus(status);
  return [
    {key: 'sprintQuali', label: 'Спринт-квалификация', page: 'sprint-quali-results', visible: Boolean(race.sprint_quali_start_utc) && sessionHasStarted(race.sprint_quali_start_utc, nowMs)},
    {key: 'sprint', label: 'Спринт', page: 'sprint-results', visible: Boolean(race.sprint_start_utc) && sessionHasStarted(race.sprint_start_utc, nowMs)},
    {key: 'quali', label: 'Квалификация', page: 'quali-results', visible: sessionHasStarted(race.quali_start_utc, nowMs, fallback)},
    {key: 'race', label: 'Гонка', page: 'race-results', visible: sessionHasStarted(race.race_start_utc, nowMs, fallback)},
  ].filter(link => link.visible).map(link => ({key: link.key, label: link.label, href: `/${link.page}?mode=archive&season=${year}&round=${race.round}`}));
}
