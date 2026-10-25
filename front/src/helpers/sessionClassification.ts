export type SessionResultKind = 'practice' | 'quali' | 'sprint-quali' | 'sprint' | 'race';
export type SessionResultRow = {
  position: number; name?: string; driver?: string; code?: string; team?: string;
  best?: string; time?: string | null; gap?: string | null; status?: string | null;
  laps?: number; points?: number; segment?: string; is_favorite_driver?: boolean;
};

export function lapMilliseconds(value?: string | null): number | null {
  const match = value?.trim().match(/^(?:(\d+):)?(\d{1,2})\.(\d{3})$/);
  if (!match) return null;
  const time = (Number(match[1] || 0) * 60 + Number(match[2])) * 1000 + Number(match[3]);
  return time > 0 ? time : null;
}

export function classificationRows(rows: SessionResultRow[], kind: SessionResultKind) {
  if (kind !== 'practice') return [...rows].sort((a, b) => (a.position || Infinity) - (b.position || Infinity));
  return [...rows]
    .sort((a, b) => (lapMilliseconds(a.best) ?? Infinity) - (lapMilliseconds(b.best) ?? Infinity) || (a.position || Infinity) - (b.position || Infinity));
}

export function practiceGap(row: SessionResultRow, leader?: SessionResultRow) {
  const time = lapMilliseconds(row.best), fastest = lapMilliseconds(leader?.best);
  return time !== null && fastest !== null ? (time === fastest ? '—' : `+${((time - fastest) / 1000).toFixed(3)}`) : row.gap || '—';
}
