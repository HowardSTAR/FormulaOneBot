import { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { YearSelect } from '../../components/YearSelect';
import { PageFeedback } from '../../components/PageFeedback';
import { apiRequest } from '../../helpers/api';
import { teamLogoBounds as logoBounds } from '../../helpers/teamLogoBounds';
import { teamLogoUrl, carImageUrl } from '../../helpers/f1Assets';
import { homeTeamIdentity } from '../index/team-identity';
import { spotlightTeamMedia } from '../index/spotlight-team-media';
import '../index/home-team-colors.css';
import '../../assets/entrant-highlight.css';
import './constructors.css';

const currentRealYear = new Date().getFullYear();
const minConstructorYear = 1958;
const numberFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 });
type Constructor = { position: number; name: string; points: number; is_favorite?: boolean; constructorId?: string };
type ConstructorsResponse = { round?: number | null; constructors?: Constructor[] };
function teamLink(team: Constructor, season: number) {
  return `/constructor-details?${new URLSearchParams({ constructorId: team.constructorId || team.name, season: String(season) })}`;
}

function TeamImage({ sources, className, fallback, width = 640, height = 180, bounds }: { sources: string[]; className: string; fallback?: string; width?: number; height?: number; bounds?: readonly [number, number, number, number] }) {
  const [index, setIndex] = useState(0);
  if (index >= sources.length) return fallback ? <span className="constructors-monogram" aria-hidden="true">{fallback}</span> : null;
  const image = <img src={sources[index]} className={className} alt="" width={width} height={height} decoding="async" onError={() => setIndex(value => value + 1)} />;
  if (index !== 0 || !bounds) return image;
  const [left, top, right, bottom] = bounds;
  const markWidth = right - left, markHeight = bottom - top;
  const round = Math.abs(markWidth / markHeight - 1) < .1;
  const scale = Math.min((round ? 28 : 34) / markWidth, (round ? 28 : 30) / markHeight);
  return <span className="constructors-logo-art" style={{ width: `${markWidth * scale / 16}rem`, height: `${markHeight * scale / 16}rem` }}>
    <span style={{ position: 'absolute', width: `${width / markWidth * 100}%`, height: `${height / markHeight * 100}%`, left: `${-left / markWidth * 100}%`, top: `${-top / markHeight * 100}%` }}>{image}</span>
  </span>;
}

function ConstructorsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedYear = Number(searchParams.get('year'));
  const year = Number.isInteger(requestedYear) && requestedYear >= minConstructorYear && requestedYear <= currentRealYear ? requestedYear : currentRealYear;
  const [teams, setTeams] = useState<Constructor[]>([]);
  const [loadedYear, setLoadedYear] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const standingsRequest = useRef(0);
  const cancelStandingsRequest = useCallback(() => { standingsRequest.current++; }, []);

  const loadTeams = useCallback(async (season: number) => {
    const request = ++standingsRequest.current;
    setLoading(true);
    setError(null);
    try {
      const data = await apiRequest<ConstructorsResponse>('/api/constructors', { season });
      if (request !== standingsRequest.current) return;
      setTeams(data.constructors || []);
    } catch (e) {
      if (request !== standingsRequest.current) return;
      setTeams([]);
      setError(e instanceof Error ? e.message : 'Не удалось загрузить зачёт');
    } finally {
      if (request === standingsRequest.current) {
        setLoadedYear(season);
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadTeams(year);
    return cancelStandingsRequest;
  }, [year, loadTeams, cancelStandingsRequest]);

  const updateYear = (value: number) => {
    const next = new URLSearchParams(searchParams);
    if (value === currentRealYear) next.delete('year'); else next.set('year', String(value));
    setSearchParams(next, { replace: true });
  };
  const isLoading = loading || loadedYear !== year;
  const hasData = !isLoading && !error && teams.length > 0;
  const leader = hasData ? teams[0] : null;
  const second = hasData ? teams[1] : null;
  const gap = leader && second ? Math.max(0, leader.points - second.points) : null;
  const leaderMedia = leader ? spotlightTeamMedia(leader.constructorId || '', leader.name, year) : null;

  return <div className="constructors-page">
    <header className={`constructors-heading${leader ? ' constructors-heading--with-leader' : ''}`}>
      <div className="constructors-heading-copy">
        <h1>Команды</h1>
        <p>Кубок конструкторов Формулы-1. Два пилота — один результат.</p>
        <div className="constructors-tools">
          <YearSelect value={year} onChange={updateYear} minYear={minConstructorYear} maxYear={currentRealYear}
            showCurrentYearBtn={year !== currentRealYear} ariaLabel="Сезон Кубка конструкторов" />
          <Link className="constructors-history" to="/history?kind=constructors" aria-label="Сравнить команды по сезонам" title="Сравнить команды по сезонам">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M4 4v16h16M7 14l4-5 4 3 5-6" strokeLinecap="round" strokeLinejoin="round" /></svg>
            <span>Сравнить команды по сезонам</span>
          </Link>
        </div>
      </div>
      {leader && <Link className="constructors-leader entrant-highlight" to={teamLink(leader, year)} data-team={homeTeamIdentity(leader.constructorId || '', leader.name)}>
        <div className="constructors-leader-copy">
          <h2>{leader.name}</h2>
          <p>Лидер зачёта {year}</p>
          <strong>{numberFormat.format(leader.points)} <span>очк.</span></strong>
          {second && gap !== null && <small>{gap === 0 ? `Поровну очков с ${second.name}` : `+${numberFormat.format(gap)} очк. к ${second.name}`}</small>}
        </div>
        <div className="constructors-leader-car" aria-hidden="true">
          <TeamImage key={`${year}:${leader.name}`} className="constructors-car-image" sources={[...(leaderMedia?.car || []), carImageUrl(leader.name, year)]} />
        </div>
      </Link>}
    </header>
    <section className="constructors-classification" aria-labelledby="constructors-standings-title" aria-busy={isLoading}>
      <div className="constructors-list-heading">
        <h2 id="constructors-standings-title">Кубок конструкторов <span>{year}</span></h2>
        <Link className="constructors-driver-link" to={`/drivers?year=${year}`}>Зачёт пилотов
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m9 5 7 7-7 7" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </Link>
      </div>
      {isLoading && <div className="constructors-state" role="status"><div className="spinner" aria-hidden="true" /><p>Загрузка команд…</p></div>}
      {!isLoading && error && <PageFeedback message={error} retry={() => void loadTeams(year)} />}
      {!isLoading && !error && teams.length === 0 && <div className="constructors-state" role="status">
        <h3>{year === currentRealYear ? 'Сезон ещё не начался' : 'Нет данных за этот сезон'}</h3>
        <p>{year === currentRealYear ? 'После первой гонки здесь появятся команды и очки.' : `Информация за ${year} год отсутствует. Выберите другой сезон.`}</p>
      </div>}
      {hasData && <>
        <div className="constructors-columns" aria-hidden="true"><span>Место</span><span>Команда</span><span>От лидера</span><span>Очки</span></div>
        <ol className="constructors-list" aria-label={`Кубок конструкторов ${year}`}>
          {teams.map(team => {
            const media = spotlightTeamMedia(team.constructorId || '', team.name, year);
            const pointsGap = Math.max(0, (leader?.points ?? 0) - team.points);
            return <li key={team.constructorId || team.name}>
              <Link className="constructors-entry entrant-highlight" to={teamLink(team, year)} data-team={homeTeamIdentity(team.constructorId || '', team.name)}>
                <span className="constructors-position"><span className="constructors-sr">Место </span>{team.position}</span>
                <div className="constructors-identity">
                  <span className="constructors-logo" aria-hidden="true"><TeamImage key={`${year}:${team.name}`} sources={[...media.logo, teamLogoUrl(team.constructorId || '', team.name, year)]} className="constructors-logo-image" fallback={team.name.slice(0, 3)} width={480} height={480} bounds={year === 2026 && media.logo.length ? logoBounds[homeTeamIdentity(team.constructorId || '', team.name)] : undefined} /></span>
                  <span className="constructors-name">{team.name}{team.is_favorite && <svg className="constructors-favorite" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="Избранная команда"><path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z" /></svg>}</span>
                </div>
                <div className="constructors-score">
                  <span className="constructors-points"><strong>{numberFormat.format(team.points)}</strong><span className="constructors-sr"> очков за сезон</span></span>
                  <span className="constructors-gap">{team === leader ? 'Лидер' : <><span className="constructors-sr">От лидера: </span>−{numberFormat.format(pointsGap)}<span className="constructors-gap-label" aria-hidden="true"> от лидера</span></>}</span>
                </div>
              </Link>
            </li>;
          })}
        </ol>
      </>}
    </section>
  </div>;
}
export default ConstructorsPage;
