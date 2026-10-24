import { useEffect, useRef, useState } from 'react';
import { apiRequest } from '../helpers/api';
import { AUTH_CHANGED_EVENT, type AuthState } from '../helpers/auth';
import { visibleInterval } from '../helpers/visibleInterval';
import { latestDockRace, type DockRace } from '../helpers/dockRating';

type RatingState = { race: DockRace; season: number; value: number; canRate: boolean };
export function useDockRating(enabled: boolean, auth: AuthState, season: number) {
  const [data, setData] = useState<RatingState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [celebrate, setCelebrate] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const generation = useRef(0);
  const saving = useRef(false);
  const saveSequence = useRef(0);
  useEffect(() => {
    if (!enabled || !auth.loaded) return;
    const request = ++generation.current;
    const invalidate = () => { generation.current++; };
    const load = async () => {
      try {
        let year = season;
        let schedule = await apiRequest<{ races?: DockRace[] }>('/api/season', { season: year, completed_only: true });
        let race = latestDockRace(schedule.races || [], Date.now());
        if (!race) { year--; schedule = await apiRequest<{ races?: DockRace[] }>('/api/season', { season: year, completed_only: true }); race = latestDockRace(schedule.races || [], Date.now()); }
        if (!race || request !== generation.current) return;
        let value = 0, canRate = auth.personalized;
        if (auth.personalized) {
          try { const votes = await apiRequest<{ race_votes: Record<number, number> }>('/api/votes/me', { season: year }); const saved = votes.race_votes?.[race.round]; value = Number.isInteger(saved) && saved >= 1 && saved <= 5 ? saved : 0; }
          catch { canRate = false; }
        }
        if (request === generation.current) setData({ race, season: year, value, canRate });
      } catch { /* A failed schedule is not evidence that there was a rateable race. */ }
    };
    void load();
    const reset = () => { generation.current++; saveSequence.current++; saving.current = false; setBusy(false); setCelebrate(false); setData(null); setError(''); setAttempt(v => v + 1); };
    const refresh = () => { if (!saving.current && !document.hidden) setAttempt(v => v + 1); };
    const stop = visibleInterval(refresh, 60000);
    window.addEventListener('focus', refresh);
    window.addEventListener(AUTH_CHANGED_EVENT, reset);
    return () => { invalidate(); stop(); window.removeEventListener('focus', refresh); window.removeEventListener(AUTH_CHANGED_EVENT, reset); };
  }, [enabled, auth.loaded, auth.personalized, season, attempt]);
  useEffect(() => { if (!celebrate) return; const timer = window.setTimeout(() => setCelebrate(false), 700); return () => clearTimeout(timer); }, [celebrate]);
  const rate = async (value: number) => {
    if (!data?.canRate || saving.current) return;
    const request = generation.current;
    const save = ++saveSequence.current;
    saving.current = true; setBusy(true); setError('');
    try {
      await apiRequest('/api/votes/race', { season: data.season, round: data.race.round, rating: value }, 'POST');
      if (request === generation.current) { setData({ ...data, value }); setCelebrate(true); }
    } catch (e) { if (request === generation.current) setError(e instanceof Error ? e.message : 'Не удалось сохранить оценку. Попробуйте ещё раз.'); }
    finally { if (save === saveSequence.current) { saving.current = false; setBusy(false); } }
  };
  return { data: enabled && auth.loaded ? data : null, busy, error, celebrate, rate };
}
