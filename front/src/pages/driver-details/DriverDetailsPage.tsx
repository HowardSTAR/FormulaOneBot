import { EntrantBiography, type BiographyImage } from '../../components/EntrantBiography';
import { entrantValue } from '../../helpers/entrantPresentation';
import { DriverPortrait } from '../../components/DriverPortrait';
import { NationalityFlagBackdrop } from '../../components/NationalityFlagBackdrop';
import { EntrantLoading, EntrantNavigation, EntrantSections, EntrantMetric, EntrantRecord, EntrantPanels, EntrantStat as StatRow } from '../../components/EntrantDetails';
import { homeTeamIdentity } from '../index/team-identity';
import { DriverGuide } from "../../components/DriverGuide";
import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiRequest } from "../../helpers/api";
import { PageFeedback } from "../../components/PageFeedback";
import { getFlagUrlForNationality, nationalityLabel } from "../../constants/flags";

type SeasonStats = {
  position: number;
  points: number;
  grand_prix_races: number;
  grand_prix_points: number;
  grand_prix_wins: number;
  grand_prix_podiums: number;
  grand_prix_poles: number;
  grand_prix_top10s: number;
  fastest_laps: number;
  dnfs: number;
  sprint_races: number;
  sprint_points: number;
  sprint_wins: number;
  sprint_podiums: number;
  sprint_poles: number;
  sprint_top10s: number;
};

type CareerStats = {
  available?: boolean;
  grand_prix_entered: number;
  career_points: number;
  highest_race_finish: { position: number | string; count: number };
  podiums: number;
  highest_grid: { position: number | string; count: number };
  pole_positions: number;
  world_championships: number;
  dnfs: number;
};

type DriverDetailsResponse = {
  driverId: string;
  code: string;
  givenName: string;
  familyName: string;
  permanentNumber: string;
  dateOfBirth: string;
  nationality: string;
  url: string;
  bio: string;
  biography_source_url?: string;
  biography_image?: BiographyImage | null;
  headshot_url: string;
  season: number;
  season_stats: SeasonStats;
  career_stats: CareerStats;
};
type DriversListItem = {
  code?: string;
  driverId?: string;
  constructorName?: string;
  constructorId?: string;
};
type DriversListResponse = { drivers?: DriversListItem[] };

function DriverDetailsPage() {
  const [searchParams] = useSearchParams();
  const code = searchParams.get("code");
  const driverId = searchParams.get("driverId");
  const seasonParam = searchParams.get("season");
  const season = seasonParam ? parseInt(seasonParam, 10) : new Date().getFullYear();
  const standingsPath = `/drivers?year=${season}`;

  const [data, setData] = useState<DriverDetailsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const tab = searchParams.get("tab") === "bio" ? "bio" : "stats";
  const [team, setTeam] = useState<DriversListItem | null>(null);

  useEffect(() => {
    const id = code || driverId;
    if (!id) {
      setError("Не указан пилот");
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true); setError(null);
    async function load() {
      try {
        const params: Record<string, string | number> = { season };
        if (code) params.code = code;
        if (driverId) params.driverId = driverId;
        const [res, driversRes] = await Promise.all([
          apiRequest<DriverDetailsResponse>("/api/driver-details", params),
          apiRequest<DriversListResponse>("/api/drivers", { season }).catch(() => ({ drivers: [] })),
        ]);
        if (!cancelled) {
          setData(res);
          const match = (driversRes.drivers || []).find(
            (d) =>
              (res.code && d.code === res.code) ||
              (res.driverId && d.driverId && d.driverId === res.driverId) ||
              (code && d.code === code)
          );
          setTeam(match || null);
        }
      } catch (e) {
        if (!cancelled) {
          console.error(e);
          setError("Ошибка загрузки карточки пилота");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [code, driverId, season, attempt]);

  const navigation = <EntrantNavigation to={standingsPath} label={`Зачёт пилотов · ${season}`} />;
  if (error || (!code && !driverId)) {
    return <div className="entrant-details">{navigation}<PageFeedback message={error || "Не указан пилот"} retry={code || driverId ? () => setAttempt(v => v + 1) : undefined} parent={{ to: standingsPath, label: "Личный зачёт" }} /></div>;
  }
  if (loading || !data) {
    return <div className="entrant-details">{navigation}<EntrantLoading label="Загрузка карточки пилота" /></div>;
  }

  const fullName = `${data.givenName} ${data.familyName}`;
  const nationalityFlagUrl = getFlagUrlForNationality(data.nationality);
  const ss = data.season_stats;
  const cs = data.career_stats;
  const careerValue = (value: string | number) => cs.available === false ? "Нет данных" : value;
  const teamPath = team?.constructorName ? `/constructor-details?${new URLSearchParams({ constructorId: team.constructorId || team.constructorName, season: String(season) })}` : null;

  return <article className="entrant-details entrant-details--driver" data-team={homeTeamIdentity(team?.constructorId || '', team?.constructorName || '')}>
    {navigation}
    <header className="entrant-hero">
      <NationalityFlagBackdrop nationality={data.nationality} />
      <div className="entrant-hero-copy">
        <h1><span>{data.givenName}</span><strong>{data.familyName}</strong></h1>
        {teamPath && <Link className="entrant-team-link" to={teamPath}>{team?.constructorName}<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="m9 5 7 7-7 7" /></svg></Link>}
        <div className="entrant-identity">
          {data.permanentNumber && <span>№ {data.permanentNumber}</span>}
          {data.code && <span translate="no">{data.code}</span>}
          {data.nationality && <span>{nationalityFlagUrl && <img src={nationalityFlagUrl} width="22" height="15" alt="" onError={event => { event.currentTarget.style.visibility = 'hidden'; }} />}{nationalityLabel(data.nationality)}</span>}
        </div>
        <p className="entrant-season-label">Сезон {data.season}</p>
      </div>
      {data.permanentNumber && <span className="entrant-racing-number" aria-hidden="true">{data.permanentNumber}</span>}
      <div className="entrant-hero-media" aria-hidden="true">
        <DriverPortrait key={`${data.driverId}-${season}`} code={data.code} name={fullName} season={season} src={data.headshot_url} />
      </div>
    </header>
    <dl className="entrant-season-summary" aria-label={`Сезон ${data.season}`}>
      <StatRow label="Место в зачёте" value={ss.position || '—'} />
      <StatRow label="Очки сезона" value={ss.points} />
      <StatRow label="Победы в Гран-при" value={ss.grand_prix_wins} />
    </dl>
    <EntrantSections />
    <EntrantPanels key={`${data.driverId}-${season}`}>{tab === 'stats' ? <div className="entrant-statistics">
      <section className="entrant-stat-section" aria-labelledby="entrant-season-title">
        <div className="entrant-stat-heading"><h2 id="entrant-season-title">Сезон {data.season}</h2><span>{entrantValue(ss.grand_prix_races)} Гран-при</span></div>
        <dl className="entrant-highlights">
          <EntrantMetric label="Победы" icon="win" value={ss.grand_prix_wins} total={ss.grand_prix_races} />
          <EntrantMetric label="Подиумы" icon="podium" tone="gold" value={ss.grand_prix_podiums} total={ss.grand_prix_races} />
          <EntrantMetric label="Топ-10" icon="finish" tone="blue" value={ss.grand_prix_top10s} total={ss.grand_prix_races} />
        </dl>
        <dl>
          <StatRow label="Очки в Гран-при" value={ss.grand_prix_points} />
          <StatRow label="Поулы" value={ss.grand_prix_poles} />
          <StatRow label="Быстрые круги" value={ss.fastest_laps} />
          <StatRow label="Сходы" value={ss.dnfs} />
        </dl>
        {ss.sprint_races > 0 && <details className="entrant-sprints"><summary>Спринты <span>{entrantValue(ss.sprint_points)} очк.</span></summary><dl>
          <StatRow label="Спринты" value={ss.sprint_races} />
          <StatRow label="Очки в спринтах" value={ss.sprint_points} />
          <StatRow label="Победы" value={ss.sprint_wins} />
          <StatRow label="Подиумы" value={ss.sprint_podiums} />
          <StatRow label="Поулы" value={ss.sprint_poles} />
          <StatRow label="Финиши в топ-10" value={ss.sprint_top10s} />
        </dl></details>}
      </section>
      <section className="entrant-stat-section" aria-labelledby="entrant-career-title">
        <div className="entrant-stat-heading"><h2 id="entrant-career-title">Карьера</h2></div>
        <dl className="entrant-highlights">
          <EntrantMetric label="Титулы" icon="title" tone="gold" value={careerValue(cs.world_championships)} />
          <EntrantMetric label="Подиумы" icon="podium" value={careerValue(cs.podiums)} />
          <EntrantMetric label="Поулы" icon="grid" tone="blue" value={careerValue(cs.pole_positions)} />
        </dl>
        <dl className="entrant-records">
          <EntrantRecord label="Лучший финиш" record={cs.highest_race_finish} available={cs.available !== false} />
          <EntrantRecord label="Лучшая позиция на старте" record={cs.highest_grid} available={cs.available !== false} />
        </dl>
        <dl>
          <StatRow label="Гран-при за карьеру" value={careerValue(cs.grand_prix_entered)} />
          <StatRow label="Очки в Гран-при" value={careerValue(cs.career_points)} />
          <StatRow label="Сходы" value={careerValue(cs.dnfs)} />
        </dl>
      </section>
    </div> : <EntrantBiography key={`${data.driverId}-${season}-${data.biography_image?.url || ''}`} title="Биография" text={data.bio} source={data.biography_source_url || data.url} image={data.biography_image} facts={<>
      <StatRow label="Гражданство" value={nationalityLabel(data.nationality)} />
      <StatRow label="Дата рождения" value={data.dateOfBirth ? new Date(data.dateOfBirth + 'T12:00:00').toLocaleDateString('ru-RU') : '—'} />
    </>} />}</EntrantPanels>
    <DriverGuide key={data.driverId} driverId={data.driverId} />
  </article>;
}

export default DriverDetailsPage;
