export type ReminderTiming = {kind: string; start_utc: string | null; duration_minutes: number};
export function reminderClock(reminder: ReminderTiming, now: number) {
  const start = reminder.start_utc ? Date.parse(reminder.start_utc) : NaN;
  if (!Number.isFinite(start) || !Number.isFinite(now)) return {phase: 'unknown', label: 'Время старта уточняется', estimated: false};
  const seconds = Math.max(0, Math.ceil((start - now) / 1000));
  if (now < start) {
    const days = Math.floor(seconds / 86400);
    const hh = Math.floor(seconds / 3600) % 24;
    const mm = Math.floor(seconds / 60) % 60;
    const ss = seconds % 60;
    return {phase: 'before', label: `До старта: ${days ? `${days} д · ` : ''}${[hh, mm, ss].map(n => String(n).padStart(2, '0')).join(':')}`, estimated: false};
  }
  const minutes = reminder.duration_minutes;
  if (!Number.isFinite(minutes) || minutes <= 0) return {phase: 'unknown', label: 'Время старта прошло', estimated: true};
  return now < start + minutes * 60000
    ? {phase: 'live', label: 'УЖЕ ИДЁТ', estimated: true}
    : {phase: 'finished', label: reminder.kind === 'race' ? 'Этап прошёл' : 'Сессия прошла', estimated: true};
}

/** Retain the event and absolute date; don't show a frozen relative countdown. */
export function reminderBody(body: string): string {
  return body.split('\n').map(line => {
    const match = line.match(/^.*?\s+старт:\s*(.+)$/i);
    if (match) return match[1];
    return line.replace(/Скоро\s+(?=свободные заезды|квалификация|спринт|гонка)/i, '');
  }).join('\n').trim();
}
