import { EntrantBiography, type BiographyImage } from '../../components/EntrantBiography';
import { carImageUrl } from '../../helpers/f1Assets';
import { DriverPortrait } from '../../components/DriverPortrait';
import { TeamLogo } from '../../components/TeamLogo';
import { NationalityFlagBackdrop } from '../../components/NationalityFlagBackdrop';
import { EntrantLoading, EntrantNavigation, EntrantSections, EntrantMetric, EntrantRecord, EntrantPanels, EntrantStat as StatRow } from '../../components/EntrantDetails';
import { homeTeamIdentity } from '../index/team-identity';
import { spotlightTeamMedia } from '../index/spotlight-team-media';
import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiRequest } from "../../helpers/api";
import { nationalityLabel } from "../../constants/flags";
import { PageFeedback } from "../../components/PageFeedback";

type SeasonStats = {
  position: number | string;
  points: number;
  points_source?: string;
  grand_prix_points?: number;
  standings_round?: number;
  grand_prix_entries?: number;
  grand_prix_points_finishes?: number;
  grand_prix_unclassified?: number | null;
  highest_race_finish?: { position: number | string; count: number };
  highest_grid?: { position: number | string; count: number };
  grand_prix_races: number;
  grand_prix_wins: number;
  grand_prix_podiums: number;
  grand_prix_poles: number;
};

type CareerStats = {
  available?: boolean;
  grand_prix_entered: number;
  grand_prix_events?: number | null;
  career_points: number;
  highest_race_finish: { position: number | string; count: number };
  podiums: number;
  pole_positions: number;
  world_championships: number;
};

type SeasonDriver = {
  driverId: string;
  code: string;
  givenName: string;
  familyName: string;
  permanentNumber: string;
  nationality: string;
  headshot_url?: string;
};

type TeamPrincipal = {
  id: string;
  name: string;
  role: string;
  team_name: string;
  photo_url: string;
  bio: string;
  url: string;
};

type ConstructorDetailsResponse = {
  constructorId: string;
  name: string;
  nationality: string;
  url: string;
  bio: string;
  biography_source_url?: string;
  biography_image?: BiographyImage | null;
  drivers?: SeasonDriver[];
  principal?: TeamPrincipal | null;
  season: number;
  season_stats: SeasonStats;
  career_stats: CareerStats;
};

function TeamCar({ id, name, season }: { id: string; name: string; season: number }) {
  const [index, setIndex] = useState(0);
  const sources = [...spotlightTeamMedia(id, name, season).car, carImageUrl(name, season)];
  return index < sources.length ? <img className="entrant-team-car" src={sources[index]} alt="" width="1400" height="400" decoding="async" onError={() => setIndex(value => value + 1)} /> : null;
}

function ConstructorDetailsPage() {
  const [searchParams] = useSearchParams();
  const constructorId = searchParams.get("constructorId");
  const seasonParam = searchParams.get("season");
  const season = seasonParam ? parseInt(seasonParam, 10) : new Date().getFullYear();

  const [data, setData] = useState<ConstructorDetailsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const tab = searchParams.get("tab") === "bio" ? "bio" : "stats";
  const [principalImageAvailable, setPrincipalImageAvailable] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!constructorId) {
      setError("Не указана команда");
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    async function load() {
      try {
        const res = await apiRequest<ConstructorDetailsResponse>("/api/constructor-details", {
          constructorId,
          season,
        });
        if (!cancelled) {
          setData(res);
          setPrincipalImageAvailable(Boolean(res.principal?.photo_url));
        }
      } catch (e) {
        if (!cancelled) {
          console.error(e);
          setError("Ошибка загрузки карточки команды");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [constructorId, season, attempt]);

  const standingsPath = `/constructors?year=${season}`;
  const navigation = <EntrantNavigation to={standingsPath} label={`Зачёт команд · ${season}`} />;
  if (error || !constructorId) {
    return <div className="entrant-details">{navigation}<PageFeedback message={error || "Не указана команда"} retry={constructorId ? () => setAttempt(v => v + 1) : undefined} parent={{ to: standingsPath, label: "Кубок конструкторов" }} /></div>;
  }
  if (loading || !data) {
    return <div className="entrant-details">{navigation}<EntrantLoading label="Загрузка карточки команды" /></div>;
  }

  const ss = data.season_stats;
  const cs = data.career_stats;
  const careerValue = (value: string | number) => cs.available === false ? "Нет данных" : value;
  const drivers = data.drivers || [];
  const principal = data.principal?.photo_url ? data.principal : null;
  const principalPath = `/team-principal?constructorId=${encodeURIComponent(data.constructorId)}&season=${season}`;

  return <article className="entrant-details entrant-details--team" data-team={homeTeamIdentity(data.constructorId, data.name)}>
    {navigation}
    <header className="entrant-hero">
      <NationalityFlagBackdrop nationality={data.nationality} />
      <div className="entrant-hero-copy">
        <h1>{data.name}</h1>
        <div className="entrant-identity"><span>Сезон {data.season}</span>{data.nationality && <span>{nationalityLabel(data.nationality)}</span>}</div>
        {drivers.length > 0 && <nav className="entrant-hero-lineup" aria-label={`Пилоты команды в сезоне ${data.season}`}>
          {drivers.map(driver => <Link key={driver.driverId || driver.code} to={`/driver-details?${new URLSearchParams({ ...(driver.code ? { code: driver.code } : { driverId: driver.driverId }), season: String(season) })}`}>
            <DriverPortrait key={`${driver.driverId}-${season}`} code={driver.code} name={`${driver.givenName} ${driver.familyName}`} season={season} src={driver.headshot_url} />
            <span className="entrant-lineup-number">{driver.permanentNumber || '—'}</span>
            <span className="entrant-lineup-name">{driver.givenName} <strong>{driver.familyName}</strong></span>
            <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m9 5 7 7-7 7" /></svg>
          </Link>)}
        </nav>}
      </div>
      <div className="entrant-team-emblem" aria-hidden="true"><TeamLogo key={`${data.constructorId}-${season}`} id={data.constructorId} name={data.name} season={season} size={220} /></div>
      <div className="entrant-hero-media" aria-hidden="true"><TeamCar key={`${data.constructorId}-${season}`} id={data.constructorId} name={data.name} season={season} /></div>
    </header>
    <dl className="entrant-season-summary" aria-label={`Сезон ${data.season}`}>
      <StatRow label="Место в зачёте" value={ss.position ?? '—'} />
      <StatRow label={ss.points_source === 'grand_prix' ? 'Очки Гран-при' : 'Очки общего зачёта'} value={ss.points} />
      <StatRow label="Победы в Гран-при" value={ss.grand_prix_wins} />
    </dl>
    {ss.points_source === 'grand_prix' && <p className="entrant-data-note">Зачёт сезона недоступен. Показаны очки Гран-при.</p>}
    <EntrantSections />
    <EntrantPanels key={`${data.constructorId}-${season}`}>{tab === 'stats' ? <div className="entrant-statistics">
      <section className="entrant-stat-section" aria-labelledby="entrant-season-title">
        <div className="entrant-stat-heading"><h2 id="entrant-season-title">Сезон {data.season}</h2><span>{ss.grand_prix_races} Гран-при</span></div>
        <dl className="entrant-highlights">
          <EntrantMetric label="Победы" icon="win" value={ss.grand_prix_wins} />
          <EntrantMetric label="Подиумы" icon="podium" tone="gold" value={ss.grand_prix_podiums} />
          <EntrantMetric label="Поулы" icon="grid" tone="blue" value={ss.grand_prix_poles} />
        </dl>
        {(ss.highest_race_finish || ss.highest_grid) && <dl className="entrant-records">
          {ss.highest_race_finish && <EntrantRecord label="Лучший финиш" record={ss.highest_race_finish} />}
          {ss.highest_grid && <EntrantRecord label="Лучший старт" record={ss.highest_grid} />}
        </dl>}
        <dl>
          {ss.grand_prix_points != null && <StatRow label="Очки в Гран-при" value={ss.grand_prix_points} />}
          {ss.grand_prix_entries !== undefined && <StatRow label="Выступления машин" value={ss.grand_prix_entries} />}
          {ss.grand_prix_points_finishes !== undefined && <StatRow label="Финиши с очками" value={ss.grand_prix_points_finishes} />}
          {ss.grand_prix_unclassified !== undefined && <StatRow label="Без классификации" value={ss.grand_prix_unclassified} />}
        </dl>
        {ss.grand_prix_points != null && ss.points_source !== 'grand_prix' && <p className="entrant-data-note">Общий зачёт также учитывает спринты и возможные корректировки.</p>}
        {ss.standings_round != null && <p className="entrant-data-note">После этапа {ss.standings_round}</p>}
      </section>
      <section className="entrant-stat-section" aria-labelledby="entrant-career-title">
        <div className="entrant-stat-heading"><h2 id="entrant-career-title">Карьера</h2></div>
        <dl className="entrant-highlights">
          <EntrantMetric label="Титулы" icon="title" tone="gold" value={careerValue(cs.world_championships)} />
          <EntrantMetric label="Подиумы" icon="podium" value={careerValue(cs.podiums)} />
          <EntrantMetric label="Поулы" icon="grid" tone="blue" value={careerValue(cs.pole_positions)} />
        </dl>
        <dl className="entrant-records"><EntrantRecord label="Лучший финиш" record={cs.highest_race_finish} available={cs.available !== false} /></dl>
        <dl>
          <StatRow label="Выступления машин в Гран-при" value={careerValue(cs.grand_prix_entered)} />
          {cs.grand_prix_events != null && <StatRow label="Этапы команды" value={careerValue(cs.grand_prix_events)} />}
          <StatRow label="Очки в Гран-при" value={careerValue(Math.round(cs.career_points))} />
        </dl>
      </section>
    </div> : <EntrantBiography key={`${data.constructorId}-${season}-${data.biography_image?.url || ''}`} title="История команды" text={data.bio} source={data.biography_source_url || data.url} image={data.biography_image} />}</EntrantPanels>
    <section className="entrant-roster" aria-labelledby="entrant-roster-title">
      <h2 id="entrant-roster-title">Состав команды <span>{data.season}</span></h2>
      {drivers.length > 0 || principal ? <div className="entrant-roster-grid">
        {drivers.map(driver => <Link className="entrant-roster-entry" key={driver.driverId} to={`/driver-details?${new URLSearchParams({ code: driver.code, driverId: driver.driverId, season: String(season) })}`}>
          <DriverPortrait code={driver.code} name={`${driver.givenName} ${driver.familyName}`} season={season} src={driver.headshot_url} />
          <div><span className="entrant-roster-name">{driver.givenName}<strong>{driver.familyName}</strong></span><span className="entrant-roster-role">{nationalityLabel(driver.nationality) || 'Пилот'}</span></div>
          {driver.permanentNumber && <span className="entrant-roster-number">№ {driver.permanentNumber}</span>}
        </Link>)}
        {principal && <Link className="entrant-roster-entry entrant-roster-entry--principal" to={principalPath}>
          <span className="entrant-principal-photo">{principalImageAvailable ? <img src={principal.photo_url} alt="" width="160" height="180" loading="lazy" onError={() => setPrincipalImageAvailable(false)} /> : <svg aria-hidden="true" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="12" cy="8" r="4" /><path d="M4 22v-2a8 8 0 0 1 16 0v2" /></svg>}</span>
          <div><strong className="entrant-roster-name">{principal.name}</strong><span className="entrant-roster-role">{principal.role}</span></div>
        </Link>}
      </div> : <p className="entrant-data-note">Состав команды за этот сезон пока недоступен.</p>}
    </section>
  </article>;
}

export default ConstructorDetailsPage;
