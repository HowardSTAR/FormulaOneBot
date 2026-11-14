import { useEffect, useState } from 'react';
import { apiRequest } from './api';
type Title = { status: string; season: number; round: number; id?: string; points?: number };
export function useChampionshipTitle(season: number, round: number | null, kind: 'drivers' | 'constructors') {
  const [data, setData] = useState<Title | null>(null);
  useEffect(() => {
    let active = true;
    if (round !== null && season >= 2025) void apiRequest<Title>('/api/championship-title', { season, round_number: round, kind }).then(value => { if (active) setData(value); }).catch(() => { if (active) setData(null); });
    return () => { active = false; };
  }, [season, round, kind]);
  return (id: string, points: number | null) => round !== null && data?.status === 'secured' && data.season === season && data.round === round && data.id === id && data.points === points;
}
