import { YearSelect } from './YearSelect';
export function ResultsSeasonFilter({ season, onChange, minYear = 1950 }: {season: number; onChange: (year: number) => void; minYear?: number}) {
  return <div className="ui-results-year"><span>Сезон результатов</span><YearSelect ariaLabel="Сезон результатов" value={season} onChange={onChange} minYear={minYear} maxYear={new Date().getFullYear()} /></div>;
}
