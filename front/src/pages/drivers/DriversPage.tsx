import { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { DriverPortrait } from '../../components/DriverPortrait';
import { YearSelect } from '../../components/YearSelect';
import { PageFeedback } from '../../components/PageFeedback';
import { apiRequest } from '../../helpers/api';
import { homeTeamIdentity } from '../index/team-identity';
import '../index/home-team-colors.css';
import '../../assets/entrant-highlight.css';
import './drivers.css';

const currentRealYear = new Date().getFullYear();
const numberFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 });

type Driver = {
  position: number;
  name: string;
  code: string;
  points: number | null;
  is_favorite?: boolean;
  number?: string;
  constructorId?: string;
  constructorName?: string;
  driverId?: string;
  imageUrl?: string;
};
type DriversResponse = { round?: number | null; drivers?: Driver[] };
type RaceResultsResponse = { results?: { code?: string; points?: number }[] };

function driverLink(driver: Driver, year: number) {
  const params = new URLSearchParams({ code: driver.code, season: String(year) });
  if (driver.driverId) params.set('driverId', driver.driverId);
  return `/driver-details?${params}`;
}

function hasPoints(points: number | null): points is number {
  return points !== null && Number.isFinite(points);
}

function formatPoints(points: number | null) {
  return hasPoints(points) ? numberFormat.format(points) : '—';
}

function gapToLeader(driver: Driver, leader: Driver | null) {
  return leader && hasPoints(driver.points) && hasPoints(leader.points)
    ? Math.max(0, leader.points - driver.points) : null;
}

function DriversPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedYear = Number(searchParams.get('year'));
  const year = Number.isInteger(requestedYear) && requestedYear >= 1950 && requestedYear <= currentRealYear
    ? requestedYear : currentRealYear;
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [loadedYear, setLoadedYear] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [racePoints, setRacePoints] = useState<{ year: number; byCode: Record<string, number> } | null>(null);
  const standingsRequest = useRef(0);
  const cancelStandingsRequest = useCallback(() => { standingsRequest.current++; }, []);

  const loadDrivers = useCallback(async (season: number) => {
    const request = ++standingsRequest.current;
    setLoading(true);
    setError(null);
    try {
      const data = await apiRequest<DriversResponse>('/api/drivers', { season });
      if (request !== standingsRequest.current) return;
      setDrivers(data.drivers || []);
    } catch (e) {
      if (request !== standingsRequest.current) return;
      setDrivers([]);
      setError(e instanceof Error ? e.message : 'Не удалось загрузить зачёт');
    } finally {
      if (request === standingsRequest.current) {
        setLoadedYear(season);
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadDrivers(year);
    return cancelStandingsRequest;
  }, [year, loadDrivers, cancelStandingsRequest]);

  useEffect(() => {
    let cancelled = false;
    async function loadLastRacePoints() {
      try {
        const response = await apiRequest<RaceResultsResponse>('/api/race-results', { season: year });
        if (cancelled) return;
        const byCode: Record<string, number> = {};
        for (const row of response.results || []) {
          const code = (row.code || '').toUpperCase();
          if (code && row.points != null && Number.isFinite(Number(row.points))) byCode[code] = Number(row.points);
        }
        setRacePoints({ year, byCode });
      } catch {
        if (!cancelled) setRacePoints(null);
      }
    }
    void loadLastRacePoints();
    return () => { cancelled = true; };
  }, [year]);

  const updateYear = (value: number) => {
    const next = new URLSearchParams(searchParams);
    if (value === currentRealYear) next.delete('year'); else next.set('year', String(value));
    setSearchParams(next, { replace: true });
  };
  const isLoading = loading || loadedYear !== year;
  const hasData = !isLoading && !error && drivers.length > 0;
  const leader = hasData ? drivers[0] : null;
  const second = hasData ? drivers[1] : null;
  const contenders = hasData ? drivers.slice(0, 3) : [];
  const lastRacePoints = racePoints?.year === year ? racePoints.byCode : {};

  return (
    <div className="drivers-page">
      <header className={`drivers-heading${leader ? ' drivers-heading--with-leader' : ''}`}>
        <div className="drivers-heading-copy">
          <h1>Пилоты</h1>
          <p>Личный зачёт Формулы-1. От первой гонки до титула.</p>
          <div className="drivers-tools">
            <YearSelect value={year} onChange={updateYear} minYear={1950} maxYear={currentRealYear}
              showCurrentYearBtn={year !== currentRealYear} ariaLabel="Сезон личного зачёта" />
            <Link className="drivers-history" to="/history?kind=drivers">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M3 11a9 9 0 1 1 2.7 7.4M3 4v7h7m2-4v5l3 2" strokeLinecap="round" strokeLinejoin="round" /></svg>
              История сезонов
            </Link>
          </div>
        </div>
        {leader && <div className="drivers-contenders" data-count={contenders.length}>
          {contenders.map((driver, index) => {
            const isLeader = index === 0;
            const comparedDriver = isLeader ? second : driver;
            const gap = comparedDriver ? gapToLeader(comparedDriver, leader) : null;
            const caption = isLeader
              ? year < currentRealYear ? `Чемпион мира ${year}` : `Лидер сезона ${year}`
              : `${driver.position}-е место`;
            let gapLabel: string | null = null;
            if (gap !== null) {
              if (isLeader && second) gapLabel = gap === 0
                ? `Поровну очков с ${second.code || second.name}` : `+${numberFormat.format(gap)} очк. к ${second.code || second.name}`;
              else gapLabel = gap === 0 ? 'Наравне с лидером' : `−${numberFormat.format(gap)} очк. от лидера`;
            }
            return <Link key={driver.driverId || driver.code || driver.name}
              className={`drivers-leader entrant-highlight${index > 0 ? ' drivers-leader--secondary' : ''}`}
              to={driverLink(driver, year)} data-team={homeTeamIdentity(driver.constructorId || '', driver.constructorName || '')}>
              <div className="drivers-leader-copy">
                <h2>{driver.name}</h2>
                <p>{caption}</p>
                <strong>{formatPoints(driver.points)} <span>очк.</span></strong>
                {gapLabel && <small>{gapLabel}</small>}
              </div>
              <DriverPortrait key={`leader:${year}:${driver.code}`} code={driver.code} name={driver.name} season={year} src={driver.imageUrl} />
            </Link>;
          })}
        </div>}
      </header>

      <section className="drivers-classification" aria-labelledby="drivers-standings-title" aria-busy={isLoading}>
        <div className="drivers-list-heading">
          <h2 id="drivers-standings-title">Личный зачёт <span>{year}</span></h2>
          <Link className="drivers-team-link" to={`/constructors?year=${year}`}>Зачёт команд
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m9 5 7 7-7 7" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </Link>
        </div>
        {isLoading && <div className="drivers-state" role="status"><div className="spinner" aria-hidden="true" /><p>Загрузка пилотов…</p></div>}
        {!isLoading && error && <PageFeedback message={error} retry={() => void loadDrivers(year)} />}
        {!isLoading && !error && drivers.length === 0 && <div className="drivers-state" role="status">
          <h3>{year === currentRealYear ? 'Сезон ещё не начался' : 'Нет данных за этот сезон'}</h3>
          <p>{year === currentRealYear ? 'После первой гонки здесь появятся пилоты и очки.' : `Информация за ${year} год отсутствует. Выберите другой сезон.`}</p>
        </div>}
        {hasData && <>
          <div className="drivers-columns" aria-hidden="true"><span>Место</span><span>Пилот / команда</span><span className="drivers-columns-comparison"><span>Соотношение очков</span><span>Отставание</span></span><span>Последняя гонка</span><span>Очки</span></div>
          <ol className="drivers-list" aria-label={`Личный зачёт пилотов ${year}`}>
            {drivers.map(driver => {
              const earned = lastRacePoints[(driver.code || '').toUpperCase()];
              const gap = gapToLeader(driver, leader);
              const share = leader && hasPoints(leader.points) && leader.points > 0 && hasPoints(driver.points)
                ? Math.max(0, Math.min(100, driver.points / leader.points * 100)) : null;
              return <li key={driver.driverId || driver.code || driver.name}>
                <Link className="drivers-entry entrant-highlight" to={driverLink(driver, year)}
                  data-team={homeTeamIdentity(driver.constructorId || '', driver.constructorName || '')}>
                  <span className="drivers-position"><span className="drivers-sr">Место </span>{driver.position}</span>
                  <div className="drivers-identity">
                    <DriverPortrait key={`${year}:${driver.code}`} code={driver.code} name={driver.name} season={year} src={driver.imageUrl} />
                    <div className="drivers-name-team">
                      <span className="drivers-name">{driver.name}{driver.is_favorite && <svg className="drivers-favorite" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="Избранный пилот"><path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z" /></svg>}</span>
                      <span className="drivers-team">{driver.constructorName || 'Команда не указана'}</span>
                      <span className="drivers-number-code">{driver.number && <span>#{driver.number}</span>}{driver.code && <span>{driver.code}</span>}</span>
                    </div>
                  </div>
                  <span className="drivers-comparison">
                    <span className="drivers-points-track" aria-hidden="true">
                      {share !== null && <span className="drivers-points-fill" style={{ width: `${share}%` }} />}
                    </span>
                    <span className="drivers-gap">{driver === leader ? 'Лидер' : <>
                      <span className="drivers-sr">Отставание от лидера: </span>{gap === null ? '—' : gap === 0 ? '0' : `−${numberFormat.format(gap)}`}<span className="drivers-sr"> очков</span>
                    </>}</span>
                  </span>
                  <span className="drivers-race-points"><span className="drivers-sr">Последняя гонка: </span>{earned == null ? '—' : `+${numberFormat.format(earned)}`}<span className="drivers-race-label" aria-hidden="true">{earned == null ? 'Нет данных' : 'за гонку'}</span></span>
                  <span className="drivers-season-points"><strong>{formatPoints(driver.points)}</strong><span className="drivers-sr"> очков за сезон</span></span>
                </Link>
              </li>;
            })}
          </ol>
          <p className="drivers-footnote">Очки разных эпох начислялись по разным правилам. В истории сезонов можно сравнить итоговые места.</p>
        </>}
      </section>
    </div>
  );
}

export default DriversPage;
