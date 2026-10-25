// Fictional calendar data for the Vite design fixture only.
import { raceSessions, type CalendarRace } from '../../src/helpers/seasonCalendar.ts';
export function calendarPreviewRaces(year: number): CalendarRace[] {
  const venues = [
    [17, 'Azerbaijan Grand Prix', 'Баку', 'Азербайджан', '09-27'],
    [18, 'Singapore Grand Prix', 'Сингапур', 'Сингапур', '10-11'],
    [19, 'United States Grand Prix', 'Остин', 'США', '10-25'],
    [20, 'Mexico City Grand Prix', 'Мехико', 'Мексика', '11-01'],
    [21, 'São Paulo Grand Prix', 'Сан-Паулу', 'Бразилия', '11-08'],
    [22, 'Las Vegas Grand Prix', 'Лас-Вегас', 'США', '11-22'],
    [23, 'Qatar Grand Prix', 'Лусаил', 'Катар', '11-29'],
    [24, 'Abu Dhabi Grand Prix', 'Абу-Даби', 'ОАЭ', '12-06'],
    [25, 'A deliberately long cancelled Grand Prix name for narrow screens', 'Длинное название места проведения', '', '12-13'],
  ] as const;
  return venues.map(([round, event_name, location, country, day]) => {
    const date = `${year}-${day}`;
    const race = new Date(`${date}T20:00:00Z`).getTime();
    const iso = (hours: number) => new Date(race - hours * 3_600_000).toISOString();
    return { round, event_name, location, country, date, is_cancelled: round === 25,
      race_start_utc: round === 24 ? null : iso(0), quali_start_utc: round === 24 ? null : iso(24),
      practice1_start_utc: iso(51), ...(round === 19 ? { sprint_start_utc: iso(29), sprint_quali_start_utc: iso(47) } : { practice2_start_utc: iso(47), practice3_start_utc: iso(27) }) };
  });
}

// The calendar, stage overview and results must share the same event identity.
export function calendarPreviewStage(season: number, round: number) {
  const race = calendarPreviewRaces(season).find(race => race.round === round);
  if (!race) return null;
  return { ...race, season, sessions: raceSessions(race).map(session => ({ name: session.label, utc_iso: session.iso || undefined })) };
}
