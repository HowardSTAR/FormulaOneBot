type WindowState = {is_open: boolean; opens_at_utc?: string | null; deadline_utc?: string | null};

// The same window applies to guests and authenticated participants.
// The server remains authoritative; dates also protect a stale open page.
export function canEditPrediction(state: WindowState | null, now = Date.now()): boolean {
  if (!state?.is_open) return false;
  const opens = Date.parse(state.opens_at_utc || '');
  const closes = Date.parse(state.deadline_utc || '');
  return Number.isFinite(opens) && Number.isFinite(closes) && now >= opens && now < closes;
}
