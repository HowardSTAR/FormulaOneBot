import { useEffect, useState } from 'react';
import { apiRequest } from '../../helpers/api';
import { AUTH_CHANGED_EVENT, type AuthState } from '../../helpers/auth';
import type { HomeFavorites, SpotlightEntry } from './spotlight-model';

type Data = { key: string; drivers: SpotlightEntry[]; teams: SpotlightEntry[]; favorites: HomeFavorites; failed: boolean; favoritesFailed: boolean };
export function useSpotlightData(season: number, auth: AuthState) {
  const [data, setData] = useState<Data | null>(null);
  const [revision, setRevision] = useState(0);
  const key = `${season}:${auth.loaded}:${auth.signedIn}:${revision}`;
  useEffect(() => {
    const changed = () => setRevision(value => value + 1);
    window.addEventListener(AUTH_CHANGED_EVENT, changed);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, changed);
  }, []);
  useEffect(() => {
    if (!auth.signedIn) return;
    let active = true;
    void Promise.allSettled([
      apiRequest<{ drivers?: SpotlightEntry[] }>('/api/drivers', { season }),
      apiRequest<{ constructors?: SpotlightEntry[] }>('/api/constructors', { season }),
      auth.loaded && auth.signedIn ? apiRequest<HomeFavorites>('/api/favorites') : Promise.resolve({ drivers: [], teams: [] }),
    ]).then(([drivers, teams, favorites]) => {
      if (active) setData({ key, drivers: drivers.status === 'fulfilled' ? drivers.value.drivers || [] : [],
        teams: teams.status === 'fulfilled' ? teams.value.constructors || [] : [],
        favorites: favorites.status === 'fulfilled' ? { drivers: favorites.value.drivers || [], teams: favorites.value.teams || [] } : { drivers: [], teams: [] },
        failed: drivers.status === 'rejected' || teams.status === 'rejected', favoritesFailed: favorites.status === 'rejected' });
    });
    return () => { active = false; };
  }, [season, auth.loaded, auth.signedIn, key]);
  return { data: data?.key === key ? data : null, retry: () => setRevision(value => value + 1) };
}
