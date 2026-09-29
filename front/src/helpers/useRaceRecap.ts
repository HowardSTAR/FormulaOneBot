import { useEffect, useState } from 'react';
import { apiRequest } from './api';

type Impact = {status: string; items: {category: string; title: string; text: string}[]; note: string; sources?: {title: string; url: string}[]; updated_at?: string};

// Both layouts share one request and retry state, not two parallel source loads.
export function useRaceRecap(season: number, round: number, enabled: boolean) {
  const key = `${season}:${round}`;
  const [response, setResponse] = useState<{key: string; data: Impact} | null>(null);
  const [failedKey, setFailedKey] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    apiRequest<Impact>('/api/race-recap', {season, round_num: round}, 'GET', 45000)
      .then(data => {if (active) setResponse({key, data});})
      .catch(() => {if (active) setFailedKey(key);});
    return () => {active = false;};
  }, [season, round, retry, key, enabled]);
  return {data: response?.key === key ? response.data : null, error: failedKey === key,
    reload: () => {setResponse(null); setFailedKey(null); setRetry(r => r + 1);}};
}
