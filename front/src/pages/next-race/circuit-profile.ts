export type CircuitProfile = {
  name: string; season: number; round: number; eventName: string;
  published?: string; ratingPublished?: string; updatedAt?: string; stale?: boolean;
  compounds: string[]; ratings: { label: string; value: number }[];
  team?: { name: string; wins: number }; driver?: { name: string; wins: number };
  opened?: number; firstRace?: number; historyThrough?: number;
  lapRecord?: { time: string; driver: string; year: number } | null;
  pitLoss?: string; pressures?: { front: string; rear: string };
  sources: { title: string; href: string }[];
};
export type ProfileResponse = { status: 'ok' | 'stale' | 'unavailable'; season: number; round: number; profile: CircuitProfile | null };

export function matchingProfile(response: ProfileResponse, season: number, round: number, eventName: string): CircuitProfile | null {
  return (response.status === 'ok' || response.status === 'stale') && response.season === season && response.round === round && response.profile?.season === season && response.profile.round === round && response.profile.eventName === eventName ? response.profile : null;
}

export function ratingTone(value: number): 'low' | 'medium' | 'high' {
  return value <= 2 ? 'low' : value === 3 ? 'medium' : 'high';
}

export function profileDate(value?: string): string {
  const timestamp = value ? Date.parse(value) : NaN;
  return Number.isFinite(timestamp) ? new Date(timestamp).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }) : '';
}
