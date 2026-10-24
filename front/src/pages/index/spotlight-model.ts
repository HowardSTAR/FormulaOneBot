export type SpotlightEntry = {
  name: string; points?: number | null; position?: number | null; code?: string;
  number?: string; driverId?: string; constructorId?: string; constructorName?: string;
  imageUrl?: string;
};
export type HomeFavorites = { drivers: string[]; teams: string[] };
export type SpotlightSlot = { kind: 'driver' | 'team'; entry: SpotlightEntry | null; favorite: boolean; unavailable: boolean };

// Saved selections keep their order and never silently become someone else.
export function spotlightSlots(drivers: SpotlightEntry[], teams: SpotlightEntry[], favorites: HomeFavorites): SpotlightSlot[] {
  const driverSlots = [0, 1].map(index => {
    const saved = favorites.drivers[index];
    const entry = saved ? drivers.find(row => row.code?.toUpperCase() === saved.toUpperCase())
      : favorites.drivers.length ? undefined : drivers[index];
    return { kind: 'driver' as const, entry: entry || null, favorite: Boolean(saved), unavailable: Boolean(saved && !entry) };
  });
  const savedTeam = favorites.teams[0];
  const team = savedTeam ? teams.find(row => [row.name, row.constructorId].some(value => value?.toLowerCase() === savedTeam.toLowerCase())) : teams[0];
  return [...driverSlots, { kind: 'team', entry: team || null, favorite: Boolean(savedTeam), unavailable: Boolean(savedTeam && !team) }];
}
