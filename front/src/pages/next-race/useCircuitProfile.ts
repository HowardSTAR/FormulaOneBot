import { useEffect, useState } from 'react';
import { apiRequest } from '../../helpers/api';
import { matchingProfile, type ProfileResponse, type CircuitProfile } from './circuit-profile';

export function useCircuitProfile(season?: number, round?: number, eventName?: string) {
  const key = `${season}:${round}:${eventName}`;
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; profile: CircuitProfile | null; error: boolean } | null>(null);
  useEffect(() => {
    if (!season || !round || !eventName) return;
    let active = true;
    void apiRequest<ProfileResponse>('/api/circuit-profile', { season, round }).then(response => {
      if (active) setResult({ key, profile: matchingProfile(response, season, round, eventName), error: false });
    }).catch(() => { if (active) setResult({ key, profile: null, error: true }); });
    return () => { active = false; };
  }, [season, round, eventName, key, attempt]);
  return { profile: result?.key === key ? result.profile : null, loading: Boolean(season && round && result?.key !== key), error: result?.key === key && result.error,
    retry: () => { setResult(null); setAttempt(value => value + 1); } };
}
