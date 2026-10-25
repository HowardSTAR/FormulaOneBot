import type { SessionItem } from '../../context/HeroDataContext';

export type StageSelection = { kind: 'next' } | { kind: 'selected'; season: number; round: number } | { kind: 'invalid' };

export function stageSelection(season: string | null, round: string | null): StageSelection {
  if (season === null && round === null) return { kind: 'next' };
  if (!/^\d{4}$/.test(season ?? '') || !/^\d{1,2}$/.test(round ?? '') || Number(season) < 1950 || Number(season) > 2100 || Number(round) < 1 || Number(round) > 30) return { kind: 'invalid' };
  return { kind: 'selected', season: Number(season), round: Number(round) };
}

// Older race-details responses omit season, but must still identify their round.
export function matchesWeekendStage(response: { season?: number; round?: number | null }, season: number, round: number) {
  return response.round === round && (response.season === undefined || response.season === season);
}

export function sessionStart(session: SessionItem): number | null {
  if (!session.utc_iso || !/(Z|[+-]\d\d:\d\d)$/i.test(session.utc_iso)) return null;
  const time = Date.parse(session.utc_iso);
  return Number.isFinite(time) ? time : null;
}

export function sortedWeekend(sessions: SessionItem[]): SessionItem[] {
  return [...sessions].sort((a, b) => (sessionStart(a) ?? Infinity) - (sessionStart(b) ?? Infinity));
}

export function sessionResultsPath(name: string): string | null {
  if (/спринт.*квалиф|sprint.*qual|sprint.*shootout/i.test(name)) return '/sprint-quali-results';
  if (/спринт|sprint/i.test(name)) return '/sprint-results';
  if (/квалиф|qualifying/i.test(name)) return '/quali-results';
  if (/^(гонка|race)$/i.test(name.trim())) return '/race-results';
  if (/практик|свободн|practice|^fp[123]$/i.test(name)) return '/practice-results';
  return null;
}

export function weekendSession(name: string): { id: string; path: string; practice?: number } | null {
  const path = sessionResultsPath(name);
  if (!path) return null;
  if (path === '/practice-results') {
    const number = Number(name.match(/([123])\s*$/)?.[1]);
    return number ? { id: `fp${number}`, path, practice: number } : null;
  }
  return { id: path.slice(1).replace('-results', ''), path };
}

export function weekendSessionLink(season: number, round: number, name?: string) {
  const params = new URLSearchParams({ season: String(season), round: String(round) });
  const session = name && weekendSession(name);
  if (session) params.set('session', session.id);
  return `/next-race?${params}`;
}

// Providers can return a previous practice when the requested one is unavailable.
// An embedded stage result must never label those rows as the selected stage.
export function matchesWeekendResult(response: { season?: number; round?: number | null; session?: number }, season: number, round: number, practice?: number) {
  return response.season === season && response.round === round && (practice === undefined || response.session === practice);
}

export function availableResults(sessions: SessionItem[], now: number) {
  const seen = new Set<string>();
  return sortedWeekend(sessions).flatMap(session => {
    const start = sessionStart(session), path = sessionResultsPath(session.name);
    if (start === null || start > now || !path || seen.has(path)) return [];
    seen.add(path);
    return [{ path, title: path === '/practice-results' ? 'Свободные заезды' : session.name }];
  });
}

export function weekendResultGroups(sessions: SessionItem[]) {
  const definitions = [
    { id: 'practice', label: 'Практика', ids: ['fp1', 'fp2', 'fp3'], labels: ['P1', 'P2', 'P3'] },
    { id: 'sprint', label: 'Спринт', ids: ['sprint-quali', 'sprint'], labels: ['SQ', 'SR'] },
    { id: 'weekend', label: 'Уик-энд', ids: ['quali', 'race'], labels: ['Квалификация', 'Гонка'] },
  ];
  return definitions.map(group => ({ id: group.id, label: group.label, sessions: group.ids.flatMap((id, index) => {
    const session = sessions.find(item => weekendSession(item.name)?.id === id);
    return session ? [{ id, label: group.labels[index], session }] : [];
  }) })).filter(group => group.sessions.length > 0);
}
