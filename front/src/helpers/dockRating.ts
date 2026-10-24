export type DockRace = { round: number; event_name: string; date?: string; race_start_utc?: string; is_cancelled?: boolean };
/** Match voting's conservative completed-stage window, never rate a future start. */
export function latestDockRace(races: DockRace[], now: number): DockRace | undefined {
  const end = (race: DockRace) => race.race_start_utc && /(Z|[+-]\d\d:\d\d)$/i.test(race.race_start_utc)
    ? Date.parse(race.race_start_utc) + 3 * 3600000 : /^\d{4}-\d{2}-\d{2}$/.test(race.date || '') ? Date.parse(`${race.date}T00:00:00Z`) + 86400000 : NaN;
  return races.filter(race => !race.is_cancelled && Number.isInteger(race.round) && race.round > 0 && race.round <= 30 && end(race) <= now).sort((a, b) => end(b) - end(a))[0];
}
