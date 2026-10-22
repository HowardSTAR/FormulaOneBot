import type { NextRaceResponse, SessionItem } from '../../context/HeroDataContext';

export function orderedSessions(sessions: SessionItem[]) {
  return sessions.filter((session): session is SessionItem & { utc_iso: string } => Boolean(session.utc_iso) && Number.isFinite(Date.parse(session.utc_iso!)))
    .sort((a, b) => Date.parse(a.utc_iso) - Date.parse(b.utc_iso));
}
export function upcomingSession(sessions: SessionItem[], race: NextRaceResponse | null, now: number): SessionItem | null {
  if (race?.is_cancelled || race?.status !== 'ok') return null;
  const next = orderedSessions(sessions).find(session => Date.parse(session.utc_iso) > now);
  if (next) return next;
  // A published start time alone cannot establish a live or completed session.
  const utc_iso = race.next_session_iso || race.race_start_utc;
  return utc_iso && Number.isFinite(Date.parse(utc_iso)) && Date.parse(utc_iso) > now
    ? { name: race.next_session_name || 'Гонка', utc_iso } : null;
}
export function countdownLabel(iso: string, now: number): string {
  const target = Date.parse(iso);
  if (!Number.isFinite(target)) return 'Время уточняется';
  const minutes = Math.max(0, Math.ceil((target - now) / 60000));
  if (!minutes) return 'Старт по расписанию';
  const days = Math.floor(minutes / 1440), hours = Math.floor((minutes % 1440) / 60), rest = minutes % 60;
  return `Через ${days ? `${days} д ` : ''}${hours ? `${hours} ч ` : ''}${rest || (!days && !hours) ? `${rest} мин` : ''}`.trim();
}
