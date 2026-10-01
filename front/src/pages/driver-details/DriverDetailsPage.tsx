import { GlossaryText } from "../../components/GlossaryText";
import { DriverGuide } from "../../components/DriverGuide";
import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BackButton } from "../../components/BackButton";
import { apiAssetUrl, apiRequest } from "../../helpers/api";
import { PageFeedback } from "../../components/PageFeedback";
import { cleanBiography } from "../../helpers/presentation";
import { getFlagUrlForNationality, nationalityLabel } from "../../constants/flags";

function pilotPortraitUrl(code: string, fullName: string, season: number): string {
  return apiAssetUrl("/api/pilot-portrait", {
    season,
    code,
    name: fullName,
  });
}

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
  headshot_url: string;
  season: number;
  season_stats: SeasonStats;
  career_stats: CareerStats;
};
type DriversListItem = {
  code?: string;
  driverId?: string;
  constructorName?: string;
};
type DriversListResponse = { drivers?: DriversListItem[] };

function StatRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="driver-stat-row">
      <span className="driver-stat-label">{label}</span>
      <span className="driver-stat-value">{value}</span>
    </div>
  );
}

function DriverDetailsPage() {
  const [searchParams] = useSearchParams();
  const code = searchParams.get("code");
  const driverId = searchParams.get("driverId");
  const seasonParam = searchParams.get("season");
  const season = seasonParam ? parseInt(seasonParam, 10) : new Date().getFullYear();

  const [data, setData] = useState<DriverDetailsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"stats" | "bio">("stats");
  const [teamName, setTeamName] = useState<string>("Команда Формулы-1");

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
          if (match?.constructorName) setTeamName(match.constructorName);
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

  if (error || (!code && !driverId)) {
    return (
      <>
        <BackButton fallback="/drivers">← <span>Личный зачет</span></BackButton>
        <PageFeedback message={error || "Не указан пилот"} retry={() => setAttempt(v => v + 1)} parent={{to: "/drivers", label: "Личный зачёт"}} />
      </>
    );
  }

  if (loading || !data) {
    return (
      <>
        <BackButton fallback="/drivers">← <span>Личный зачет</span></BackButton>
        <div className="loading full-width">
          <div className="spinner" />
          <div>Загрузка карточки пилота...</div>
        </div>
      </>
    );
  }

  const fullName = `${data.givenName} ${data.familyName}`;
  const nationalityFlagUrl = getFlagUrlForNationality(data.nationality);
  const ss = data.season_stats;
  const cs = data.career_stats;
  const firstName = data.givenName.toUpperCase();
  const lastName = data.familyName.toUpperCase();
  const teamLabel =
    teamName === "Команда Формулы-1" && data.code === "ANT"
      ? "Mercedes-AMG Petronas F1 Team"
      : teamName;

  const formatHigh = (h: { position: number | string; count: number }) =>
    h.position === "-" ? "-" : `${h.position}${h.count > 1 ? ` (x${h.count})` : ""}`;

  return (
    <>
      <div className="driver-details-mobile">
        <nav className="ui-section-links" aria-label="Родительский раздел"><Link to={`/drivers?year=${season}`}>К зачёту пилотов · {season}</Link></nav>
        <BackButton fallback="/drivers">← <span>Личный зачет</span></BackButton>

        <div className="driver-card-header">
          <div className="driver-portrait-wrap">
            <img
              src={pilotPortraitUrl(data.code, fullName, season)}
              alt={fullName}
              className="driver-portrait"
              onError={(e) => {
                if (e.currentTarget.src !== window.location.origin + "/api/pilot-portrait") {
                  e.currentTarget.src = "/api/pilot-portrait";
                }
              }}
            />
          </div>
          <div className="driver-card-info">
            <h2 className="driver-card-name">{fullName}</h2>
            <div className="driver-card-meta">
              {data.permanentNumber && <span className="driver-number-badge">#{data.permanentNumber}</span>}
              <span className="driver-code-badge">{data.code}</span>
            </div>
            {data.nationality && (
              <div className="driver-nationality">
                {nationalityFlagUrl && (
                  <img
                    src={nationalityFlagUrl}
                    alt={data.nationality}
                    className="country-flag-svg"
                  />
                )}
                <span>{nationalityLabel(data.nationality)}</span>
              </div>
            )}
          </div>
        </div>

        <DriverGuide key={data.driverId} driverId={data.driverId} />
        <div className="driver-tabs">
          <button
            type="button"
            className={`driver-tab ${tab === "stats" ? "active" : ""}`}
            onClick={() => setTab("stats")}
          >
            Статистика
          </button>
          <button
            type="button"
            className={`driver-tab ${tab === "bio" ? "active" : ""}`}
            onClick={() => setTab("bio")}
          >
            Биография
          </button>
        </div>

        {tab === "stats" && (
          <div className="driver-stats-grid">
            <div className="driver-stats-block">
              <h3 className="driver-stats-title">{data.season} СЕЗОН</h3>
              <StatRow label="Позиция в сезоне" value={ss.position || "-"} />
              <StatRow label="Очки сезона" value={ss.points} />
              <StatRow label="Гран-при (гонок)" value={ss.grand_prix_races} />
              <StatRow label="Очки в ГП" value={ss.grand_prix_points} />
              <StatRow label="Победы" value={ss.grand_prix_wins} />
              <StatRow label="Подиумы" value={ss.grand_prix_podiums} />
              <StatRow label="Поулы" value={ss.grand_prix_poles} />
              <StatRow label="Топ-10" value={ss.grand_prix_top10s} />
              <StatRow label="Быстрые круги" value={ss.fastest_laps} />
              <StatRow label="Сходы" value={ss.dnfs} />
              {ss.sprint_races > 0 && (
                <>
                  <StatRow label="Спринты" value={ss.sprint_races} />
                  <StatRow label="Очки в спринтах" value={ss.sprint_points} />
                  <StatRow label="Победы в спринтах" value={ss.sprint_wins} />
                  <StatRow label="Подиумы в спринтах" value={ss.sprint_podiums} />
                  <StatRow label="Поулы в спринтах" value={ss.sprint_poles} />
                  <StatRow label="Топ-10 в спринтах" value={ss.sprint_top10s} />
                </>
              )}
            </div>
            <div className="driver-stats-block">
              <h3 className="driver-stats-title">КАРЬЕРА</h3>
              <StatRow label="Гран-при (всего)" value={cs.grand_prix_entered} />
              <StatRow label="Карьерные очки в ГП" value={cs.career_points} />
              <StatRow label="Лучший финиш" value={formatHigh(cs.highest_race_finish)} />
              <StatRow label="Подиумы" value={cs.podiums} />
              <StatRow label="Лучшая позиция на старте" value={formatHigh(cs.highest_grid)} />
              <StatRow label="Поулы" value={cs.pole_positions} />
              <StatRow label="Чемпионства" value={cs.world_championships} />
              <StatRow label="Сходы" value={cs.dnfs} />
            </div>
          </div>
        )}

        {tab === "bio" && (
          <div className="driver-bio-block">
            {data.bio ? (
              <p className="driver-bio-text"><GlossaryText>{cleanBiography(data.bio)}</GlossaryText></p>
            ) : (
              <p className="driver-bio-empty">Биография пока недоступна.</p>
            )}
            {data.url && (
              <a
                href={data.url}
                target="_blank"
                rel="noopener noreferrer"
                className="driver-bio-link"
              >
                Открыть в Wikipedia →
              </a>
            )}
          </div>
        )}
      </div>

      <section className="driver-profile-desktop">
        <nav className="ui-section-links" aria-label="Родительский раздел"><Link to={`/drivers?year=${season}`}>К зачёту пилотов · {season}</Link></nav>
        <header className="driver-profile-desktop-hero">
          <div className="driver-profile-desktop-photo">
            <img src={pilotPortraitUrl(data.code, fullName, season)} alt={fullName} />
          </div>
          <div className="driver-profile-desktop-overlay" />
          <div className="driver-profile-desktop-content">
            <div className="driver-profile-desktop-number">{data.permanentNumber || "--"}</div>
            <h1>
              <span>{firstName}</span>
              <em>{lastName}</em>
            </h1>
            <div className="driver-profile-desktop-team">
              <b>{data.code}</b>
              <span>{teamLabel}</span>
            </div>
          </div>
          <aside className="driver-profile-desktop-rank">
            <div><span>Позиция</span><strong>{ss.position ? `P${ss.position}` : '—'}</strong></div>
            <div><span>Очки</span><strong>{ss.points}</strong></div>
            <div><span>Победы</span><strong>{ss.grand_prix_wins}</strong></div>
          </aside>
        </header>

        <DriverGuide key={data.driverId} driverId={data.driverId} />
        <div className="driver-profile-desktop-grid">
          <section className="driver-profile-desktop-main">
            <h3 className="driver-profile-title">Аналитика выступлений</h3>
            <div className="driver-profile-season-cards">

              <article><span>Подиумы</span><strong>{ss.grand_prix_podiums}</strong><small>Гран-при</small></article>
              <article><span>Поулы</span><strong>{ss.grand_prix_poles}</strong><small>Квалификации</small></article>
              <article><span>Участий в ГП</span><strong>{ss.grand_prix_races}</strong><small>Сезон {season}</small></article>
            </div>
            <div className="driver-profile-career-grid">
              <article className="driver-profile-career-card">
                <h4>Итоги карьеры</h4>
                <div><span>Гран-при (всего)</span><b>{cs.grand_prix_entered}</b></div>
                <div><span>Очки в Гран-при</span><b>{cs.career_points}</b></div>
                <div><span>Лучший финиш</span><b>{formatHigh(cs.highest_race_finish)}</b></div>
              </article>
              <article className="driver-profile-accolades-card">
                <h4>Достижения</h4>
                <p>Лучшая стартовая позиция: {formatHigh(cs.highest_grid)}</p>
                <small>Поулы: {cs.pole_positions} · Титулы: {cs.world_championships}</small>
              </article>
            </div>
          </section>
        </div>

        <section className="driver-profile-desktop-bio driver-profile-desktop-bio-bottom">
          <h3 className="driver-profile-title">Биография</h3>
          <div className="driver-profile-bio-card">
            <p><GlossaryText>{cleanBiography(data.bio || "Биография пока недоступна.")}</GlossaryText></p>
            <div className="driver-profile-bio-meta">
              <div>
                <span>Гражданство</span>
                <b>{nationalityLabel(data.nationality)}</b>
              </div>
              <div>
                <span>Дата рождения</span>
                <b>{data.dateOfBirth ? new Date(data.dateOfBirth + "T12:00:00").toLocaleDateString("ru-RU") : "—"}</b>
              </div>
            </div>
            {data.url && (
              <a href={data.url} target="_blank" rel="noopener noreferrer" className="driver-bio-link">
                Открыть источник →
              </a>
            )}
          </div>
        </section>
      </section>

    </>
  );
}

export default DriverDetailsPage;
