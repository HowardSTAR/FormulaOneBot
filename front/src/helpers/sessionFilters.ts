import { useCallback } from 'react';
import type { SetStateAction } from 'react';
import { useSearchParams } from 'react-router-dom';

export function readSessionFilters(params: URLSearchParams, minYear = 1950, currentYear = new Date().getFullYear()) {
  const year = Number(params.get('season'));
  const round = Number(params.get('round'));
  const selectedRound = Number.isInteger(round) && round > 0 && round <= 40 ? round : null;
  return { season: Number.isInteger(year) && year >= minYear && year <= currentYear ? year : currentYear,
    selectedRound, mode: (params.get('mode') === 'archive' || (params.get('mode') !== 'latest' && selectedRound !== null) ? 'archive' : 'latest') as 'latest' | 'archive' };
}

export function useSessionFilters(minYear = 1950) {
  const [params, setParams] = useSearchParams();
  const filters = readSessionFilters(params, minYear);
  const setMode = useCallback((mode: 'latest' | 'archive') => setParams(previous => {
    const next = new URLSearchParams(previous); next.set('mode', mode); return next;
  }), [setParams]);
  const setSeason = (season: number) => setParams(previous => {
    const next = new URLSearchParams(previous); next.set('season', String(season)); next.set('mode', 'archive'); next.delete('round'); return next;
  });
  const setSelectedRound = useCallback((value: SetStateAction<number | null>, session?: 1 | 2 | 3) => setParams(previous => {
    const current = readSessionFilters(previous, minYear);
    const round = typeof value === 'function' ? value(current.selectedRound) : value;
    const next = new URLSearchParams(previous);
    // Explicit mode prevents the automatically selected archive round changing "latest".
    next.set('mode', current.mode);
    if (session !== undefined) next.set('session', String(session));
    if (round !== null) next.set('round', String(round)); else next.delete('round');
    return next;
  }, {replace: typeof value === 'function' || value === null}), [setParams, minYear]);
  const session = Number(params.get('session'));
  const selectedSession: 1 | 2 | 3 = session === 2 || session === 3 ? session : 1;
  const setSelectedSession = (value: 1 | 2 | 3) => setParams(previous => {
    const next = new URLSearchParams(previous); next.set('session', String(value)); return next;
  });
  return {...filters, setMode, setSeason, setSelectedRound, selectedSession, setSelectedSession};
}
