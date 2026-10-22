import type { SessionItem } from '../../context/HeroDataContext';

export type StageSelection = { kind: 'next' } | { kind: 'selected'; season: number; round: number } | { kind: 'invalid' };

export function stageSelection(season: string | null, round: string | null): StageSelection {
  if (season === null && round === null) return { kind: 'next' };
  if (!/^\d{4}$/.test(season ?? '') || !/^\d{1,2}$/.test(round ?? '') || Number(season) < 1950 || Number(season) > 2100 || Number(round) < 1 || Number(round) > 30) return { kind: 'invalid' };
  return { kind: 'selected', season: Number(season), round: Number(round) };
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

export function availableResults(sessions: SessionItem[], now: number) {
  const seen = new Set<string>();
  return sortedWeekend(sessions).flatMap(session => {
    const start = sessionStart(session), path = sessionResultsPath(session.name);
    if (start === null || start > now || !path || seen.has(path)) return [];
    seen.add(path);
    return [{ path, title: path === '/practice-results' ? 'Свободные заезды' : session.name }];
  });
}
